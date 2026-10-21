/*!
 * promo.js — 宣传页专用：把随机头像批量画到页面里的 canvas 上。
 * 依赖 mc-avatar.js（同目录），无其他依赖。
 *
 * 用法：给 canvas 加 data-avatar，其余用 data-* 传参（都可省略）
 *   <canvas data-avatar data-seed="blog-author" data-size="40"></canvas>
 *   data-seed   同 seed 出同一张图（宣传图靠它保证每次打开都一致）
 *   data-person / data-mode / data-code / data-bubble   同 McAvatar.draw 参数
 *   data-size   设计尺寸(px)，用于取不到 clientWidth 时兜底
 */
(function (global) {
  "use strict";

  var DPR = Math.min(global.devicePixelRatio || 1, 2);

  function pixelSize(canvas) {
    var hint = parseFloat(canvas.getAttribute("data-size") || "0");
    var w = canvas.clientWidth;
    if (!w && canvas.parentElement) w = canvas.parentElement.clientWidth;
    if (!w || w < 8) w = hint || 96;
    return Math.max(16, Math.round(w * DPR));
  }

  function optionsOf(canvas) {
    var d = canvas.dataset;
    var o = { size: pixelSize(canvas) };
    if (d.seed) o.seed = d.seed;
    if (d.person) o.person = d.person;
    if (d.mode) o.mode = d.mode;
    if (d.code) o.code = d.code;
    if (d.bubble !== undefined) o.bubble = d.bubble;  // "" 表示不显示聊天框
    return o;
  }

  async function drawOne(canvas) {
    var out = await McAvatar.draw(canvas, optionsOf(canvas));
    canvas.classList.add("is-ready");
    return out;
  }

  /**
   * 批量绘制。
   * @param {Element} [root] 容器，默认 document
   * @param {number}  [concurrency] 并发数，默认 4
   * @param {Function}[onEach] (canvas, out) 每张画完回调（失败时 out 为 null）
   */
  async function fill(root, concurrency, onEach) {
    var nodes = [].slice.call((root || document).querySelectorAll("canvas[data-avatar]"));
    var cursor = 0;
    var n = Math.max(1, Math.min(concurrency || 4, nodes.length || 1));

    async function worker() {
      while (cursor < nodes.length) {
        var canvas = nodes[cursor++];
        var out = null;
        try {
          out = await drawOne(canvas);
        } catch (err) {
          canvas.classList.add("is-broken");
          console.error("[promo] 头像绘制失败", err);
        }
        if (onEach) onEach(canvas, out);
      }
    }

    await Promise.all(Array.from({ length: n }, worker));
    return nodes;
  }

  global.Promo = { fill: fill, drawOne: drawOne, DPR: DPR };
})(window);
