<p align="center">
  <img src="docs/logo.png" width="120" alt="mcd-avatar logo">
</p>

<h1 align="center">今天什麦人 · mcd-avatar</h1>

<p align="center"><b>Give any project a McDonald's avatar in one line of code.</b></p>

<p align="center">
  <a href="https://jerrytry.github.io/mcd-avatar/"><b>▶ Live demo</b></a>
  &nbsp;·&nbsp;
  <a href="https://jerrytry.github.io/mcd-avatar/avatar/wall.html">Avatar wall</a>
  &nbsp;·&nbsp;
  <a href="https://jerrytry.github.io/mcd-avatar/avatar/use-cases.html">Where it fits</a>
  &nbsp;·&nbsp;
  <a href="README.md">中文</a>
</p>

<p align="center">
Zero dependencies · one canvas · stable per user ID · new menu items flow in automatically
</p>

---

> A **zero-dependency avatar engine**: one `<script>`, one `<canvas>`, one function call, and every user
> in your blog, forum, community, dashboard or app gets an avatar — a doodle character wearing the
> McDonald's hat, topped with a real menu item.
>
> The menu comes from the **McDonald's China MCP** server. When McDonald's launches something new,
> the avatars pick it up.

## ✨ What this is

Two directories, one data pipeline:

```
McDonald's MCP  ──→  mcp/  ──→  avatar/manifest.json  ──→  avatar/
(real menu)      fetch · clean · curate      item list        static avatar generator
```

| Directory | Role | Requirements |
| --- | --- | --- |
| **`avatar/`** | The generator itself: single-page app + embeddable JS engine | **No dependencies, no backend.** Drop it on any static host |
| **`mcp/`** | Data source: pulls the latest menu from MCP, decides which items may appear on avatars | Python + Pillow, only runs when you refresh the menu |

They are loosely coupled: `avatar/` works without Python (it only reads `manifest.json`).
But data flows one way — every item you can pick on an avatar comes from the real MCP menu.

## 🖼 A look

**The whole wall is rendered live.** Nothing is pre-drawn — 7 characters × 250 real menu items × hats,
reshuffled on every reload:

<img src="docs/wall.png" width="860" alt="Random avatar wall combining characters and menu items">

Put it anywhere an avatar appears and it looks like this (blog cards, forum threads, chat lists,
social feeds, team pages, inboxes, mobile profile screens):

<img src="docs/use-1.png" width="860" alt="Avatars in a blog and a forum">

<img src="docs/use-2.png" width="860" alt="Avatars in a chat app and a social feed">

<img src="docs/use-3.png" width="860" alt="Avatars on a team page and in an inbox">

<img src="docs/use-4.png" width="860" alt="Avatars in a mobile app, plus the embed code">

## 🚀 Quick start

### ① Just want an avatar

```bash
cd avatar && python3 -m http.server 8777
# open http://localhost:8777
```

Pick a character and an on-menu item, preview live on canvas, download a PNG. **Nothing to install.**

### ② Embed it in your own project

Copy the `avatar/` directory (at least `mc-avatar.js`, `manifest.json` and `assets/`) into your site,
then:

```html
<script src="mc-avatar.js"></script>
<canvas id="avatar" width="1000" height="1000"></canvas>
<script>
  // Draw onto a canvas (live preview)
  McAvatar.draw(document.getElementById("avatar"), {
    mode: "with_food", person: "a1", code: "1401", bubble: "hi"
  });

  // Or just get an image URL for <img>, upload or storage
  const url = await McAvatar.toDataURL({ seed: 20261021 });   // same seed → same image
</script>
```

| Option | Meaning |
| --- | --- |
| `mode` | `"with_food"` hat + item, `"hat_only"` hat only; random if omitted |
| `person` | character id, e.g. `"a1"`; random if omitted |
| `code` | menu item code, e.g. `"1401"`; random if omitted |
| `bubble` | chat bubble text, **first three characters only, one per line, vertical**; `""` hides it |
| `seed` | number or string, **same seed always renders the same image** — good for per-user assignment |
| `size` | output edge length, default `1000` |
| `manifest` | path to `manifest.json`, defaults to the same directory |

Also available: `McAvatar.toBlob(opts)`, `McAvatar.list()` (characters / items / bubble texts).

> ⚠️ Assets must be **same-origin** with the page (or served with CORS headers), otherwise the canvas
> is tainted and `toDataURL` throws `SecurityError`. The easy path: host the whole `avatar/` directory.

### ③ Refresh the menu (the MCP part)

The menu is not hard-coded. It is a function you can run any time:

```bash
export MCDONALD_TOKEN="your-token"    # request one at https://mcp.mcd.cn
python3 mcp/update_menu.py            # fetch → clean → download images → export
```

It calls the MCP tools `query-nearby-stores`, `query-meals`, `query-meal-detail` and
`list-nutrition-foods`, prints what was **added / delisted**, and rewrites `avatar/manifest.json`.
Offline recompute from cached raw responses:

```bash
python3 mcp/update_menu.py --skip-fetch
```

Details: [MCP_INTEGRATION.md](MCP_INTEGRATION.md).

## 🍟 Which items may appear on avatars

The menu has 250 items and 227 official images locally, but three kinds cannot go on a head:
combo trays (no clear subject), non-food SKUs (toys, hats, sauce packets) and duplicate SKUs.
Curation state lives in a single field, `in_catalog`, inside `mcp/data/catalog.json` — no extra list files:

```bash
python3 mcp/manage.py --list      # full menu with on/off state and suggestions
python3 mcp/manage.py --suggest   # reset by rules (combos / non-food / duplicates excluded)
python3 mcp/manage.py --off 1401  # delist
python3 mcp/manage.py --on 1401   # relist
python3 mcp/export_avatar.py      # apply to the avatar side
```

Delisting never deletes data or images — `--on` plus a re-export restores the item.

## 📦 Repository layout

```
.
├── avatar/          ★ static avatar generator (deployable on its own)
│   ├── index.html     single-page app
│   ├── mc-avatar.js   ★ compositing engine + embeddable API
│   ├── wall.html      promo page: random avatar wall
│   ├── use-cases.html promo page: 7 real UI placements
│   ├── manifest.json  exported data: characters + hats + on-menu items
│   └── assets/        persons / hats / food images
├── mcp/             ★ data source and curation (Python)
│   ├── update_menu.py   fetch → clean → images → export
│   ├── manage.py        list / suggest / on / off
│   ├── export_avatar.py curate → manifest for avatar/
│   └── data/catalog.json  the single source of truth
├── tools/           local verification (not runtime)
├── docs/            promo images used in this README
├── MCP_INTEGRATION.md      how the MCP calls are wired
├── CONTEST_DECLARATION.md  contest declaration (official template)
└── mcp-config.example.json sanitized MCP config example
```

## 🔧 Tech stack

- **Data**: McDonald's China MCP Server (Streamable HTTP / JSON-RPC 2.0)
- **Renderer**: vanilla JS + Canvas, zero dependencies, embeddable
- **Cleaning and verification**: Python + Pillow

## ⚠️ Disclaimer

This is a contest entry for the McDonald's Programmer's Day creative development challenge, built
independently. It is **not an official McDonald's product**. All product images are property of
McDonald's and are used for technical demonstration only. Menu items, prices and availability are
subject to McDonald's official channels.
