// 今天什麦人 · 单页应用（只负责界面与交互，合成全部交给 mc-avatar.js）
// 想在自己的页面里生成头像，不需要这个文件 —— 直接用 mc-avatar.js。

const state = {
  person: null,
  mode: "with_food",   // hat_only | with_food
  food: null,          // 产品 code
  bubble: "",          // 聊天框文案（"" = 不显示）
  shapeFilter: "all",
  search: "",
};

let MANIFEST = null;
let CATALOG = [];      // 已上架且有图的产品子集

const SHAPE_LABELS = {
  all: "全部", burger: "汉堡", chicken: "炸鸡", fries: "薯条",
  drink: "饮品", dessert: "甜品", breakfast: "早餐", side: "小食", other: "其他",
};

// ---------- 绘制（串行执行，避免快速点击时多次绘制互相覆盖） ----------

let renderChain = Promise.resolve();

function render() {
  renderChain = renderChain.then(drawOnce).catch(err => {
    console.error(err);
    setCaption("生成失败：" + (err && err.message ? err.message : err));
  });
  return renderChain;
}

async function drawOnce() {
  const canvas = document.getElementById("avatar");
  const out = await McAvatar.draw(canvas, {
    mode: state.mode,
    person: state.person,
    code: state.food,
    bubble: state.bubble,
  });

  if (out.mode === "with_food" && out.product) {
    const p = out.product;
    const price = p.price ? ` ¥${p.price}` : "";
    const kcal = p.kcal ? ` · ${Math.round(p.kcal)}kcal` : "";
    setCaption(`今日之麦：<b>${p.name}</b>${price}${kcal}`);
    highlightFood(p.code);
  } else {
    setCaption("只戴帽 · 今天不点单");
  }
  return out;
}

function setCaption(html) {
  document.getElementById("caption").innerHTML = html;
}

// ---------- 选项列表 ----------

function buildPersons() {
  const el = document.getElementById("personList");
  el.innerHTML = "";
  MANIFEST.persons.forEach(p => {
    const c = document.createElement("button");
    c.type = "button";
    c.className = "chip" + (p.id === state.person ? " active" : "");
    c.dataset.person = p.id;
    c.setAttribute("aria-label", "角色 " + p.id);
    c.setAttribute("aria-pressed", String(p.id === state.person));
    c.innerHTML = `<img src="${p.src}" alt="" loading="lazy">`;
    c.onclick = () => {
      state.person = p.id;
      document.querySelectorAll(".chip").forEach(x => {
        x.classList.remove("active");
        x.setAttribute("aria-pressed", "false");
      });
      c.classList.add("active");
      c.setAttribute("aria-pressed", "true");
      render();
    };
    el.appendChild(c);
  });
}

function buildFilters() {
  const shapes = new Set(CATALOG.map(p => p.shape_type));
  const el = document.getElementById("shapeFilters");
  el.innerHTML = "";
  const order = ["all", ...Object.keys(SHAPE_LABELS).filter(s => s !== "all" && shapes.has(s))];
  order.forEach(s => {
    const b = document.createElement("button");
    b.type = "button";
    b.className = "fbtn" + (s === state.shapeFilter ? " active" : "");
    b.dataset.shape = s;
    b.setAttribute("aria-pressed", String(s === state.shapeFilter));
    b.textContent = SHAPE_LABELS[s];
    b.onclick = () => {
      state.shapeFilter = s;
      buildFilters();
      buildFoods();
    };
    el.appendChild(b);
  });
}

function buildBubbleBtns() {
  const el = document.getElementById("bubbleFilters");
  el.innerHTML = "";
  McAvatar.BUBBLES.forEach(t => {
    const b = document.createElement("button");
    b.type = "button";
    b.className = "fbtn" + (t === state.bubble ? " active" : "");
    b.dataset.bubble = t;
    b.setAttribute("aria-pressed", String(t === state.bubble));
    b.textContent = t || "空";
    b.onclick = () => {
      state.bubble = t;
      syncBubbleUI();
      render();
    };
    el.appendChild(b);
  });
}

function filteredProducts() {
  const kw = state.search.toLowerCase();
  return CATALOG.filter(p => {
    if (state.shapeFilter !== "all" && p.shape_type !== state.shapeFilter) return false;
    if (kw && !(p.name || "").toLowerCase().includes(kw)) return false;
    return true;
  });
}

function buildFoods() {
  const list = filteredProducts();
  const el = document.getElementById("foodList");
  el.innerHTML = "";
  document.getElementById("foodCount").textContent = list.length;

  list.forEach(p => {
    const cell = document.createElement("button");
    cell.type = "button";
    cell.className = "food-cell" + (String(p.code) === String(state.food) ? " active" : "");
    cell.dataset.code = p.code;
    cell.title = p.name;
    cell.innerHTML = `<img loading="lazy" src="${p.src}" alt=""><span>${p.name}</span>`;
    cell.onclick = () => {
      state.mode = "with_food";
      state.food = p.code;
      syncModeUI();
      buildFoods();
      render();
    };
    el.appendChild(cell);
  });
}

function highlightFood(code) {
  document.querySelectorAll(".food-cell").forEach(c =>
    c.classList.toggle("active", c.dataset.code === String(code)));
}

function syncModeUI() {
  document.querySelectorAll(".mode-btn").forEach(b => {
    const on = b.dataset.mode === state.mode;
    b.classList.toggle("active", on);
    b.setAttribute("aria-pressed", String(on));
  });
  document.getElementById("foodGroup").style.opacity = state.mode === "with_food" ? "1" : ".45";
}

function syncBubbleUI() {
  const el = document.getElementById("bubbleFilters");
  if (!el) return;
  [...el.children].forEach(b => {
    const on = b.dataset.bubble === state.bubble;
    b.classList.toggle("active", on);
    b.setAttribute("aria-pressed", String(on));
  });
}

// ---------- 事件 ----------

function bindEvents() {
  document.querySelectorAll(".mode-btn").forEach(b => {
    b.onclick = () => {
      state.mode = b.dataset.mode;
      if (state.mode === "with_food" && !state.food) state.food = randomFood().code;
      syncModeUI();
      render();
    };
  });

  const search = document.getElementById("foodSearch");
  search.oninput = e => {
    state.search = e.target.value.trim();
    buildFoods();
  };

  document.getElementById("btnRandom").onclick = () => {
    state.person = randomOf(MANIFEST.persons).id;
    state.mode = Math.random() < 0.5 ? "hat_only" : "with_food";
    state.food = randomFood().code;
    state.bubble = randomOf(McAvatar.BUBBLES);
    buildPersons();
    buildFoods();
    syncModeUI();
    syncBubbleUI();
    render();
  };

  document.getElementById("btnDownload").onclick = async () => {
    await renderChain;                 // 确保画布已是当前状态
    const canvas = document.getElementById("avatar");
    const a = document.createElement("a");
    a.download = `什麦人_${stamp()}.png`;
    a.href = canvas.toDataURL("image/png");
    a.click();
  };
}

function randomOf(arr) {
  return arr[Math.floor(Math.random() * arr.length)];
}

function randomFood() {
  return randomOf(CATALOG);
}

function stamp() {
  const d = new Date();
  const pad = n => String(n).padStart(2, "0");
  return `${d.getFullYear()}${pad(d.getMonth() + 1)}${pad(d.getDate())}-${pad(d.getHours())}${pad(d.getMinutes())}`;
}

// ---------- 启动 ----------

async function init() {
  try {
    MANIFEST = await McAvatar.load("manifest.json");
  } catch (err) {
    setCaption("加载清单失败，请通过本地服务器打开（不能直接双击 HTML）。" +
      `<br><code>cd avatar && python3 -m http.server 8777</code>`);
    console.error(err);
    return;
  }

  CATALOG = McAvatar.catalog(MANIFEST);
  state.person = MANIFEST.persons[0].id;
  state.food = randomFood().code;

  buildPersons();
  buildFilters();
  buildFoods();
  buildBubbleBtns();
  syncModeUI();
  syncBubbleUI();
  bindEvents();
  await render();
}

init();
