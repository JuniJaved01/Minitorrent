/* MiniTorrent UI. Talks only to the local UI server (/api/...), which runs the tracker and the client node. */
"use strict";

// ------------------------------------------------------------------ state
const S = {
  data: null,            // last /api/state reply
  route: "/",            // current screen
  tab: "seeding",        // client tab: seeding | swarm
  filter: "",            // client search text
  devFilter: "",         // server device search text
  selectedDevice: null,  // server: selected device key
  testResult: null,      // client connect form: last "Test connection" result
  busy: false,           // a button action is running
  form: null,            // client connect form values (kept while typing)
  hostPort: null,        // server host form value
  peerColors: {},        // telemetry: ip:port -> colour
};
const PEER_COLORS = ["#00f2fe", "#4edea3", "#ffb95f", "#c084fc", "#f472b6", "#60a5fa", "#a3e635", "#fb7185"];

// ------------------------------------------------------------------ helpers
const $ = (sel) => document.querySelector(sel);
const esc = (v) => String(v ?? "").replace(/[&<>"']/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c]));
function fmtBytes(n) {
  n = Number(n) || 0;
  const u = ["B", "KB", "MB", "GB", "TB"];
  let i = 0;
  while (n >= 1024 && i < u.length - 1) { n /= 1024; i++; }
  return (i === 0 ? n.toFixed(0) : n.toFixed(n >= 100 ? 0 : n >= 10 ? 1 : 2)) + " " + u[i];
}
function rateParts(bps) {  // [number, unit] for big stat tiles
  const s = fmtBytes(bps).split(" ");
  return [s[0], s[1] + "/s"];
}
const fmtRate = (bps) => fmtBytes(bps) + "/s";
function fmtDuration(sec) {
  if (sec == null || !isFinite(sec)) return "—";
  sec = Math.round(sec);
  if (sec < 60) return sec + "s";
  if (sec < 3600) return Math.floor(sec / 60) + "m " + (sec % 60) + "s";
  return Math.floor(sec / 3600) + "h " + Math.floor((sec % 3600) / 60) + "m";
}
function fmtAgo(ts) {
  return fmtDuration(Date.now() / 1000 - ts) + " ago";
}
function fileIcon(name) {
  const ext = (name.split(".").pop() || "").toLowerCase();
  const map = [
    [["iso", "img", "dmg"], "terminal", "text-primary-container"],
    [["mp4", "mkv", "mov", "avi", "webm"], "movie", "text-primary-container"],
    [["mp3", "wav", "flac", "ogg", "m4a"], "music_note", "text-secondary"],
    [["png", "jpg", "jpeg", "gif", "webp", "svg", "bmp", "tif", "tiff"], "image", "text-secondary"],
    [["zip", "gz", "tar", "rar", "7z", "zst", "xz", "bz2"], "folder_zip", "text-tertiary-fixed-dim"],
    [["pdf", "doc", "docx", "txt", "md", "ppt", "pptx", "xls", "xlsx", "csv"], "description", "text-primary"],
    [["db", "sql", "dump", "parquet", "sqlite", "json"], "database", "text-tertiary-fixed-dim"],
    [["exe", "msi", "bin", "apk", "deb"], "deployed_code", "text-primary-container"],
    [["py", "js", "ts", "c", "cpp", "java", "html", "css"], "code", "text-secondary"],
  ];
  for (const [exts, icon, color] of map) if (exts.includes(ext)) return [icon, color];
  return ["draft", "text-on-surface-variant"];
}
const icon = (name, cls = "text-[18px]") => `<span class="material-symbols-outlined ${cls}">${name}</span>`;
function setHTML(el, html) {  // only touch the DOM when something changed (keeps hover + scroll)
  if (el && el._html !== html) { el.innerHTML = html; el._html = html; }
}

async function api(path, body, opts = {}) {
  const res = await fetch(path, {
    method: body === undefined && !opts.method ? "GET" : (opts.method || "POST"),
    headers: opts.raw ? {} : { "Content-Type": "application/json" },
    body: opts.raw ? opts.raw : body === undefined ? undefined : JSON.stringify(body),
  });
  let data = null;
  try { data = await res.json(); } catch (e) { /* not JSON */ }
  if (!res.ok) throw new Error((data && data.detail) || res.statusText);
  return data;
}

let toastTimer;
function toast(msg, kind = "info") {
  const colors = { info: ["info", "text-primary-container"], ok: ["check_circle", "text-secondary"], err: ["error", "text-error"], warn: ["warning", "text-tertiary-fixed-dim"] };
  const [ic, col] = colors[kind] || colors.info;
  $("#toastIcon").textContent = ic;
  $("#toastIcon").className = "material-symbols-outlined text-[18px] " + col;
  $("#toastMsg").textContent = msg;
  const t = $("#toast");
  t.classList.remove("translate-y-12", "opacity-0");
  clearTimeout(toastTimer);
  toastTimer = setTimeout(() => t.classList.add("translate-y-12", "opacity-0"), 3500);
}

async function act(fn, okMsg) {  // run a button action with error toast
  if (S.busy) return;
  S.busy = true;
  try {
    const r = await fn();
    if (okMsg) toast(typeof okMsg === "function" ? okMsg(r) : okMsg, "ok");
    await refresh();
    return r;
  } catch (e) {
    toast(e.message, "err");
  } finally {
    S.busy = false;
  }
}

// ------------------------------------------------------------------ modal
function openModal(html, onMount) {
  const m = $("#modal");
  $("#modalBox").innerHTML = html;
  m.classList.remove("hidden");
  m.classList.add("flex");
  if (onMount) onMount($("#modalBox"));
}
function closeModal() {
  const m = $("#modal");
  m.classList.add("hidden");
  m.classList.remove("flex");
  $("#modalBox").innerHTML = "";
}
$("#modal").addEventListener("mousedown", (e) => { if (e.target.id === "modal") closeModal(); });
document.addEventListener("keydown", (e) => { if (e.key === "Escape") closeModal(); });
const modalHead = (title, ic, color = "text-primary-container") => `
  <div class="flex items-center justify-between px-space-lg py-space-md border-b border-white/5">
    <div class="flex items-center gap-space-sm">${icon(ic, "text-[20px] " + color)}<h3 class="font-headline-md text-headline-md text-primary">${title}</h3></div>
    <button class="w-8 h-8 rounded-lg hover:bg-white/5 flex items-center justify-center text-outline" onclick="closeModal()">${icon("close")}</button>
  </div>`;

function confirmBox({ title, text, okLabel = "Confirm", danger = false, onOk }) {
  openModal(`${modalHead(esc(title), danger ? "warning" : "help", danger ? "text-error" : "text-primary-container")}
    <div class="p-space-lg font-body-md text-body-md text-on-surface-variant">${text}</div>
    <div class="flex justify-end gap-space-sm px-space-lg pb-space-lg">
      <button class="btn-ghost" onclick="closeModal()">Cancel</button>
      <button class="${danger ? "btn-danger" : "btn-primary"}" id="confirmOk">${esc(okLabel)}</button>
    </div>`, (box) => {
    box.querySelector("#confirmOk").onclick = () => { closeModal(); onOk(); };
  });
}

// ------------------------------------------------------------------ folder picker
function folderPicker(startPath, onPick) {
  let current = startPath;
  const load = async (path) => {
    let d;
    try { d = await api("/api/fs/list?path=" + encodeURIComponent(path || "")); }
    catch (e) {
      if (path) { toast(e.message, "warn"); return load(""); }  // fall back to the home folder
      toast(e.message, "err"); return;
    }
    current = d.path;
    const box = $("#modalBox");
    box.querySelector("#fpPath").value = d.path;
    box.querySelector("#fpRoots").innerHTML = d.roots.map((r) =>
      `<button class="chip-btn" data-path="${esc(r.path)}">${esc(r.label)}</button>`).join("");
    box.querySelector("#fpList").innerHTML =
      (d.parent ? `<button class="fp-row" data-path="${esc(d.parent)}">${icon("arrow_upward", "text-[18px] text-outline")}<span>..</span></button>` : "") +
      (d.dirs.length ? d.dirs.map((n) => `<button class="fp-row" data-path="${esc(d.path + (d.path.endsWith(d.sep) ? "" : d.sep) + n)}">${icon("folder", "text-[18px] text-primary-container")}<span class="truncate">${esc(n)}</span></button>`).join("")
        : `<div class="px-space-md py-space-lg text-outline font-body-sm">No sub-folders here.</div>`);
    box.querySelector("#fpInfo").textContent = d.files + " file(s) in this folder will be shared";
    box.querySelectorAll("[data-path]").forEach((b) => (b.onclick = () => load(b.dataset.path)));
  };
  openModal(`${modalHead("Choose shared folder", "folder_open")}
    <div class="p-space-lg flex flex-col gap-space-md min-h-0">
      <div class="flex gap-space-sm"><input id="fpPath" class="input flex-1" spellcheck="false"><button class="btn-ghost" id="fpGo">Go</button></div>
      <div id="fpRoots" class="flex flex-wrap gap-space-xs"></div>
      <div id="fpList" class="flex flex-col bg-surface-container-lowest rounded-lg border border-white/5 overflow-y-auto max-h-[300px] min-h-[160px]"></div>
      <div class="flex items-center gap-space-sm">
        <input id="fpNew" class="input flex-1" placeholder="New folder name">
        <button class="btn-ghost" id="fpMk">${icon("create_new_folder", "text-[16px]")}Create</button>
      </div>
      <div id="fpInfo" class="font-label-sm text-label-sm text-outline"></div>
    </div>
    <div class="flex justify-end gap-space-sm px-space-lg pb-space-lg">
      <button class="btn-ghost" onclick="closeModal()">Cancel</button>
      <button class="btn-primary" id="fpPick">${icon("check", "text-[16px]")}Use this folder</button>
    </div>`, (box) => {
    box.querySelector("#fpGo").onclick = () => load(box.querySelector("#fpPath").value);
    box.querySelector("#fpPath").onkeydown = (e) => { if (e.key === "Enter") load(e.target.value); };
    box.querySelector("#fpMk").onclick = async () => {
      const name = box.querySelector("#fpNew").value.trim();
      if (!name) return;
      try { const r = await api("/api/fs/mkdir", { path: current, name }); box.querySelector("#fpNew").value = ""; load(r.path); }
      catch (e) { toast(e.message, "err"); }
    };
    box.querySelector("#fpPick").onclick = () => { closeModal(); onPick(current); };
    load(startPath);
  });
}

// ------------------------------------------------------------------ routing
function route() {
  S.route = (location.hash.replace(/^#/, "") || "/").split("?")[0];
  if (!["/", "/client", "/server", "/telemetry", "/config"].includes(S.route)) S.route = "/";
  document.querySelectorAll(".view").forEach((v) => v.classList.toggle("hidden", v.dataset.view !== S.route));
  const navActive = (el) => el.dataset.route === S.route;
  document.querySelectorAll(".top-link").forEach((a) => {
    a.className = "top-link px-space-md py-space-xs rounded-lg font-label-md text-label-md transition-colors " +
      (navActive(a) ? "bg-surface-container-high text-primary font-bold" : "text-on-surface-variant hover:text-on-surface hover:bg-surface-container-high");
  });
  document.querySelectorAll(".side-link").forEach((a) => {
    a.className = "side-link flex items-center gap-space-md px-space-md py-space-sm rounded-lg transition-colors " +
      (navActive(a) ? "bg-surface-container-high text-primary font-bold" : "text-on-surface-variant hover:bg-surface-container-high hover:text-on-surface");
  });
  if (S.route === "/") restartIntro();
  render();
}
window.addEventListener("hashchange", route);
document.addEventListener("keydown", (e) => {
  if (S.route !== "/" || e.target.tagName === "INPUT" || !$("#modal").classList.contains("hidden")) return;
  if (e.key === "1") location.hash = "#/client";
  if (e.key === "2") location.hash = "#/server";
});

// ------------------------------------------------------------------ top bar + sidebar
function renderChrome() {
  const d = S.data, c = d && d.client, s = d && d.server;
  let pill;
  if (!d) pill = `<span class="w-2 h-2 rounded-full bg-error"></span><span class="font-label-sm text-label-sm text-error uppercase">UI offline</span>`;
  else if (c && c.status === "online") pill = `<span class="w-2 h-2 rounded-full bg-secondary-fixed-dim animate-pulse"></span><span class="font-label-sm text-label-sm text-secondary uppercase">Online</span>`;
  else if (c && c.status === "kicked") pill = `<span class="w-2 h-2 rounded-full bg-error animate-pulse"></span><span class="font-label-sm text-label-sm text-error uppercase">Disconnected</span>`;
  else if (c) pill = `<span class="w-2 h-2 rounded-full bg-tertiary-fixed-dim animate-pulse"></span><span class="font-label-sm text-label-sm text-tertiary-fixed-dim uppercase">Reconnecting</span>`;
  else if (s) pill = `<span class="w-2 h-2 rounded-full bg-secondary-fixed-dim animate-pulse"></span><span class="font-label-sm text-label-sm text-secondary uppercase">Hosting</span>`;
  else pill = `<span class="w-2 h-2 rounded-full bg-secondary-fixed-dim"></span><span class="font-label-sm text-label-sm text-secondary uppercase">Ready</span>`;
  const sep = `<span class="text-outline-variant font-label-sm text-label-sm">/</span>`;
  const kv = (k, v, cls = "text-primary") => `<div class="flex items-center gap-space-xs"><span class="font-label-sm text-label-sm text-on-surface-variant">${k}:</span><span class="font-label-sm text-label-sm ${cls}">${esc(v)}</span></div>`;
  let mid = "";
  if (c) mid = sep + kv("Peers", c.stats.seeders + c.stats.leechers) + sep + kv("Port", c.peer_port, "text-on-surface");
  else if (s) mid = sep + kv("Devices", s.stats.devices_online) + sep + kv("Port", s.port, "text-on-surface");
  const dl = c ? c.stats.down_rate : 0, ul = c ? c.stats.up_rate : (s ? s.stats.activity : 0);
  const name = d ? d.device_name : "?";
  const initials = name.replace(/[^A-Za-z0-9]/g, "").slice(0, 2).toUpperCase() || "PC";
  setHTML($("#topStatus"), `
    <div class="hidden md:flex items-center gap-space-md px-space-md py-space-xs bg-surface-container-low rounded-lg"><div class="flex items-center gap-space-xs">${pill}</div>${mid}</div>
    <div class="hidden sm:flex items-center gap-space-md px-space-md py-space-xs bg-surface-container-low rounded-lg">
      <div class="flex items-center gap-space-xs">${icon("download", "text-primary-container text-[16px]")}<span class="font-label-sm text-label-sm text-on-surface-variant">DL:</span><span class="font-label-sm text-label-sm text-primary">${fmtRate(dl)}</span></div>
      <div class="flex items-center gap-space-xs">${icon("upload", "text-secondary text-[16px]")}<span class="font-label-sm text-label-sm text-on-surface-variant">UL:</span><span class="font-label-sm text-label-sm text-secondary">${fmtRate(ul)}</span></div>
    </div>
    <div class="w-8 h-8 rounded-full bg-primary flex items-center justify-center font-label-md text-label-md text-on-primary font-bold" title="This PC: ${esc(name)}">${esc(initials)}</div>`);

  // sidebar footer: swarm coverage (client) or tracker health (server)
  let foot;
  if (c) {
    const total = c.shared.length + c.available.length;
    const pct = total ? Math.round((100 * c.shared.length) / total) : 0;
    foot = footCard("Swarm Coverage", pct + "%", pct, `${c.shared.length} files`, c.status === "online" ? "Sync OK" : "Retrying", c.status === "online");
  } else if (s) {
    foot = footCard("Tracker Uptime", fmtDuration(s.uptime), 100, `${s.stats.devices_online} online`, "Hosting", true);
  } else {
    foot = `<div class="p-space-md bg-surface-container-low rounded-lg flex items-center justify-between text-on-surface-variant"><div class="flex items-center gap-space-xs"><span class="w-2 h-2 rounded-full bg-secondary"></span><span class="font-label-sm text-label-sm text-on-surface">System Ready</span></div><span class="font-label-sm text-label-sm text-outline">v2.0</span></div>`;
  }
  setHTML($("#sideFooter"), foot);
  $("#clientCta").textContent = c ? "Open Client Terminal" : "Start Sharing";
  $("#serverCta").textContent = s ? "Open Tracker Node" : "Open Manager";
}
function footCard(label, value, pct, left, right, ok) {
  return `<div class="p-space-md bg-surface-container-low rounded-lg flex flex-col gap-space-sm">
    <div class="flex items-center justify-between"><span class="font-label-sm text-label-sm text-on-surface">${label}</span><span class="font-label-sm text-label-sm text-primary">${esc(value)}</span></div>
    <div class="h-1.5 w-full bg-surface-container-highest rounded-full overflow-hidden"><div class="h-full bg-primary-container transition-all duration-700" style="width:${pct}%"></div></div>
    <div class="flex items-center justify-between"><span class="font-label-sm text-label-sm text-outline">${esc(left)}</span><span class="font-label-sm text-label-sm ${ok ? "text-secondary" : "text-tertiary-fixed-dim"}">${esc(right)}</span></div>
  </div>`;
}

// ------------------------------------------------------------------ CLIENT: connect form
function renderConnect(el) {
  const d = S.data;
  if (!S.form) S.form = {
    host: d.last_client.host || "127.0.0.1",
    port: d.last_client.port || d.default_tracker_port,
    folder: d.last_client.folder || d.default_folder,
    name: d.device_name,
  };
  const f = S.form, t = S.testResult;
  let testLine = `<span class="text-outline">Check that a MiniTorrent server is running at this address before connecting.</span>`;
  if (t && t.pending) testLine = `<span class="text-primary-container flex items-center gap-1">${icon("progress_activity", "text-[14px] animate-spin")}Checking ${esc(t.addr)}...</span>`;
  else if (t && t.ok) testLine = `<span class="text-secondary flex items-center gap-1">${icon("check_circle", "text-[14px]")}Server found: <b>${esc(t.name)}</b> (v${esc(t.version)}) in ${t.ms} ms. It sees you as ${esc(t.your_ip)}.</span>`;
  else if (t) testLine = `<span class="text-error flex items-center gap-1">${icon("error", "text-[14px]")}${esc(t.error)}</span>`;
  const html = `
  <div class="max-w-3xl mx-auto flex flex-col gap-space-lg intro-fast">
    <div class="flex items-center gap-space-md">
      <div class="w-12 h-12 rounded-xl bg-primary-container/10 flex items-center justify-center text-primary-container">${icon("lan", "text-[24px]")}</div>
      <div><h1 class="font-headline-lg text-headline-lg text-primary">Connect to a Server</h1>
      <p class="font-body-sm text-body-sm text-on-surface-variant">Enter the address the server owner shared with you, then choose the folder this PC shares.</p></div>
    </div>
    <div class="bg-surface-container-lowest rounded-xl shadow-md overflow-hidden">
      <div class="px-space-lg py-space-md bg-surface-container-low flex items-center gap-space-sm">${icon("dns", "text-primary-container text-[20px]")}<h2 class="font-headline-md text-headline-md text-primary">1. Server address</h2></div>
      <div class="p-space-lg flex flex-col gap-space-md">
        <div class="grid grid-cols-1 sm:grid-cols-[1fr_140px] gap-space-md">
          <label class="flex flex-col gap-space-xs"><span class="field-label">Server IP or URL</span><input id="cHost" class="input" value="${esc(f.host)}" placeholder="192.168.1.10" spellcheck="false"></label>
          <label class="flex flex-col gap-space-xs"><span class="field-label">Port</span><input id="cPort" class="input" value="${esc(f.port)}" inputmode="numeric"></label>
        </div>
        <div class="flex flex-wrap items-center justify-between gap-space-md">
          <div class="font-label-md text-label-md">${testLine}</div>
          <button class="btn-ghost" id="cTest">${icon("network_ping", "text-[16px]")}Test connection</button>
        </div>
      </div>
    </div>
    <div class="bg-surface-container-lowest rounded-xl shadow-md overflow-hidden">
      <div class="px-space-lg py-space-md bg-surface-container-low flex items-center gap-space-sm">${icon("folder_shared", "text-secondary text-[20px]")}<h2 class="font-headline-md text-headline-md text-primary">2. Shared folder on this PC</h2></div>
      <div class="p-space-lg flex flex-col gap-space-md">
        <div class="flex gap-space-sm"><input id="cFolder" class="input flex-1" value="${esc(f.folder)}" spellcheck="false"><button class="btn-ghost" id="cBrowse">${icon("folder_open", "text-[16px]")}Browse</button></div>
        <p class="font-body-sm text-body-sm text-outline">Every file in this folder is shared with the swarm, and files you download are saved here. It can be anywhere on your disk. If it does not exist yet, it will be created.</p>
        <label class="flex flex-col gap-space-xs"><span class="field-label">Device name shown on the server</span><input id="cName" class="input" value="${esc(f.name)}"></label>
      </div>
    </div>
    <div class="flex justify-end gap-space-sm">
      <a class="btn-ghost" href="#/">Back</a>
      <button class="btn-primary" id="cConnect">${icon("link", "text-[18px]")}Connect &amp; start sharing</button>
    </div>
  </div>`;
  setHTML(el, html);
  const sync = () => { f.host = $("#cHost").value; f.port = $("#cPort").value; f.folder = $("#cFolder").value; f.name = $("#cName").value; };
  ["#cHost", "#cPort", "#cFolder", "#cName"].forEach((id) => { $(id).oninput = sync; });
  $("#cHost").onkeydown = $("#cPort").onkeydown = (e) => { if (e.key === "Enter") testConn(); };
  $("#cTest").onclick = testConn;
  $("#cBrowse").onclick = () => folderPicker(f.folder, (p) => { f.folder = p; el._html = null; render(); });
  $("#cConnect").onclick = async () => {
    sync();
    const btn = $("#cConnect");
    btn.disabled = true;
    btn.innerHTML = icon("progress_activity", "text-[18px] animate-spin") + "Connecting...";
    try {
      await api("/api/client/connect", { host: f.host, port: f.port, folder: f.folder, name: f.name, create: true });
      toast("Connected. Sharing " + f.folder, "ok");
      S.testResult = null;
      await refresh();
    } catch (e) {
      toast(e.message, "err");
      S.testResult = { ok: false, error: e.message };
      el._html = null;
      render();
    }
  };
}
async function testConn() {
  const f = S.form;
  f.host = $("#cHost").value; f.port = $("#cPort").value;
  S.testResult = { pending: true, addr: f.host + ":" + f.port };
  $("#clientView")._html = null; render();
  try { S.testResult = await api("/api/client/test", { host: f.host, port: f.port }); }
  catch (e) { S.testResult = { ok: false, error: e.message }; }
  $("#clientView")._html = null; render();
}

// ------------------------------------------------------------------ CLIENT: terminal
function statTile(label, value, unit, note, noteCls, ic, icCls, valCls = "text-primary", unitCls = "text-primary-container font-mono") {
  return `<div class="bg-surface-container-lowest p-space-lg rounded-xl shadow-md flex items-center justify-between">
    <div class="flex flex-col gap-1"><span class="font-label-sm text-label-sm text-outline uppercase tracking-wider">${label}</span>
      <div class="flex items-baseline gap-space-xs"><span class="font-headline-xl text-headline-xl ${valCls} font-bold tracking-tight">${esc(value)}</span><span class="font-label-md text-label-md ${unitCls}">${esc(unit)}</span></div>
      <span class="font-label-sm text-label-sm ${noteCls}">${note}</span></div>
    <div class="w-10 h-10 rounded-xl bg-surface-container-high flex items-center justify-center ${icCls}">${icon(ic, "text-[22px]")}</div></div>`;
}
const chip = (text, cls, dot, pulse = false) =>
  `<div class="inline-flex items-center gap-1.5 px-space-sm py-0.5 rounded-full ${cls} font-label-sm text-label-sm whitespace-nowrap"><span class="w-1.5 h-1.5 rounded-full ${dot} ${pulse ? "animate-pulse" : ""}"></span><span>${text}</span></div>`;
const iconBtn = (ic, title, onclick, cls = "text-on-surface hover:text-primary hover:bg-surface-container-high") =>
  `<button class="w-8 h-8 rounded-lg bg-surface-container flex items-center justify-center ${cls} transition-colors" title="${esc(title)}" onclick="${onclick}">${icon(ic, "text-[16px]")}</button>`;

function renderClient(el) {
  const c = S.data.client;
  if (!c) return renderConnect(el);
  S.form = null;
  const st = c.stats;
  const [dv, du] = rateParts(st.down_rate), [uv, uu] = rateParts(st.up_rate);
  const q = S.filter.toLowerCase();
  const shared = c.shared.filter((f) => f.name.toLowerCase().includes(q));
  const avail = c.available.filter((f) => f.name.toLowerCase().includes(q));
  const totalSize = c.shared.reduce((a, f) => a + f.size, 0);
  const seedingCount = c.shared.filter((f) => f.status === "seeding").length;
  const anyRed = c.available.some((f) => f.health === "slow" || f.health === "unavailable");
  const anyWeak = anyRed || c.available.some((f) => f.health === "low");

  let banner = "";
  if (c.status !== "online") {
    const red = c.status === "kicked";
    banner = `<div class="flex items-center gap-space-sm px-space-lg py-space-md rounded-xl ${red ? "bg-error-container/30 text-error" : "bg-tertiary-container/10 text-tertiary-fixed-dim"}">${icon(red ? "link_off" : "sync_problem", "text-[20px]")}<span class="font-body-md">${esc(c.message)}</span></div>`;
  }

  const tabBtn = (id, ic, label, count, countCls) => {
    const on = S.tab === id;
    return `<button class="flex items-center gap-space-xs px-space-lg py-space-sm rounded-lg font-label-md text-label-md transition-all ${on ? "bg-surface-container-high text-primary font-bold shadow-sm" : "text-on-surface-variant hover:text-on-surface hover:bg-surface-container-low"}" onclick="setTab('${id}')">${icon(ic)}<span>${label}</span><span class="ml-space-xs px-space-xs py-0.5 rounded-full ${countCls} text-[10px]">${count}</span></button>`;
  };

  // --- shared files table
  const sharedRows = shared.map((f) => {
    const [ic, col] = fileIcon(f.name);
    let status;
    if (f.status === "hashing") status = chip(`Hashing ${Math.round(f.progress * 100)}%`, "bg-tertiary-container/10 text-tertiary-fixed-dim", "bg-tertiary-fixed-dim", true);
    else if (f.status === "seeding") status = chip(`Seeding (${f.peers} Peer${f.peers === 1 ? "" : "s"})`, "bg-secondary-container/20 text-secondary", "bg-secondary");
    else if (f.status === "paused") status = chip("Paused", "bg-surface-container-highest text-on-surface-variant", "bg-outline");
    else status = `<span title="${esc(f.error)}">${chip("Error", "bg-error-container/30 text-error", "bg-error")}</span>`;
    const n = esc(JSON.stringify(f.name));
    const toggle = f.status === "seeding" ? iconBtn("pause", "Pause sharing", `shareAct('pause', ${n})`)
      : f.status === "paused" ? iconBtn("play_arrow", "Resume sharing", `shareAct('resume', ${n})`)
      : `<span class="w-8 h-8"></span>`;
    return `<tr class="hover:bg-surface-container-high/40 transition-colors">
      <td class="py-space-md px-space-lg"><div class="flex items-center gap-space-md min-w-0"><div class="w-9 h-9 rounded-lg bg-surface-container-high flex items-center justify-center ${col} flex-shrink-0">${icon(ic, "text-[20px]")}</div><span class="font-headline-md text-[15px] text-primary font-medium truncate max-w-[420px]" title="${esc(f.name)}">${esc(f.name)}</span></div></td>
      <td class="py-space-md px-space-md font-label-md text-label-md text-on-surface whitespace-nowrap">${fmtBytes(f.size)}</td>
      <td class="py-space-md px-space-md whitespace-nowrap">${status}</td>
      <td class="py-space-md px-space-md text-right whitespace-nowrap font-label-md text-label-md ${f.up_rate > 0 ? "text-secondary font-bold" : "text-on-surface-variant"}">${fmtRate(f.up_rate)}</td>
      <td class="py-space-md px-space-lg text-center whitespace-nowrap"><div class="flex items-center justify-center gap-space-xs">${toggle}${iconBtn("delete", "Delete file from shared folder", `deleteFile(${n})`, "text-error hover:bg-error-container/30")}</div></td>
    </tr>`;
  }).join("");
  const emptyShared = `<tr><td colspan="5" class="px-space-lg py-space-xl text-center text-on-surface-variant font-body-md">
      ${c.shared.length ? "No files match your search." : `Your shared folder is empty. Copy files into <span class="font-label-md text-primary">${esc(c.folder)}</span> or press <b>Add File</b>.`}</td></tr>`;
  const sharedPane = `<div class="bg-surface-container-lowest rounded-xl shadow-md overflow-hidden">
    <div class="px-space-lg py-space-md bg-surface-container-low flex flex-wrap items-center justify-between gap-space-sm">
      <div class="flex items-center gap-space-sm">${icon("folder_shared", "text-secondary text-[20px]")}<h2 class="font-headline-md text-headline-md text-primary font-medium tracking-tight">Shared Seed Files</h2></div>
      <div class="flex items-center gap-space-md"><button class="font-label-sm text-label-sm text-primary-container hover:underline truncate max-w-[340px]" title="Open in file manager" onclick="openFolder()">${icon("folder", "text-[14px] align-middle")} ${esc(c.folder)}</button><span class="font-label-sm text-label-sm text-outline whitespace-nowrap">${seedingCount} Files Active • ${fmtBytes(totalSize)} Total</span></div>
    </div>
    <div class="overflow-x-auto"><table class="w-full text-left">
      <thead class="bg-surface-container-lowest text-outline font-label-sm text-label-sm uppercase tracking-wider"><tr><th class="py-space-md px-space-lg">File Name</th><th class="py-space-md px-space-md">Size</th><th class="py-space-md px-space-md">Status</th><th class="py-space-md px-space-md text-right">Upload Speed</th><th class="py-space-md px-space-lg text-center">Actions</th></tr></thead>
      <tbody class="font-body-sm text-body-sm">${sharedRows || emptyShared}</tbody></table></div></div>`;

  // --- available files list
  const availRows = avail.map((f) => {
    const [ic, col] = fileIcon(f.name);
    const red = f.health === "slow" || f.health === "unavailable";
    const amber = f.health === "low";
    const healthChip = f.health === "unavailable" ? chip("Unavailable", "bg-error-container/30 text-error", "bg-error")
      : f.health === "slow" ? chip("Slow", "bg-error-container/30 text-error", "bg-error", true)
      : amber ? chip("1 Source", "bg-tertiary-container/10 text-tertiary-fixed-dim", "bg-tertiary-fixed-dim")
      : chip("Healthy", "bg-secondary-container/20 text-secondary", "bg-secondary");
    let btn;
    if (f.download_status === "downloading" || f.download_status === "starting") btn = `<button class="btn-ghost" onclick="setTab('seeding');document.getElementById('transfers').scrollIntoView({behavior:'smooth'})">${icon("progress_activity", "text-[16px] animate-spin")}${Math.round(f.progress * 100)}%</button>`;
    else if (f.download_status === "paused" || f.download_status === "stalled") btn = `<button class="btn-primary" onclick="dlAct('resume','${f.file_id}')">${icon("play_arrow", "text-[16px]")}Resume</button>`;
    else btn = `<button class="${red ? "btn-danger" : "btn-primary"}" onclick="startDl('${f.file_id}')">${icon("download", "text-[16px]")}${f.health === "unavailable" ? "Try anyway" : "Download"}</button>`;
    return `<div class="relative p-space-lg hover:bg-surface-container-high/30 transition-all flex flex-col md:flex-row md:items-center justify-between gap-space-md ${red ? "bg-error-container/[0.07]" : ""}">
      ${red ? `<div class="absolute left-0 top-0 bottom-0 w-[3px] bg-error"></div>` : ""}
      <div class="flex items-center gap-space-md min-w-0">
        <div class="w-10 h-10 rounded-xl bg-surface-container-high flex items-center justify-center ${red ? "text-error" : col} flex-shrink-0">${icon(ic, "text-[20px]")}</div>
        <div class="flex flex-col min-w-0">
          <div class="flex items-center gap-space-sm min-w-0"><span class="font-headline-md text-[15px] ${red ? "text-error" : "text-primary"} font-medium truncate" title="${esc(f.name)}">${esc(f.name)}</span>${healthChip}</div>
          <div class="flex flex-wrap items-center gap-space-sm font-label-sm text-label-sm text-on-surface-variant mt-0.5">
            <span>${fmtBytes(f.size)}</span><span>•</span><span class="${f.seeders ? "text-secondary" : "text-error"}">${f.seeders} Seeder${f.seeders === 1 ? "" : "s"}</span><span>•</span><span class="text-tertiary-fixed-dim">${f.leechers} Leecher${f.leechers === 1 ? "" : "s"}</span><span>•</span><span class="${red ? "text-error" : amber ? "text-tertiary-fixed-dim" : "text-outline"}">${esc(f.health_reason)}</span>
          </div>
        </div>
      </div>
      <div class="self-end md:self-center">${btn}</div>
    </div>`;
  }).join("");
  const emptyAvail = `<div class="px-space-lg py-space-xl text-center text-on-surface-variant font-body-md">${c.available.length ? "No files match your search." : "No other files in the swarm yet. When another device shares files they appear here."}</div>`;
  const availPane = `<div class="bg-surface-container-lowest rounded-xl shadow-md overflow-hidden">
    <div class="px-space-lg py-space-md bg-surface-container-low flex items-center justify-between">
      <div class="flex items-center gap-space-sm">${icon("cloud_download", "text-primary-container text-[20px]")}<h2 class="font-headline-md text-headline-md text-primary font-medium tracking-tight">Available Files to Download</h2></div>
      <span class="font-label-sm text-label-sm text-outline">${c.available.length} Files Found on Swarm</span></div>
    <div class="flex flex-col divide-y divide-white/[0.03] font-body-sm text-body-sm">${availRows || emptyAvail}</div></div>`;

  // --- transfers
  const tRows = c.downloads.map((d) => {
    const pct = Math.round(d.progress * 100);
    const red = d.status === "stalled" || d.status === "failed" || (d.status === "downloading" && (d.health === "slow" || d.health === "unavailable"));
    let status;
    if (d.status === "done") status = chip("Complete • Seeding", "bg-secondary-container/20 text-secondary", "bg-secondary");
    else if (d.status === "paused") status = chip("Paused", "bg-surface-container-highest text-on-surface-variant", "bg-outline");
    else if (d.status === "stalled") status = chip("Stalled", "bg-error-container/30 text-error", "bg-error");
    else if (d.status === "failed") status = chip("Failed", "bg-error-container/30 text-error", "bg-error");
    else if (d.status === "starting") status = chip("Connecting swarm", "bg-primary-container/10 text-primary-container", "bg-primary-container", true);
    else if (red) status = chip("Slow • " + fmtRate(d.rate), "bg-error-container/30 text-error", "bg-error", true);
    else status = chip("Downloading • " + fmtRate(d.rate), "bg-primary-container/10 text-primary-container", "bg-primary-container", true);
    const id = `'${d.file_id}'`;
    let actions = "";
    if (d.status === "downloading" || d.status === "starting") actions = iconBtn("pause", "Pause", `dlAct('pause',${id})`);
    else if (d.status === "paused" || d.status === "stalled" || d.status === "failed") actions = iconBtn(d.status === "paused" ? "play_arrow" : "refresh", d.status === "paused" ? "Resume" : "Retry", `dlAct('resume',${id})`);
    if (d.status !== "done") actions += iconBtn("close", "Cancel and delete partial data", `cancelDl(${id}, ${esc(JSON.stringify(d.name))})`, "text-error hover:bg-error-container/30");
    const detail = d.status === "done" ? esc(d.message)
      : d.status === "downloading" ? `${d.chunks_done}/${d.chunks_total} chunks • ETA ${fmtDuration(d.eta)}${d.hash_failures ? ` • <span class="text-tertiary-fixed-dim">${d.hash_failures} bad chunk(s) rejected</span>` : ""}${red ? ` • <span class="text-error">${esc(d.health_reason)}</span>` : ""}`
      : esc(d.message || `${d.chunks_done}/${d.chunks_total} chunks`);
    return `<div class="relative px-space-lg py-space-md flex flex-col gap-space-sm ${red ? "bg-error-container/[0.07]" : ""}">
      ${red ? `<div class="absolute left-0 top-0 bottom-0 w-[3px] bg-error"></div>` : ""}
      <div class="flex flex-wrap items-center justify-between gap-space-sm">
        <div class="flex items-center gap-space-sm min-w-0">${icon(fileIcon(d.name)[0], "text-[18px] " + (red ? "text-error" : "text-primary-container"))}<span class="font-headline-md text-[15px] ${red ? "text-error" : "text-primary"} truncate max-w-[420px]">${esc(d.name)}</span><span class="font-label-sm text-label-sm text-outline">${fmtBytes(d.size)}</span></div>
        <div class="flex items-center gap-space-sm">${status}<span class="font-label-md text-label-md ${red ? "text-error" : "text-primary"} w-12 text-right">${pct}%</span>${actions}</div>
      </div>
      <div class="h-1.5 w-full bg-[#1e293b] rounded-sm overflow-hidden"><div class="h-full ${d.status === "done" ? "bg-secondary" : red ? "bg-error" : "bg-gradient-to-r from-secondary to-primary-container"} transition-all duration-700" style="width:${pct}%"></div></div>
      <div class="font-label-sm text-label-sm text-on-surface-variant">${detail}</div>
    </div>`;
  }).join("");
  const hasDone = c.downloads.some((d) => d.status === "done");
  const transfers = c.downloads.length ? `<div id="transfers" class="bg-surface-container-lowest rounded-xl shadow-md overflow-hidden">
    <div class="px-space-lg py-space-md bg-surface-container-low flex items-center justify-between">
      <div class="flex items-center gap-space-sm">${icon("swap_vert", "text-primary-container text-[20px]")}<h2 class="font-headline-md text-headline-md text-primary font-medium tracking-tight">Active Transfers</h2></div>
      ${hasDone ? `<button class="font-label-sm text-label-sm text-outline hover:text-primary" onclick="dlAct('clear','')">Clear finished</button>` : ""}</div>
    <div class="flex flex-col divide-y divide-white/[0.03]">${tRows}</div></div>` : `<div id="transfers"></div>`;

  const html = `<div class="flex flex-col w-full gap-space-lg">
    ${banner}
    <section class="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-4 gap-space-md">
      ${statTile("Download Speed", dv, du, "Peak: " + fmtRate(st.peak_down), "text-on-surface-variant", "arrow_downward", "text-primary-container")}
      ${statTile("Upload Speed", uv, uu, "Total sent: " + fmtBytes(st.uploaded), "text-on-surface-variant", "arrow_upward", "text-secondary", "text-secondary", "text-secondary-fixed-dim font-mono")}
      ${statTile("Seeders", st.seeders, "Active", `<span class="flex items-center gap-1 ${anyRed ? "text-error" : anyWeak ? "text-tertiary-fixed-dim" : "text-secondary"}"><span class="w-1.5 h-1.5 rounded-full ${anyRed ? "bg-error" : anyWeak ? "bg-tertiary-fixed-dim" : "bg-secondary"}"></span>${anyRed ? "Some files are slow" : anyWeak ? "Some have 1 source" : "Healthy Swarm"}</span>`, "", "hub", "text-secondary", "text-on-surface", "text-on-surface-variant")}
      ${statTile("Leechers", st.leechers, "Peers", `${st.requesting} file(s) being requested`, "text-tertiary-fixed-dim", "group", "text-tertiary-fixed-dim", "text-on-surface", "text-on-surface-variant")}
    </section>
    <div class="flex flex-wrap items-center justify-between gap-space-md mt-space-sm">
      <div class="flex items-center bg-surface-container-lowest p-space-xs rounded-xl shadow-sm">
        ${tabBtn("seeding", "cloud_upload", "My Shared Files (Seeding)", c.shared.length, "bg-secondary-container text-on-secondary-container")}
        ${tabBtn("swarm", "cloud_download", "Available to Download", c.available.length, anyRed ? "bg-error-container text-on-error-container" : "bg-surface-container-highest text-on-surface-variant")}
      </div>
      <div class="flex items-center gap-space-sm" id="clientTools"></div>
    </div>
    ${S.tab === "seeding" ? sharedPane : availPane}
    ${transfers}
  </div>`;
  setHTML(el, html);
  ensureClientTools();
}
function ensureClientTools() {  // the search box lives outside re-rendered HTML so typing is never interrupted
  const slot = $("#clientTools");
  if (!slot) return;
  let tools = document.getElementById("clientToolsInner");
  if (!tools) {
    tools = document.createElement("div");
    tools.id = "clientToolsInner";
    tools.className = "flex items-center gap-space-sm";
    tools.innerHTML = `<div class="relative"><input class="bg-surface-container-lowest text-on-surface placeholder:text-outline font-body-sm text-body-sm pl-8 pr-3 py-2 rounded-lg focus:outline-none focus:ring-1 focus:ring-primary-container w-56 lg:w-64 transition-all shadow-sm" id="filterInput" placeholder="Search files..." type="text">${icon("search", "text-outline text-[16px] absolute left-2.5 top-2.5")}</div>
      <button class="flex items-center gap-space-xs px-space-md py-2 rounded-lg bg-primary-container text-on-primary-container font-label-md text-label-md font-bold hover:brightness-110 active:scale-[0.98] transition-all shadow-sm" onclick="addFileModal()">${icon("add")}<span>Add File</span></button>`;
    tools.querySelector("#filterInput").oninput = (e) => { S.filter = e.target.value; render(); };
  }
  if (tools.parentElement !== slot) slot.appendChild(tools);
}
window.setTab = (t) => { S.tab = t; render(); };
window.startDl = (id) => act(() => api("/api/client/download", { file_id: id }), "Download started");
window.dlAct = (a, id) => act(() => api("/api/client/download/" + a, { file_id: id }));
window.cancelDl = (id, name) => confirmBox({ title: "Cancel download?", text: `Stop downloading <b>${esc(name)}</b> and delete the partial data?`, okLabel: "Cancel download", danger: true, onOk: () => dlAct("cancel", id) });
window.shareAct = (a, name) => act(() => api("/api/client/share/" + a, { name }), a === "pause" ? "Stopped sharing " + name : "Sharing " + name + " again");
window.deleteFile = (name) => confirmBox({ title: "Delete file?", text: `This deletes <b>${esc(name)}</b> from your shared folder on disk. Other devices will stop seeing it from you.`, okLabel: "Delete from disk", danger: true, onOk: () => shareAct("delete", name) });
window.openFolder = () => act(() => api("/api/client/open-folder", {}));
window.addFileModal = () => {
  openModal(`${modalHead("Add a file to your shared folder", "upload_file")}
    <div class="p-space-lg flex flex-col gap-space-md">
      <label id="drop" class="flex flex-col items-center justify-center gap-space-sm p-space-xl rounded-lg border border-dashed border-primary-container/40 bg-primary-container/5 cursor-pointer hover:bg-primary-container/10 transition-colors text-center">
        ${icon("cloud_upload", "text-[36px] text-primary-container")}
        <span class="font-body-md text-on-surface">Drop files here or click to choose</span>
        <span class="font-label-sm text-label-sm text-outline">They are copied into ${esc(S.data.client.folder)} and shared automatically.</span>
        <input type="file" id="fileIn" class="hidden" multiple>
      </label>
      <div id="upStatus" class="font-label-md text-label-md text-on-surface-variant"></div>
      <p class="font-body-sm text-body-sm text-outline">Tip: you can also copy files into the folder with your file manager. New files are picked up within a few seconds.</p>
    </div>
    <div class="flex justify-between gap-space-sm px-space-lg pb-space-lg">
      <button class="btn-ghost" onclick="openFolder()">${icon("folder_open", "text-[16px]")}Open folder</button>
      <button class="btn-ghost" onclick="closeModal()">Close</button>
    </div>`, (box) => {
    const upload = async (files) => {
      for (const f of files) {
        box.querySelector("#upStatus").innerHTML = icon("progress_activity", "text-[14px] animate-spin align-middle") + " Copying " + esc(f.name) + " (" + fmtBytes(f.size) + ")...";
        try {
          const r = await api("/api/client/upload?name=" + encodeURIComponent(f.name), undefined, { method: "POST", raw: f });
          toast("Added " + r.name + ". Hashing and seeding...", "ok");
        } catch (e) { toast(e.message, "err"); }
      }
      box.querySelector("#upStatus").textContent = "";
      closeModal();
      S.tab = "seeding";
      refresh();
    };
    box.querySelector("#fileIn").onchange = (e) => upload([...e.target.files]);
    const drop = box.querySelector("#drop");
    drop.ondragover = (e) => { e.preventDefault(); drop.classList.add("bg-primary-container/20"); };
    drop.ondragleave = () => drop.classList.remove("bg-primary-container/20");
    drop.ondrop = (e) => { e.preventDefault(); upload([...e.dataTransfer.files]); };
  });
};

// ------------------------------------------------------------------ SERVER: host form
function renderHost(el) {
  const d = S.data;
  if (S.hostPort == null) S.hostPort = d.default_tracker_port;
  const html = `<div class="max-w-3xl mx-auto flex flex-col gap-space-lg intro-fast">
    <div class="flex items-center gap-space-md">
      <div class="w-12 h-12 rounded-xl bg-secondary-container/10 flex items-center justify-center text-secondary">${icon("dns", "text-[24px]")}</div>
      <div><h1 class="font-headline-lg text-headline-lg text-primary">Host a Tracker Server</h1>
      <p class="font-body-sm text-body-sm text-on-surface-variant">The server keeps the list of devices and files. It never stores or sends the files themselves.</p></div>
    </div>
    <div class="bg-surface-container-lowest rounded-xl shadow-md p-space-lg flex flex-col gap-space-md">
      <div class="grid grid-cols-1 sm:grid-cols-[1fr_160px] gap-space-md items-end">
        <div class="flex flex-col gap-space-xs"><span class="field-label">This PC</span><div class="input flex items-center gap-space-sm">${icon("computer", "text-[16px] text-outline")}${esc(d.device_name)} <span class="text-outline">•</span> ${esc(d.lan_ip)}</div></div>
        <label class="flex flex-col gap-space-xs"><span class="field-label">Port</span><input id="hPort" class="input" value="${esc(S.hostPort)}" inputmode="numeric"></label>
      </div>
      <div class="flex justify-end"><button class="btn-secondary" id="hStart">${icon("play_arrow", "text-[18px]")}Start hosting</button></div>
    </div>
    ${howHostingWorks(d.lan_ip, S.hostPort)}
  </div>`;
  setHTML(el, html);
  $("#hPort").oninput = (e) => { S.hostPort = e.target.value; };
  $("#hStart").onclick = () => act(() => api("/api/server/start", { port: S.hostPort }), (r) => "Hosting on port " + r.port);
}
function howHostingWorks(ip, port) {
  return `<div class="bg-surface-container-lowest rounded-xl shadow-md overflow-hidden">
    <div class="px-space-lg py-space-md bg-surface-container-low flex items-center gap-space-sm">${icon("info", "text-primary-container text-[20px]")}<h2 class="font-headline-md text-headline-md text-primary">How the address works</h2></div>
    <div class="p-space-lg grid grid-cols-1 md:grid-cols-3 gap-space-md font-body-sm text-body-sm text-on-surface-variant">
      <div class="p-space-md rounded-lg bg-surface-container"><div class="font-label-md text-label-md text-primary mb-1">Same PC</div><code class="font-label-md text-primary-container">127.0.0.1:${esc(port)}</code><p class="mt-1">"localhost". Only clients on this computer can use it. Good for testing with several windows.</p></div>
      <div class="p-space-md rounded-lg bg-surface-container"><div class="font-label-md text-label-md text-secondary mb-1">Same Wi-Fi / LAN</div><code class="font-label-md text-secondary">${esc(ip)}:${esc(port)}</code><p class="mt-1">Share this with friends on the same network. Allow the port in your firewall when Windows asks.</p></div>
      <div class="p-space-md rounded-lg bg-surface-container"><div class="font-label-md text-label-md text-tertiary-fixed-dim mb-1">Over the internet</div><code class="font-label-md text-tertiary-fixed-dim">needs a VPN</code><p class="mt-1">A LAN address does not work from outside. Use Tailscale/ZeroTier, or port forwarding on your router.</p></div>
    </div></div>`;
}

// ------------------------------------------------------------------ SERVER: tracker node
function renderServer(el) {
  const s = S.data.server;
  if (!s) return renderHost(el);
  S.hostPort = null;
  const devs = s.devices;
  if (!S.selectedDevice || !devs.find((x) => x.key === S.selectedDevice)) S.selectedDevice = devs.length ? devs[0].key : null;
  const sel = devs.find((x) => x.key === S.selectedDevice);
  const q = S.devFilter.toLowerCase();
  const shown = devs.filter((x) => (x.name + " " + x.ip + " " + x.lan_ip).toLowerCase().includes(q));
  const [av, au] = rateParts(s.stats.activity);
  const allOnline = s.stats.devices && s.stats.devices_online === s.stats.devices;

  const devIcon = (d) => d.os === "Windows" ? "desktop_windows" : d.os === "Darwin" ? "laptop_mac" : d.os === "cli" ? "terminal" : "computer";
  const deviceCards = shown.map((d) => {
    const on = d.key === S.selectedDevice;
    const ipText = d.ip === "127.0.0.1" ? `${d.lan_ip} (this PC)` : d.ip;
    return `<div class="group relative p-space-md bg-surface-container rounded-lg cursor-pointer transition-all hover:bg-surface-container-high ${on ? "bg-surface-container-high" : ""}" onclick="selectDevice('${esc(d.key)}')">
      <div class="absolute left-0 top-0 bottom-0 w-1 ${on ? "bg-primary-container" : "bg-transparent group-hover:bg-outline"} rounded-l-lg"></div>
      <div class="flex items-center justify-between gap-space-sm">
        <div class="flex items-center gap-space-sm min-w-0">
          <div class="w-8 h-8 rounded-lg bg-surface-container-highest flex items-center justify-center flex-shrink-0">${icon(devIcon(d), "text-[18px] " + (d.online ? "text-primary" : "text-outline"))}</div>
          <div class="flex flex-col min-w-0"><span class="font-headline-md text-sm ${d.online ? "text-on-background" : "text-outline"} group-hover:text-primary truncate">${esc(d.name)}</span><span class="font-label-sm text-label-sm text-outline">${esc(ipText)} • ${d.files.length} file${d.files.length === 1 ? "" : "s"}</span></div>
        </div>
        ${d.online ? `<span class="px-space-xs py-0.5 rounded font-label-sm text-label-sm bg-secondary-container/20 text-secondary flex items-center gap-1"><span class="w-1.5 h-1.5 rounded-full bg-secondary-fixed-dim animate-pulse"></span>Online</span>`
          : `<span class="px-space-xs py-0.5 rounded font-label-sm text-label-sm bg-surface-container-highest text-outline flex items-center gap-1"><span class="w-1.5 h-1.5 rounded-full bg-outline"></span>Offline</span>`}
      </div></div>`;
  }).join("") || `<div class="p-space-lg text-center text-on-surface-variant font-body-sm">${devs.length ? "No devices match." : `No devices yet. Ask your friends to open <b>Client Mode</b> and connect to <span class="text-primary-container font-label-md">${esc(s.share_url)}</span>.`}</div>`;

  let detail;
  if (!sel) {
    detail = `<div class="bg-surface-container-lowest rounded-xl p-space-xl shadow-lg flex flex-col items-center justify-center text-center gap-space-md min-h-[300px]">
      ${icon("devices_other", "text-[48px] text-outline")}<div class="font-headline-md text-headline-md text-primary">Waiting for devices</div>
      <p class="font-body-sm text-body-sm text-on-surface-variant max-w-sm">When a client connects, its PC name, IP address and the files in its shared folder appear here.</p></div>`;
  } else {
    const rows = sel.files.map((f) => {
      const [ic, col] = fileIcon(f.name);
      const st = f.complete ? `<span class="flex items-center gap-1 text-secondary">${icon("group", "text-[14px]")}${f.seeders} seed${f.seeders === 1 ? "" : "s"}${f.leechers ? ` • ${f.leechers} leech` : ""}</span>`
        : `<span class="flex items-center gap-1 text-primary-container">${icon("downloading", "text-[14px]")}downloading ${Math.round((100 * f.chunks_held) / Math.max(1, f.num_chunks))}%</span>`;
      return `<tr class="hover:bg-surface-container-high/40 transition-colors">
        <td class="py-space-sm px-space-md"><div class="flex items-center gap-space-sm min-w-0">${icon(ic, "text-[18px] " + col)}<span class="font-label-md text-label-md text-on-surface truncate max-w-[260px]" title="${esc(f.name)}">${esc(f.name)}</span></div></td>
        <td class="py-space-sm px-space-md font-label-md text-label-md text-on-surface whitespace-nowrap">${fmtBytes(f.size)}</td>
        <td class="py-space-sm px-space-md font-label-sm text-label-sm whitespace-nowrap">${st}</td>
        <td class="py-space-sm px-space-md text-right"><button class="text-on-surface-variant hover:text-primary-container" title="Who has this file" onclick="fileDetail('${f.file_id}')">${icon("visibility", "text-[18px]")}</button></td></tr>`;
    }).join("") || `<tr><td colspan="4" class="px-space-md py-space-lg text-center text-on-surface-variant">This device is not sharing any files.</td></tr>`;
    detail = `<div class="flex flex-col gap-space-lg">
      <div class="bg-surface-container-lowest rounded-xl p-space-lg shadow-lg">
        <div class="flex flex-wrap items-start justify-between gap-space-md">
          <div class="flex flex-col gap-1 min-w-0">
            <div class="flex flex-wrap items-center gap-space-sm">${icon(devIcon(sel), "text-[22px] text-primary-container")}<span class="font-headline-lg text-headline-lg text-primary truncate">${esc(sel.name)}</span><span class="px-space-sm py-0.5 rounded bg-surface-container-high font-label-sm text-label-sm text-on-surface">${esc(sel.ip)}</span></div>
            <span class="font-body-sm text-body-sm text-on-surface-variant">Files currently shared by this device.</span>
          </div>
          ${sel.online ? `<button class="flex items-center gap-space-xs px-space-md py-space-xs rounded-lg bg-error-container/30 text-error hover:bg-error-container/50 font-label-md text-label-md transition-colors" onclick="kick('${esc(sel.key)}', ${esc(JSON.stringify(sel.name))})">${icon("link_off", "text-[16px]")}Disconnect</button>` : ""}
        </div>
        <div class="grid grid-cols-2 lg:grid-cols-4 gap-space-md mt-space-lg pt-space-md border-t border-white/5">
          ${kvBlock("PC Name", sel.name)}${kvBlock("IP Address", sel.ip === "127.0.0.1" ? sel.lan_ip + " (local)" : sel.ip)}${kvBlock("Peer Port", sel.port)}${kvBlock("OS", sel.os || "—")}
        </div>
        <div class="grid grid-cols-2 gap-space-md mt-space-md">
          <div><span class="font-label-sm text-label-sm text-outline uppercase">Shared Files</span><div class="font-headline-lg text-headline-lg text-primary-container">${sel.shared_count} Files</div></div>
          <div><span class="font-label-sm text-label-sm text-outline uppercase">Total Size</span><div class="font-headline-lg text-headline-lg text-on-background">${fmtBytes(sel.total_size)}</div></div>
        </div>
        <div class="mt-space-sm font-label-sm text-label-sm text-outline">Connected ${fmtAgo(sel.first_seen)} • last heartbeat ${sel.seconds_ago}s ago • ↑ ${fmtRate(sel.up_rate)} ↓ ${fmtRate(sel.down_rate)}</div>
      </div>
      <div class="bg-surface-container-lowest rounded-xl p-space-lg shadow-lg">
        <div class="flex items-center gap-space-sm mb-space-md"><span class="font-headline-md text-headline-md text-primary">Shared Files</span><span class="font-label-sm text-label-sm text-outline">${sel.files.length} files shown</span></div>
        <div class="rounded-lg overflow-hidden bg-surface-container"><table class="w-full text-left">
          <thead class="bg-surface-container-high text-outline font-label-sm text-label-sm uppercase tracking-wider"><tr><th class="py-space-sm px-space-md">File Name</th><th class="py-space-sm px-space-md">Size</th><th class="py-space-sm px-space-md">Status</th><th class="py-space-sm px-space-md text-right">Action</th></tr></thead>
          <tbody>${rows}</tbody></table></div>
      </div></div>`;
  }

  const html = `<div class="flex flex-col w-full gap-space-lg">
    <div class="relative bg-surface-container-lowest rounded-xl p-space-lg shadow-xl overflow-hidden">
      <div class="absolute -right-20 -top-20 w-80 h-80 rounded-full bg-gradient-to-br from-primary-container/10 via-secondary-fixed-dim/5 to-transparent blur-3xl pointer-events-none"></div>
      <div class="relative flex flex-col lg:flex-row lg:items-center justify-between gap-space-md">
        <div class="flex items-center gap-space-md min-w-0">
          <div class="w-12 h-12 rounded-xl bg-surface-container-high flex items-center justify-center relative shadow-inner flex-shrink-0">${icon("dns", "text-primary-container text-[24px]")}<span class="absolute top-1 right-1 w-2.5 h-2.5 rounded-full bg-secondary-fixed-dim animate-ping"></span><span class="absolute top-1 right-1 w-2.5 h-2.5 rounded-full bg-secondary-fixed-dim"></span></div>
          <div class="flex flex-col min-w-0">
            <div class="flex flex-wrap items-center gap-space-sm"><span class="font-headline-lg text-headline-lg text-primary tracking-tight">Tracker Swarm Node</span><span class="px-space-xs py-0.5 rounded bg-surface-container-high font-label-sm text-label-sm text-secondary uppercase tracking-wider">v${esc(s.version)}</span><span class="px-space-xs py-0.5 rounded bg-secondary-container/20 font-label-sm text-label-sm text-secondary uppercase tracking-widest font-semibold">Hosting</span></div>
            <span class="font-label-md text-label-md text-outline flex flex-wrap items-center gap-x-space-sm">Share this address:
              <button class="text-secondary hover:underline flex items-center gap-1" onclick="copy('${esc(s.share_url)}')" title="Copy">${esc(s.share_url)}${icon("content_copy", "text-[14px]")}</button>
              <span class="text-outline-variant">|</span> same PC: <button class="text-on-surface-variant hover:underline flex items-center gap-1" onclick="copy('${esc(s.local_url)}')">${esc(s.local_url)}${icon("content_copy", "text-[14px]")}</button></span>
          </div>
        </div>
        <div class="flex items-center gap-space-sm flex-wrap">
          <button class="flex items-center gap-space-xs px-space-md py-space-xs rounded-lg bg-surface-container-high hover:bg-surface-bright text-on-surface transition-all text-label-md font-label-md" onclick="refreshSwarm(this)">${icon("sync", "text-[16px] text-primary-container")}Refresh Swarm</button>
          <a class="flex items-center gap-space-xs px-space-md py-space-xs rounded-lg bg-primary-container/15 hover:bg-primary-container/25 text-primary-fixed-dim shadow-sm transition-all text-label-md font-label-md" href="/api/server/export?fmt=csv">${icon("file_download", "text-[16px]")}Export List</a>
          <button class="flex items-center gap-space-xs px-space-md py-space-xs rounded-lg bg-error-container/20 hover:bg-error-container/40 text-error transition-all text-label-md font-label-md" onclick="stopServer()">${icon("stop_circle", "text-[16px]")}Stop</button>
        </div>
      </div>
      <div class="relative grid grid-cols-1 sm:grid-cols-3 gap-space-md mt-space-lg">
        <div class="p-space-md bg-surface-container rounded-lg flex flex-col justify-between"><span class="font-label-sm text-label-sm text-outline uppercase">Connected Devices</span><div class="flex items-baseline gap-space-xs mt-space-xs"><span class="font-headline-xl text-headline-xl text-primary font-bold">${s.stats.devices_online}</span><span class="font-label-sm text-label-sm ${allOnline ? "text-secondary" : "text-outline"}">${!s.stats.devices ? "Waiting" : allOnline ? "All Online" : (s.stats.devices - s.stats.devices_online) + " Offline"}</span></div></div>
        <div class="p-space-md bg-surface-container rounded-lg flex flex-col justify-between"><span class="font-label-sm text-label-sm text-outline uppercase">Total Shared Files</span><div class="flex items-baseline gap-space-xs mt-space-xs"><span class="font-headline-xl text-headline-xl text-on-background font-bold">${s.stats.files}</span><span class="font-label-sm text-label-sm text-outline">files</span></div></div>
        <div class="p-space-md bg-surface-container rounded-lg flex flex-col justify-between"><span class="font-label-sm text-label-sm text-outline uppercase">Network Activity</span><div class="flex items-baseline gap-space-xs mt-space-xs"><span class="font-headline-xl text-headline-xl text-primary-container font-bold">${av}</span><span class="font-label-sm text-label-sm text-primary">${au} aggregate</span></div></div>
      </div>
    </div>
    <div class="grid grid-cols-1 xl:grid-cols-12 gap-space-lg items-start">
      <div class="xl:col-span-5 bg-surface-container-lowest rounded-xl p-space-md flex flex-col gap-space-md shadow-lg">
        <div class="flex items-center justify-between px-space-xs"><div class="flex items-center gap-space-sm">${icon("devices", "text-primary text-[20px]")}<span class="font-headline-md text-headline-md text-primary">Connected Devices</span><span class="px-space-xs py-0.5 rounded-full bg-surface-container-high font-label-sm text-label-sm text-primary-fixed-dim">${devs.length}</span></div></div>
        <div id="devSearchSlot"></div>
        <div class="flex flex-col gap-space-xs max-h-[720px] overflow-y-auto pr-1">${deviceCards}</div>
      </div>
      <div class="xl:col-span-7">${detail}</div>
    </div>
  </div>`;
  setHTML(el, html);
  let box = document.getElementById("devSearchBox");
  if (!box) {
    box = document.createElement("div");
    box.id = "devSearchBox";
    box.className = "relative w-full";
    box.innerHTML = `${icon("search", "absolute left-3 top-2.5 text-outline text-[16px]")}<input class="w-full bg-surface-container-low pl-9 pr-space-md py-1.5 rounded-lg text-body-sm font-body-sm text-on-surface placeholder:text-outline focus:outline-none focus:ring-1 focus:ring-primary-container" placeholder="Search devices..." type="text">`;
    box.querySelector("input").oninput = (e) => { S.devFilter = e.target.value; render(); };
  }
  const slot = $("#devSearchSlot");
  if (slot && box.parentElement !== slot) slot.appendChild(box);
}
const kvBlock = (k, v) => `<div class="min-w-0"><div class="font-label-sm text-label-sm text-outline uppercase">${k}</div><div class="font-label-lg text-label-lg text-on-surface truncate">${esc(v)}</div></div>`;
window.selectDevice = (k) => { S.selectedDevice = k; render(); };
window.copy = async (text) => {
  try { await navigator.clipboard.writeText(text); toast("Copied " + text, "ok"); }
  catch (e) { toast("Copy this address: " + text, "info"); }
};
window.refreshSwarm = async (btn) => {
  btn.querySelector(".material-symbols-outlined").classList.add("animate-spin");
  await refresh();
  setTimeout(() => toast("Swarm list refreshed", "ok"), 300);
};
window.kick = (key, name) => confirmBox({ title: "Disconnect device?", text: `<b>${esc(name)}</b> is removed from the swarm and cannot reconnect for 60 seconds. Its files disappear from the list.`, okLabel: "Disconnect", danger: true, onOk: () => act(() => api("/api/server/kick", { key }), name + " disconnected") });
window.stopServer = () => confirmBox({ title: "Stop hosting?", text: "Every connected device loses the server. They will keep retrying until you host again on the same port.", okLabel: "Stop server", danger: true, onOk: () => act(() => api("/api/server/stop", {}), "Server stopped") });
window.fileDetail = (fid) => {
  const s = S.data.server;
  const f = s.files.find((x) => x.file_id === fid);
  if (!f) return toast("File is no longer in the swarm", "warn");
  const holders = s.devices.filter((d) => d.files.some((x) => x.file_id === fid));
  const rows = holders.map((d) => {
    const x = d.files.find((y) => y.file_id === fid);
    const pct = Math.round((100 * x.chunks_held) / Math.max(1, x.num_chunks));
    return `<div class="flex items-center justify-between gap-space-sm py-space-sm border-b border-white/5"><div class="flex flex-col"><span class="font-body-md text-on-surface">${esc(d.name)}</span><span class="font-label-sm text-label-sm text-outline">${esc(d.key)}</span></div><span class="font-label-md text-label-md ${x.complete ? "text-secondary" : "text-primary-container"}">${x.complete ? "Seeder" : "Leecher " + pct + "%"}</span></div>`;
  }).join("");
  openModal(`${modalHead(esc(f.name), "visibility")}
    <div class="p-space-lg flex flex-col gap-space-md overflow-y-auto">
      <div class="grid grid-cols-3 gap-space-md">${kvBlock("Size", fmtBytes(f.size))}${kvBlock("Chunks", f.num_chunks)}${kvBlock("Swarm", f.seeders + " seed / " + f.leechers + " leech")}</div>
      <div><div class="field-label mb-space-xs">Chunk availability</div>${availStrip(f)}</div>
      <div><div class="field-label mb-space-xs">Devices holding this file</div>${rows}</div>
      <div class="font-label-sm text-label-sm text-outline break-all">File id ${esc(f.file_id)}</div>
    </div>`);
};

// ------------------------------------------------------------------ TELEMETRY
const AVAIL = ["#1e293b", "#004f53", "#00a5ad", "#00f2fe"];
function availStrip(f) {
  const n = f.availability.length;
  const size = n <= 120 ? 12 : n <= 400 ? 8 : 5;
  const cells = n > 2000 ? `<div class="font-label-sm text-outline">${n} chunks (too many to draw)</div>`
    : f.availability.map((h, i) => `<div title="Chunk ${i}: ${h} holder(s)" style="width:${size}px;height:${size}px;background:${AVAIL[Math.min(h, 3)]}" class="rounded-[1px]"></div>`).join("");
  return `<div class="flex flex-wrap gap-[2px]">${cells}</div>
    <div class="flex flex-wrap gap-space-md mt-space-sm font-label-sm text-label-sm text-outline">${["0 peers", "1 peer (rare)", "2 peers", "3+ peers"].map((t, i) => `<span class="flex items-center gap-1"><i class="inline-block w-2.5 h-2.5 rounded-[1px]" style="background:${AVAIL[i]}"></i>${t}</span>`).join("")}</div>`;
}
function colorOf(key) {
  if (!S.peerColors[key]) S.peerColors[key] = PEER_COLORS[Object.keys(S.peerColors).length % PEER_COLORS.length];
  return S.peerColors[key];
}
function chunkMap(bitmap, sources, ownColor) {
  const n = bitmap.length;
  if (!n) return "";
  const size = n <= 120 ? 12 : n <= 400 ? 8 : 5;
  return `<div class="flex flex-wrap gap-[2px]">${[...bitmap].map((b, i) => {
    if (b !== "1") return `<div title="Chunk ${i}: missing" style="width:${size}px;height:${size}px" class="rounded-[1px] bg-surface-container-lowest ring-1 ring-inset ring-outline-variant"></div>`;
    const src = sources[String(i)];
    const col = src ? colorOf(src) : ownColor || "#849495";
    return `<div title="Chunk ${i}: ${src ? "from " + esc(src) : "own / resumed"}" style="width:${size}px;height:${size}px;background:${col}" class="rounded-[1px]"></div>`;
  }).join("")}</div>`;
}
function sparkline(points, key, color, h = 120) {
  if (points.length < 2) return `<div class="h-[${h}px] flex items-center justify-center text-outline font-label-sm">Collecting samples...</div>`;
  const w = 600, max = Math.max(1, ...points.map((p) => p[key]));
  const xy = points.map((p, i) => [(i / (points.length - 1)) * w, h - (p[key] / max) * (h - 8) - 4]);
  const line = xy.map((p) => p[0].toFixed(1) + "," + p[1].toFixed(1)).join(" ");
  return `<svg viewBox="0 0 ${w} ${h}" preserveAspectRatio="none" class="w-full" style="height:${h}px">
    <polygon points="0,${h} ${line} ${w},${h}" fill="${color}" fill-opacity="0.08"></polygon>
    <polyline points="${line}" fill="none" stroke="${color}" stroke-width="2" vector-effect="non-scaling-stroke"></polyline></svg>
    <div class="flex justify-between font-label-sm text-label-sm text-outline mt-1"><span>${Math.round((points[points.length - 1].t - points[0].t))}s ago</span><span>peak ${fmtRate(max)}</span><span>now ${fmtRate(points[points.length - 1][key])}</span></div>`;
}
function panel(title, ic, body, right = "") {
  return `<div class="bg-surface-container-lowest rounded-xl shadow-md overflow-hidden">
    <div class="px-space-lg py-space-md bg-surface-container-low flex items-center justify-between gap-space-sm"><div class="flex items-center gap-space-sm">${icon(ic, "text-primary-container text-[20px]")}<h2 class="font-headline-md text-headline-md text-primary">${title}</h2></div>${right}</div>
    <div class="p-space-lg">${body}</div></div>`;
}
function renderTelemetry(el) {
  const c = S.data.client, s = S.data.server;
  if (!c && !s) {
    setHTML(el, `<div class="max-w-xl mx-auto mt-space-xl text-center flex flex-col items-center gap-space-md">${icon("query_stats", "text-[48px] text-outline")}<div class="font-headline-md text-headline-md text-primary">Nothing to measure yet</div><p class="text-on-surface-variant">Start Client or Server mode first.</p><a class="btn-primary" href="#/">Choose a mode</a></div>`);
    return;
  }
  const parts = [];
  if (c) {
    parts.push(`<div class="grid grid-cols-1 lg:grid-cols-2 gap-space-lg">
      ${panel("Download Speed (this PC)", "arrow_downward", sparkline(c.history, "down", "#00f2fe"))}
      ${panel("Upload Speed (this PC)", "arrow_upward", sparkline(c.history, "up", "#4edea3"))}</div>`);
    const active = c.downloads.filter((d) => d.bitmap);
    if (active.length) {
      parts.push(panel("My Downloads • chunk map", "grid_view", active.map((d) => {
        const counts = {};
        Object.values(d.sources).forEach((v) => (counts[v] = (counts[v] || 0) + 1));
        const legend = Object.entries(counts).map(([k, v]) => `<span class="flex items-center gap-1"><i class="inline-block w-2.5 h-2.5 rounded-[1px]" style="background:${colorOf(k)}"></i>${v} from ${esc(k)}</span>`).join("");
        return `<div class="mb-space-lg last:mb-0"><div class="flex items-center justify-between mb-space-sm"><span class="font-label-lg text-label-lg text-primary">${esc(d.name)}</span><span class="font-label-sm text-label-sm text-outline">${d.chunks_done}/${d.chunks_total} chunks • strategy rarest-first</span></div>
          ${chunkMap(d.bitmap, d.sources, null)}<div class="flex flex-wrap gap-space-md mt-space-sm font-label-sm text-label-sm text-outline">${legend || "Waiting for chunks..."}</div></div>`;
      }).join(""), `<span class="font-label-sm text-label-sm text-outline">square colour = peer that sent the chunk</span>`));
    }
  }
  if (s) {
    const events = s.events.map((e) => {
      const map = { join: ["add_circle", "text-secondary", "JOINED"], done: ["check_circle", "text-primary-container", "DONE"], timeout: ["remove_circle", "text-error", "LOST"] };
      const [ic, col, word] = map[e.kind] || ["info", "text-outline", e.kind];
      return `<div class="flex items-start gap-space-sm py-space-sm border-b border-white/5"><span class="font-label-sm text-label-sm text-outline w-16 flex-shrink-0">${new Date(e.time * 1000).toLocaleTimeString()}</span>${icon(ic, "text-[16px] " + col)}<span class="font-label-sm text-label-sm ${col} w-14 flex-shrink-0">${word}</span><span class="font-body-sm text-body-sm text-on-surface-variant">${esc(e.text)}</span></div>`;
    }).join("") || `<div class="text-outline font-body-sm">Nothing yet.</div>`;
    parts.push(`<div class="grid grid-cols-1 lg:grid-cols-2 gap-space-lg">
      ${panel("Swarm Activity (all devices)", "monitoring", sparkline(s.history, "rate", "#00f2fe"))}
      ${panel("Tracker Activity", "history", `<div class="max-h-[220px] overflow-y-auto">${events}</div>`)}</div>`);
    s.files.forEach((f) => {
      const peers = s.peers.filter((p) => p.file_id === f.file_id);
      peers.forEach((p) => colorOf(p.ip + ":" + p.port));
      const cards = peers.map((p) => {
        const key = p.ip + ":" + p.port;
        const pct = Math.round((100 * p.chunks_held) / Math.max(1, p.num_chunks));
        const role = p.chunks_held >= p.num_chunks ? ((p.extra || {}).role === "seeder" ? "SEEDER" : "COMPLETE") : "DOWNLOADING";
        const late = p.seconds_ago > s.timeout / 2;
        return `<div class="rounded-lg bg-surface-container p-space-md border-l-4" style="border-color:${colorOf(key)}">
          <div class="flex flex-wrap items-center gap-space-sm mb-space-sm"><span class="font-label-lg text-label-lg text-on-surface">${esc(key)}</span>
          <span class="px-space-xs py-0.5 rounded font-label-sm text-label-sm ${role === "DOWNLOADING" ? "bg-primary-container/10 text-primary-container" : "bg-secondary-container/20 text-secondary"}">${role}</span>
          ${late ? `<span class="px-space-xs py-0.5 rounded font-label-sm text-label-sm bg-tertiary-container/10 text-tertiary-fixed-dim">no heartbeat ${p.seconds_ago}s</span>` : ""}
          <span class="ml-auto font-headline-md text-headline-md text-primary">${pct}%</span></div>
          ${chunkMap(p.bitmap, (p.extra || {}).sources || {}, colorOf(key))}
          <div class="flex flex-wrap gap-space-md mt-space-sm font-label-sm text-label-sm text-on-surface-variant"><span>↓ ${fmtRate(p.down_rate)}</span><span>↑ ${fmtRate(p.up_rate)}</span><span>uploaded ${fmtBytes(p.uploaded)}</span></div></div>`;
      }).join("");
      parts.push(panel(esc(f.name), "description", `<div class="mb-space-lg">${availStrip(f)}</div><div class="grid grid-cols-1 lg:grid-cols-2 gap-space-md">${cards}</div>`,
        `<span class="font-label-sm text-label-sm text-outline">${fmtBytes(f.size)} • ${f.num_chunks} chunks • ${f.seeders} seed / ${f.leechers} leech</span>`));
    });
  }
  setHTML(el, `<div class="flex flex-col gap-space-lg">${parts.join("")}</div>`);
}

// ------------------------------------------------------------------ CONFIG
function renderConfig(el) {
  const d = S.data, c = d.client, s = d.server;
  const clientCard = c ? `
    <div class="flex flex-col gap-space-md">
      <div class="grid grid-cols-2 gap-space-md">${kvBlock("Server", c.server + (c.server_name ? " (" + c.server_name + ")" : ""))}${kvBlock("Status", c.status)}${kvBlock("Device name", c.device_name)}${kvBlock("Seen by server as", (c.my_ip || "?") + ":" + c.peer_port)}</div>
      <label class="flex flex-col gap-space-xs"><span class="field-label">Shared folder</span>
        <div class="flex gap-space-sm"><input id="cfgFolder" class="input flex-1" value="${esc(c.folder)}" spellcheck="false"><button class="btn-ghost" id="cfgBrowse">${icon("folder_open", "text-[16px]")}Browse</button><button class="btn-primary" id="cfgApply">Apply</button></div></label>
      <p class="font-body-sm text-body-sm text-outline">Changing the folder reconnects. Running downloads pause and resume later from the old folder only.</p>
      <div class="flex flex-wrap gap-space-sm"><button class="btn-ghost" onclick="openFolder()">${icon("folder", "text-[16px]")}Open folder</button><button class="btn-danger" onclick="disconnectClient()">${icon("link_off", "text-[16px]")}Disconnect</button></div>
    </div>` : `<p class="text-on-surface-variant font-body-md">Not connected. <a class="text-primary-container hover:underline" href="#/client">Connect to a server</a>.</p>`;
  const serverCard = s ? `
    <div class="flex flex-col gap-space-md">
      <div class="grid grid-cols-2 gap-space-md">${kvBlock("Share address (LAN)", s.share_url)}${kvBlock("Same PC", s.local_url)}${kvBlock("Peer timeout", s.timeout + " s")}${kvBlock("Uptime", fmtDuration(s.uptime))}</div>
      <div class="flex gap-space-sm"><button class="btn-ghost" onclick="copy('${esc(s.share_url)}')">${icon("content_copy", "text-[16px]")}Copy address</button><button class="btn-danger" onclick="stopServer()">${icon("stop_circle", "text-[16px]")}Stop server</button></div>
    </div>` : `<p class="text-on-surface-variant font-body-md">Not hosting. <a class="text-primary-container hover:underline" href="#/server">Host a server</a>.</p>`;
  const html = `<div class="max-w-4xl mx-auto flex flex-col gap-space-lg">
    ${panel("Client", "lan", clientCard)}
    ${panel("Server", "dns", serverCard)}
    ${howHostingWorks(d.lan_ip, s ? s.port : d.default_tracker_port)}
    ${panel("This PC", "computer", `<div class="grid grid-cols-3 gap-space-md">${kvBlock("PC name", d.device_name)}${kvBlock("LAN IP", d.lan_ip)}${kvBlock("OS", d.os)}</div>`)}
  </div>`;
  setHTML(el, html);
  if (c) {
    $("#cfgBrowse").onclick = () => folderPicker($("#cfgFolder").value, (p) => { $("#cfgFolder").value = p; });
    $("#cfgApply").onclick = () => act(() => api("/api/client/folder", { folder: $("#cfgFolder").value, create: true }), "Now sharing " + $("#cfgFolder").value);
  }
}
window.disconnectClient = () => confirmBox({ title: "Disconnect from server?", text: "Your files stop being shared and running downloads pause. Partial downloads resume when you reconnect with the same folder.", okLabel: "Disconnect", danger: true, onOk: () => act(() => api("/api/client/disconnect", {}), "Disconnected") });

// ------------------------------------------------------------------ main loop
function render() {
  renderChrome();
  if (!S.data) return;
  const input = document.activeElement;
  const keepFocus = input && input.tagName === "INPUT" && input.closest(".view") && !["filterInput"].includes(input.id) && !input.closest("#devSearchBox");
  if (keepFocus && (S.route === "/client" && !S.data.client || S.route === "/server" && !S.data.server || S.route === "/config")) return;  // do not redraw forms while typing
  if (S.route === "/client") renderClient($("#clientView"));
  if (S.route === "/server") renderServer($("#serverView"));
  if (S.route === "/telemetry") renderTelemetry($("#telemetryView"));
  if (S.route === "/config") renderConfig($("#configView"));
}
async function refresh() {
  try { S.data = await api("/api/state"); }
  catch (e) { S.data = null; }
  render();
}
setInterval(() => { if (!S.busy) refresh(); }, 1000);

// ------------------------------------------------------------------ title animation
function restartIntro() {
  document.querySelectorAll("[data-view='/'] .intro").forEach((n) => { n.style.animation = "none"; void n.offsetWidth; n.style.animation = ""; });
}
(function swarmBackground() {
  const cv = $("#swarmCanvas"), ctx = cv.getContext("2d");
  let nodes = [], W = 0, H = 0, packets = [];
  const reduce = window.matchMedia("(prefers-reduced-motion: reduce)").matches;
  function resize() {
    const r = cv.getBoundingClientRect();
    W = cv.width = r.width * devicePixelRatio; H = cv.height = r.height * devicePixelRatio;
    const n = Math.max(18, Math.min(60, Math.round((r.width * r.height) / 22000)));
    nodes = Array.from({ length: n }, () => ({ x: Math.random() * W, y: Math.random() * H, vx: (Math.random() - 0.5) * 0.25 * devicePixelRatio, vy: (Math.random() - 0.5) * 0.25 * devicePixelRatio, seed: Math.random() < 0.25 }));
  }
  function frame() {
    if (S.route === "/" && W) {
      ctx.clearRect(0, 0, W, H);
      const link = 150 * devicePixelRatio;
      for (const a of nodes) {
        if (!reduce) { a.x += a.vx; a.y += a.vy; }
        if (a.x < 0 || a.x > W) a.vx *= -1;
        if (a.y < 0 || a.y > H) a.vy *= -1;
      }
      for (let i = 0; i < nodes.length; i++) for (let j = i + 1; j < nodes.length; j++) {
        const a = nodes[i], b = nodes[j], d = Math.hypot(a.x - b.x, a.y - b.y);
        if (d < link) {
          ctx.strokeStyle = `rgba(0,242,254,${0.18 * (1 - d / link)})`;
          ctx.lineWidth = devicePixelRatio;
          ctx.beginPath(); ctx.moveTo(a.x, a.y); ctx.lineTo(b.x, b.y); ctx.stroke();
          if (!reduce && Math.random() < 0.0015) packets.push({ a, b, t: 0 });
        }
      }
      packets = packets.filter((p) => p.t <= 1);
      for (const p of packets) {
        p.t += 0.02;
        const x = p.a.x + (p.b.x - p.a.x) * p.t, y = p.a.y + (p.b.y - p.a.y) * p.t;
        ctx.fillStyle = "rgba(78,222,163,0.9)";
        ctx.fillRect(x - 1.5 * devicePixelRatio, y - 1.5 * devicePixelRatio, 3 * devicePixelRatio, 3 * devicePixelRatio);
      }
      for (const a of nodes) {
        ctx.fillStyle = a.seed ? "rgba(78,222,163,0.8)" : "rgba(0,242,254,0.55)";
        ctx.beginPath(); ctx.arc(a.x, a.y, (a.seed ? 2.4 : 1.6) * devicePixelRatio, 0, Math.PI * 2); ctx.fill();
      }
    }
    requestAnimationFrame(frame);
  }
  window.addEventListener("resize", resize);
  setTimeout(resize, 50);
  requestAnimationFrame(frame);
})();

route();
refresh();
