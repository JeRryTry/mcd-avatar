// 菜品管理页：直接读 mcp/data/catalog.json，勾选后生成一条可执行的 manage.py 命令。
// 纯静态、无后端；页面本身不写文件，避免出现「前后端两套状态」的歧义。

const state = {
  products: [],        // catalog 全量产品
  initial: new Set(),  // 打开页面时的上架状态
  selected: new Set(), // 当前勾选
  query: "",
  onlyHint: false,
};

const $ = id => document.getElementById(id);

// 构建标记：页面上会显示，用来确认你打开的是不是最新前端（旧标签页会显示旧/空）
const BUILD = "2026-10-21 21:35";

function tip(text, isError) {
  const el = $("msg");
  el.textContent = text || "";
  el.style.color = isError ? "#c00" : "var(--muted)";
  if (text) {
    clearTimeout(tip._t);
    tip._t = setTimeout(() => { el.textContent = ""; }, isError ? 9000 : 3000);
  }
}

function visible() {
  const kw = state.query.toLowerCase();
  return state.products.filter(p => {
    if (state.onlyHint && !p.hint) return false;
    if (kw && !(p.name || "").toLowerCase().includes(kw)) return false;
    return true;
  });
}

function renderGrid() {
  const grid = $("grid");
  const list = visible();
  grid.innerHTML = "";

  list.forEach(p => {
    const code = String(p.code);
    const on = state.selected.has(code);
    const cell = document.createElement("button");
    cell.type = "button";
    cell.className = "item" + (on ? " on" : " off");
    cell.dataset.code = code;
    cell.setAttribute("aria-pressed", String(on));

    const img = p.local_image
      ? `<img loading="lazy" src="${p.local_image}" alt="">`
      : `<div class="noimg">缺图</div>`;
    cell.innerHTML =
      (p.hint ? `<span class="hint">${p.hint}</span>` : "") +
      img +
      `<div class="nm">${p.name || code}</div>` +
      `<div class="meta"><span>${p.shape_type || "-"}</span><span>${p.price ? "¥" + p.price : ""}</span></div>`;

    cell.onclick = () => {
      if (state.selected.has(code)) state.selected.delete(code);
      else state.selected.add(code);
      cell.classList.toggle("on", state.selected.has(code));
      cell.classList.toggle("off", !state.selected.has(code));
      cell.setAttribute("aria-pressed", String(state.selected.has(code)));
      renderStats();
    };
    grid.appendChild(cell);
  });

  if (!list.length) {
    grid.innerHTML = `<p class="note">没有匹配的单品。</p>`;
  }
}

function renderStats() {
  $("statSel").textContent = state.selected.size;
}

function diff() {
  const on = [];
  const off = [];
  state.products.forEach(p => {
    const code = String(p.code);
    const was = state.initial.has(code);
    const now = state.selected.has(code);
    if (!was && now) on.push(code);
    if (was && !now) off.push(code);
  });
  return { on, off };
}

async function saveCatalog() {
  const { on, off } = diff();
  if (!on.length && !off.length) {
    tip("没有改动");
    return;
  }
  try {
    const res = await fetch("/api/save-catalog", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ selected: [...state.selected] }),
    });
    if (!res.ok) throw new Error("HTTP " + res.status);
    const data = await res.json();
    if (!data.ok) throw new Error(data.error || "保存失败");
    // 同步基准，避免离开页面时重复提醒
    state.initial = new Set(state.selected);
    $("statListed").textContent = state.selected.size;
    const tail = data.ready != null && data.ready !== data.listed
      ? `，已重新导出头像（其中 ${data.ready} 款有本地图，实际进头像池）`
      : "，已重新导出头像";
    tip(`已保存：上架 ${data.listed} 款${data.export || tail}`);
  } catch (err) {
    const isNet = err && err.name === "TypeError"; // fetch 本身失败（请求没到服务）
    const msg = isNet
      ? "请求未到达服务（请确认用 python3 mcp/serve.py 起服务，并已刷新本页）"
      : (err && err.message) || String(err);
    tip("保存失败：" + msg, true);
  }
}

async function init() {
  let catalog;
  try {
    const res = await fetch("data/catalog.json");
    if (!res.ok) throw new Error(res.status);
    catalog = await res.json();
  } catch (err) {
    tip("加载 data/catalog.json 失败：请在项目根目录起静态服务后访问 /mcp/manage.html", true);
    return;
  }

  state.products = catalog.products || [];
  state.products.forEach(p => {
    const code = String(p.code);
    if (p.in_catalog) state.initial.add(code);
  });
  state.selected = new Set(state.initial);

  const meta = catalog.meta || {};
  $("statMenu").textContent = meta.total_products != null ? meta.total_products : state.products.length;
  $("statImg").textContent = state.products.filter(p => p.local_image).length;
  $("statListed").textContent = state.initial.size;
  $("statNoImg").textContent = state.products.filter(p => !p.local_image).length;

  renderStats();
  renderGrid();

  const b = $("build");
  if (b) b.textContent = "· 前端 v" + BUILD;
  console.log("manage.js 已加载，构建:", BUILD);

  $("q").oninput = e => { state.query = e.target.value.trim(); renderGrid(); };
  $("onlyHint").onchange = e => { state.onlyHint = e.target.checked; renderGrid(); };
  $("btnAll").onclick = () => {
    visible().forEach(p => state.selected.add(String(p.code)));
    renderStats(); renderGrid();
  };
  $("btnNone").onclick = () => {
    visible().forEach(p => state.selected.delete(String(p.code)));
    renderStats(); renderGrid();
  };
  $("btnSave").onclick = saveCatalog;
}

window.addEventListener("beforeunload", e => {
  const { on, off } = diff();
  if (!on.length && !off.length) return;
  e.preventDefault();
  e.returnValue = "";
});

init();
