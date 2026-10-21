/*!
 * mc-avatar.js — 「今天什麦人」头像合成引擎
 *
 * 纯前端、零依赖，只用 manifest.json + 素材图。与 tools/preview.py（Python 参照实现）的几何逻辑保持一致。
 *
 * ── 用法 A：页面里有 <canvas>，直接画上去 ──────────────────────────────
 *   <script src="mc-avatar.js"></script>
 *   <canvas id="avatar" width="1000" height="1000"></canvas>
 *   <script>
 *     McAvatar.draw(document.getElementById("avatar"), {
 *       mode: "with_food", person: "a1", code: "1401", bubble: "你懂的"
 *     });
 *   </script>
 *
 * ── 用法 B：只要一张图（dataURL），塞进 <img> 或上传 ───────────────────
 *   const url = await McAvatar.toDataURL({ seed: 20261021 });
 *   img.src = url;
 *
 * ── 可选项 ─────────────────────────────────────────────────────────────
 *   mode      "hat_only" | "with_food"   不传则随机
 *   person    人物 id，如 "a1"            不传则随机
 *   code      食物 code，如 "1401"        不传则随机
 *   bubble    聊天框文案（固定取前三个字，竖排），"" 表示不显示    不传则随机
 *   seed      数字或字符串，同 seed 出同一张图（可复现）
 *   manifest  manifest.json 的地址，默认同目录
 *   size      输出边长（像素），默认 1000
 *
 * ⚠️ 素材与 manifest 必须同源，或托管方返回 CORS 头 —— 否则 canvas 会被污染，
 *    toDataURL 直接抛 SecurityError。自我托管（把 avatar/ 原样放到自己站点）最省事。
 */
(function (global) {
  "use strict";

  var DEFAULTS = {
    manifest: "manifest.json",
    size: 1000,
  };

  // 几何参数：全部基于 1000×1000 基准画布，输出尺寸不同时整体缩放。
  var G = {
    BASE: 1000,
    HAT_W: 530,          // 帽子基准宽
    HAT_DX: -30,         // 帽子水平偏移(相对画布中心)
    FOOD_W: 480,         // 食物基准宽
    HAT_OVERLAP: 190,    // 帽底压到头顶下方
    MARGIN_TOP: 20,      // 顶部安全边距
    TARGET_HEAD_TOP: 400,// 统一把人物头顶对齐到此高度
    FOOD_DX_RATIO: 0.24, // 食物相对帽子中心的左右偏移比例(×帽宽)
    FOOD_DY: -120,       // 食物上下偏移(相对帽顶,-=上移)
    FOOD_ROT: 16,        // 食物旋转角度(度,正值顺时针)
    AUTO_SHRINK: true,   // 竖高食物自动缩小防出界
  };

  var BUBBLES = ["就这个", "你懂的", "你请客", "加班狗", ""];
  var BUBBLE_CHARS = 3;  // 聊天框固定三个字，竖排

  var _manifests = Object.create(null);
  var _images = Object.create(null);

  // ---------------------------------------------------------------- 基础工具

  function loadImage(src) {
    if (_images[src]) return _images[src];
    var p = new Promise(function (resolve, reject) {
      var im = new Image();
      im.crossOrigin = "anonymous";
      im.onload = function () { resolve(im); };
      im.onerror = function () { reject(new Error("图片加载失败: " + src)); };
      im.src = src;
    });
    _images[src] = p;
    p.catch(function () { delete _images[src]; }); // 失败不缓存，允许重试
    return p;
  }

  var _probe = document.createElement("canvas");
  var _pctx = _probe.getContext("2d", { willReadFrequently: true });

  // 基于 alpha 通道求内容包围盒，自动裁掉素材四周的透明边
  function contentBbox(img) {
    if (img._bbox) return img._bbox;
    var w = img.naturalWidth, h = img.naturalHeight;
    _probe.width = w; _probe.height = h;
    _pctx.clearRect(0, 0, w, h);
    _pctx.drawImage(img, 0, 0);
    var d = _pctx.getImageData(0, 0, w, h).data;
    var minX = w, minY = h, maxX = -1, maxY = -1;
    for (var y = 0; y < h; y++) {
      for (var x = 0; x < w; x++) {
        if (d[(y * w + x) * 4 + 3] > 8) {
          if (x < minX) minX = x;
          if (x > maxX) maxX = x;
          if (y < minY) minY = y;
          if (y > maxY) maxY = y;
        }
      }
    }
    var box = maxX < 0
      ? { x: 0, y: 0, w: w, h: h }
      : { x: minX, y: minY, w: maxX - minX + 1, h: maxY - minY + 1 };
    img._bbox = box;
    return box;
  }

  function drawContentCentered(ctx, img, b, cx, cy, tw, th) {
    ctx.drawImage(img, b.x, b.y, b.w, b.h, cx - tw / 2, cy - th / 2, tw, th);
  }

  // 确定性伪随机：同 seed → 同结果
  function seededRandom(seed) {
    var a = 0;
    if (typeof seed === "number" && isFinite(seed)) {
      a = seed | 0;
    } else {
      var s = String(seed);
      for (var i = 0; i < s.length; i++) a = (a * 31 + s.charCodeAt(i)) | 0;
    }
    return function () {
      a = (a + 0x6D2B79F5) | 0;
      var t = Math.imul(a ^ (a >>> 15), 1 | a);
      t = (t + Math.imul(t ^ (t >>> 7), 61 | t)) ^ t;
      return ((t ^ (t >>> 14)) >>> 0) / 4294967296;
    };
  }

  // ---------------------------------------------------------------- 清单

  function load(url) {
    var key = url || DEFAULTS.manifest;
    if (!_manifests[key]) {
      _manifests[key] = fetch(key).then(function (res) {
        if (!res.ok) throw new Error("manifest 读取失败: " + key + " (" + res.status + ")");
        return res.json();
      });
      _manifests[key].catch(function () { delete _manifests[key]; });
    }
    return _manifests[key];
  }

  // 只有「上架 + 有图」的产品参与合成
  function catalog(manifest) {
    return (manifest.products || []).filter(function (p) {
      return p && p.src && p.in_catalog !== false;
    });
  }

  function pick(array, rng) {
    return array[Math.floor(rng() * array.length) % array.length];
  }

  // 把外部传入的可选项补全成一套确定的绘制参数
  function resolve(manifest, opts) {
    var rng = opts.seed === undefined || opts.seed === null
      ? Math.random
      : seededRandom(opts.seed);

    var persons = manifest.persons || [];
    var products = catalog(manifest);
    if (!persons.length) throw new Error("manifest 里没有人物素材");
    if (!products.length) throw new Error("manifest 里没有可用的食物（检查 in_catalog / 图片）");

    var person = persons.filter(function (p) { return p.id === opts.person; })[0] || pick(persons, rng);
    var mode = opts.mode === "hat_only" || opts.mode === "with_food"
      ? opts.mode
      : (rng() < 0.5 ? "hat_only" : "with_food");
    var product = products.filter(function (p) {
      return String(p.code) === String(opts.code);
    })[0] || pick(products, rng);

    var bubble;
    if (typeof opts.bubble === "string") bubble = opts.bubble;
    else if (opts.bubble === null) bubble = "";
    else bubble = BUBBLES[Math.floor(rng() * BUBBLES.length)];

    return { person: person, mode: mode, product: product, bubble: bubble };
  }

  // ---------------------------------------------------------------- 绘制

  // 聊天框：右侧紧贴人物最左边缘；文案固定三个字，竖排（一字一行）居中
  async function drawBubble(ctx, manifest, text, figLeftX) {
    if (!text || !manifest.bubble) return null;
    var bub;
    try { bub = await loadImage(manifest.bubble.src); } catch (e) { return null; }

    var b = contentBbox(bub);
    var W = G.BASE;
    var bw = Math.max(Math.floor(W * 0.19), figLeftX - 10 - Math.floor(W * 0.01));
    bw = Math.min(bw, Math.floor(W * 0.34));
    var bh = b.h * (bw / b.w);
    var bx = Math.floor(W * 0.01), by = Math.floor(W * 0.34);

    ctx.save(); // 隔离文字对齐等状态，避免污染后续绘制
    drawContentCentered(ctx, bub, b, bx + bw / 2, by + bh / 2, bw, bh);

    // 固定三个字：只取前 3 个字符，一字一行竖排（宁少不挤）
    var chars = String(text).replace(/\s+/g, "").slice(0, BUBBLE_CHARS).split("");
    var fsize = Math.round(Math.min(Math.max(bw * 0.30, 44), 88));
    var lh = Math.round(fsize * 1.16);
    ctx.font = "bold " + fsize + "px -apple-system, 'PingFang SC', 'Microsoft YaHei', sans-serif";
    ctx.textBaseline = "top";
    ctx.textAlign = "center";
    ctx.lineJoin = "round";
    var y0 = by + bh / 2 - (lh * chars.length) / 2 + (lh - fsize) / 2;
    chars.forEach(function (ch, i) {
      var y = y0 + i * lh;
      ctx.lineWidth = 4;
      ctx.strokeStyle = "#141414";
      ctx.strokeText(ch, bx + bw / 2, y);
      ctx.fillStyle = "#141414";
      ctx.fillText(ch, bx + bw / 2, y);
    });
    ctx.restore();
    return { x: bx, y: by, w: bw, h: bh };
  }

  // 在 1000×1000 坐标系里画完整画面
  async function paint(ctx, manifest, picked) {
    var W = G.BASE;

    // 1) 人物：等比缩放 + 平移，把头顶对齐到 TARGET_HEAD_TOP，上方留给帽子和食物
    var pImg = await loadImage(picked.person.src);
    var dy = G.TARGET_HEAD_TOP - picked.person.head_top_ratio * W;
    ctx.drawImage(pImg, 0, dy, W, W);

    // 人物内容最左边缘（供聊天框避让）
    var pb = contentBbox(pImg);
    var figLeftX = pb.x * (W / pImg.naturalWidth);

    var headTop = G.TARGET_HEAD_TOP;
    var cx = W / 2;
    var drawn = null;

    if (picked.mode === "hat_only") {
      if (manifest.hats && manifest.hats.plain) {
        var hat = await loadImage(manifest.hats.plain.src);
        var hb = contentBbox(hat);
        var hh = hb.h * (G.HAT_W / hb.w);
        var hatBottom = headTop + G.HAT_OVERLAP;
        drawContentCentered(ctx, hat, hb, cx + G.HAT_DX, hatBottom - hh / 2, G.HAT_W, hh);
      }
    } else {
      if (!manifest.hats || !manifest.hats.food) throw new Error("manifest 缺少顶食帽素材（hats.food）");

      var fhat = await loadImage(manifest.hats.food.src);
      var fhb = contentBbox(fhat);
      var hatW = G.HAT_W, hatH = fhb.h * (G.HAT_W / fhb.w);

      var food = await loadImage(picked.product.src);
      var fb = contentBbox(food);
      var foodW = G.FOOD_W, foodH = fb.h * (G.FOOD_W / fb.w);

      var hatCx = cx + G.HAT_DX;
      var hBottom = headTop + G.HAT_OVERLAP;
      var hcyc = hBottom - hatH / 2;
      var hTop = hcyc - hatH / 2;

      // 以帽顶为基准向上放食物；竖高食物(杯子)按剩余空间自动缩小，绝不顶出画布
      var avail = Math.max(hTop - G.MARGIN_TOP + 40, 80);
      if (G.AUTO_SHRINK && foodH > avail) {
        var k = avail / foodH;
        foodW *= k; foodH *= k;
      }

      // Z 轴：食物在帽子下层 → 先画食物(绕自身中心旋转)，再画帽子盖在其上
      var fcx = hatCx + hatW * G.FOOD_DX_RATIO;
      var fcy = hTop - foodH / 2 - G.FOOD_DY;
      ctx.save();
      ctx.translate(fcx, fcy);
      ctx.rotate(G.FOOD_ROT * Math.PI / 180);
      ctx.drawImage(food, fb.x, fb.y, fb.w, fb.h, -foodW / 2, -foodH / 2, foodW, foodH);
      ctx.restore();

      drawContentCentered(ctx, fhat, fhb, hatCx, hcyc, hatW, hatH);
      drawn = picked.product;
    }

    // 2) 聊天框画在最上层
    var bubbleBox = await drawBubble(ctx, manifest, picked.bubble, figLeftX);
    return { product: drawn, bubbleBox: bubbleBox };
  }

  // ---------------------------------------------------------------- 对外 API

  /**
   * 把头像画到给定 canvas 上。
   * @returns {Promise<{person, mode, product, bubble, canvas}>}
   */
  async function draw(canvas, opts) {
    opts = opts || {};
    var manifest = await load(opts.manifest || DEFAULTS.manifest);

    // 尺寸优先级：显式 size > canvas 上的 width/height 属性 > 默认 1000
    var attr = canvas.getAttribute("width") && canvas.getAttribute("height")
      ? Math.min(parseInt(canvas.getAttribute("width"), 10), parseInt(canvas.getAttribute("height"), 10))
      : 0;
    var size = Math.round(opts.size || attr || DEFAULTS.size);

    if (canvas.width !== size || canvas.height !== size) {
      canvas.width = size;
      canvas.height = size;
    }
    var ctx = canvas.getContext("2d");
    if (!ctx) throw new Error("canvas.getContext('2d') 不可用");

    var picked = resolve(manifest, opts);

    ctx.setTransform(1, 0, 0, 1, 0, 0);
    ctx.clearRect(0, 0, size, size);
    ctx.fillStyle = "#ffffff";
    ctx.fillRect(0, 0, size, size);

    var scale = size / G.BASE;
    ctx.save();
    ctx.setTransform(scale, 0, 0, scale, 0, 0);
    await paint(ctx, manifest, picked);
    ctx.restore();

    return {
      person: picked.person.id,
      mode: picked.mode,
      product: picked.product,
      bubble: picked.bubble,
      canvas: canvas,
    };
  }

  /** 生成一张 PNG 的 dataURL（内部用离屏 canvas，不碰页面 DOM）。 */
  async function toDataURL(opts) {
    var size = (opts && opts.size) || DEFAULTS.size;
    var canvas = document.createElement("canvas");
    canvas.width = size;
    canvas.height = size;
    await draw(canvas, opts);
    return canvas.toDataURL("image/png");
  }

  /** 生成 Blob（适合直接上传 / File 对象 / URL.createObjectURL）。 */
  function toBlob(opts) {
    return new Promise(function (resolve, reject) {
      toDataURL(opts).then(function (url) {
        try {
          var bin = atob(url.split(",")[1]);
          var bytes = new Uint8Array(bin.length);
          for (var i = 0; i < bin.length; i++) bytes[i] = bin.charCodeAt(i);
          resolve(new Blob([bytes], { type: "image/png" }));
        } catch (e) { reject(e); }
      }, reject);
    });
  }

  /** 清单摘要：可选人物 / 上架食物 / 气泡文案。 */
  function list(url) {
    return load(url || DEFAULTS.manifest).then(function (manifest) {
      return {
        persons: manifest.persons || [],
        products: catalog(manifest),
        bubbles: BUBBLES.slice(),
        meta: manifest.meta || {},
      };
    });
  }

  global.McAvatar = {
    draw: draw,
    toDataURL: toDataURL,
    toBlob: toBlob,
    load: load,
    list: list,
    catalog: catalog,
    BUBBLES: BUBBLES,
    VERSION: "1.0.0",
  };
})(window);
