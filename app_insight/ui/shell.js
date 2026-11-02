/* shell: icon helper, shared page pieces, router, global search, export, toast. Screens register themselves as functions p<Name>(main, ...). */
const put = (m, html) => m.insertAdjacentHTML("beforeend", html);
const PAGE = 50;
const fmtDate = iso => { try { return new Date(iso).toUTCString().replace(/ GMT$/, " UTC").replace(/^\w+, /, ""); } catch (e) { return iso; } };
const pageHeading = (title, sub, right) => `<div class="pageheading"><div><h1>${esc(title)}</h1>${sub ? `<p>${esc(sub)}</p>` : ""}</div>${right || ""}</div>`;
const crumbs = parts => `<nav class="breadcrumbs" aria-label="Breadcrumb">${parts.map((p, i) => (i ? '<span class="sep">›</span>' : "") + (p[1] ? `<a href="${esc(p[1])}">${esc(p[0])}</a>` : `<span>${esc(p[0])}</span>`)).join("")}</nav>`;
const staticBanner = () => `<div class="static-banner">${icon("info")}<span><b>Static scan.</b> ${esc(D.apps.length)} repositories were read; nothing was built, run or queried. Every number opens the applications or evidence behind it.</span></div>`;
const emptyState = (title, text) => `<div class="empty"><b>${esc(title)}</b><div class="tiny" style="margin-top:4px">${esc(text)}</div></div>`;
const sectionHeading = (title, sub, right, iconName, iconCls) => `<div class="section-heading"><div class="${iconName ? "title-with-icon" : ""}">${iconName ? `<span class="small-icon ${iconCls || ""}">${icon(iconName)}</span>` : ""}<div><h2>${title}</h2>${sub ? `<p>${sub}</p>` : ""}</div></div>${right || ""}</div>`;
const linkBtn = (text, href) => `<a class="linkbtn" href="${esc(href)}">${esc(text)} ${icon("arrow-right")}</a>`;
const ringStyle = (v, c) => `background:conic-gradient(${c} 0 ${v}%,#e9edf3 ${v}% 100%)`;
function toast(text) { const n = $("#toast"); n.textContent = text; n.classList.add("show"); clearTimeout(window._toast); window._toast = setTimeout(() => n.classList.remove("show"), 2800); }

/* the sidebar holds only whole-portfolio pages, so each item always opens the same place. One application's pages share appHead:
   its name, a switcher that keeps the tab, and the tabs. CUR is only the last application opened, shown as a visible shortcut. */
let CUR = null;
const NAV = [
  ["portfolio", "Dashboard", "dashboard", "#/portfolio"],
  ["apps", "Applications", "grid", "#/apps"],
  ["architecture", "Architecture", "network", "#/architecture"],
  ["gaps", "Findings", "alert-triangle", "#/gaps"],
  ["roadmap", "Roadmap", "list", "#/roadmap"],
  ["impact", "Change impact", "share", "#/impact"],
  ["about", "About", "info", "#/about"]];
const ATABS = [["app", "AS-IS", n => "#/app/" + n + "/overview"], ["assessment", "Assessment", n => "#/assessment/" + n], ["architecture", "Architecture", n => "#/architecture/" + n], ["findings", "Findings", n => "#/app/" + n + "/findings"]];
function appHead(m, name, tab) {
  const a = APPS[name], about = (a.discovery.identity.about || {}).value, enc = encodeURIComponent(name), nf = allFindings().filter(f => f.app === name).length, label = ATABS.find(t => t[0] === tab)[1];
  put(m, crumbs([["Applications", "#/apps"], [name, tab === "app" ? null : "#/app/" + enc + "/overview"]].concat(tab === "app" ? [] : [[label]])));
  put(m, `<div class="entity-head"><div style="display:flex;gap:14px;align-items:flex-start"><div class="title-icon">${icon(val(a, "stack.artifact_kind") === "library" ? "package" : "box")}</div><div><div class="title-line"><h1 style="margin:0">${esc(name)}</h1><span class="status-pill green">Scanned</span></div><p>${esc(kindOf(a) || "application")}</p>${about ? `<p style="margin-top:8px;max-width:640px">${esc(String(about).slice(0, 260))}</p>` : ""}</div></div><div class="button-group"><label class="tiny" for="appSwitch">Switch application</label><select class="filter" id="appSwitch">${D.apps.map(x => `<option${x.name === name ? " selected" : ""}>${esc(x.name)}</option>`).join("")}</select></div></div>
<nav class="tabs compact app-tabs" aria-label="${esc(name)} views">${ATABS.map(([k, l, href]) => `<a class="tab${k === tab ? " active" : ""}"${k === tab ? ' aria-current="page"' : ""} href="${href(enc)}">${esc(l)}${k === "findings" && nf ? ` <span class="tab-badge">${nf}</span>` : ""}</a>`).join("")}</nav>`);
  $("#appSwitch").addEventListener("change", e => { location.hash = ATABS.find(t => t[0] === tab)[2](encodeURIComponent(e.target.value)); });
}
const recentLink = () => CUR && APPS[CUR] ? `<p class="tiny" style="margin:-4px 0 10px">Last opened: <a class="appname" href="#/app/${encodeURIComponent(CUR)}/overview">${esc(CUR)}</a></p>` : "";

function route() {
  const raw = (location.hash || "#/portfolio").replace(/^#\/?/, ""), qi = raw.indexOf("?"), query = qi >= 0 ? raw.slice(qi + 1) : "", parts = (qi >= 0 ? raw.slice(0, qi) : raw).split("/"), view = parts[0] || "portfolio";
  closeDrawer();
  const app = parts[1] ? decodeURIComponent(parts[1]) : null, inApp = app && APPS[app] && ["app", "assessment", "architecture", "map"].includes(view);
  if (inApp) CUR = app;
  // inside one application the sidebar marks Applications: that is where its pages live
  const key = inApp ? "apps" : ({map: "architecture", finding: "gaps", app: "apps", assessment: "apps"})[view] || view;
  $("#navigation").innerHTML = NAV.map(([k, l, ic, href]) => `<a href="${esc(href)}" class="navitem${k === key ? " active" : ""}"${k === key ? ' aria-current="page"' : ""}>${icon(ic)}<span>${esc(l)}</span></a>`).join("");
  const m = $("#main"); m.replaceChildren();
  if (view === "app") app ? pApp(m, app, parts[2]) : pApps(m, "");
  else if (view === "apps") pApps(m, parts[1] && !query ? "f=" + parts[1] : query);
  else if (view === "assessment") app ? pAssessment(m, app, parts[2]) : pApps(m, "");
  else if (view === "architecture") pArchitecture(m, app === "all" ? null : app, parts[2], parts[3]);
  else if (view === "map") pArchitecture(m, app && app !== "all" ? app : null, parts[2], parts[3]);
  else if (view === "gaps") pFindings(m, query);
  else if (view === "finding") pFinding(m, decodeURIComponent(parts.slice(1).join("/")));
  else if (view === "roadmap") pRoadmap(m);
  else if (view === "impact") pImpact(m);
  else if (view === "about") pAbout(m);
  else pDashboard(m);
  window.scrollTo(0, 0);
}

/* global search: applications and relationships */
const q = $("#q"), res = $("#results"); let selIdx = 0, hits = [];
function drawRes() {
  const t = q.value.trim().toLowerCase(); if (!t) { res.hidden = true; return; }
  hits = [...D.apps.filter(a => a.name.toLowerCase().includes(t)).map(a => ({l: a.name, s: "application", go: () => location.hash = "#/app/" + a.name + "/overview"})),
    ...D.portfolio.graph.edges.filter(e => e.type !== "CONTAINS" && edgeSentence(e).toLowerCase().includes(t)).slice(0, 8).map(e => ({l: edgeSentence(e), s: e.resolution.state, go: () => showEdges([e.id])}))].slice(0, 12);
  selIdx = 0; res.hidden = false; res.replaceChildren(...(hits.length ? hits.map((x, i) => h("button", {class: i === 0 ? "sel" : "", onclick: () => { res.hidden = true; q.value = ""; x.go(); }}, x.l, h("small", {}, x.s))) : [h("div", {class: "tiny", style: "padding:12px"}, "No match")]));
}
q.addEventListener("input", drawRes);
q.addEventListener("keydown", e => { if (e.key === "Enter" && hits[selIdx]) { res.hidden = true; const x = hits[selIdx]; q.value = ""; x.go(); } if (e.key === "Escape") { res.hidden = true; q.blur(); } });
document.addEventListener("keydown", e => { const t = document.activeElement.tagName; if (e.key === "/" && t !== "INPUT" && t !== "SELECT" && t !== "TEXTAREA") { e.preventDefault(); q.focus(); } if ((e.metaKey || e.ctrlKey) && e.key.toLowerCase() === "k") { e.preventDefault(); q.focus(); } if (e.key === "Escape") closeDrawer(); });
document.addEventListener("click", e => { if (!e.target.closest("#searchbox")) res.hidden = true; });
$("#export").addEventListener("click", () => {
  const out = {generated: D.generated, applications: D.apps.map(a => ({name: a.name, dimensions: Object.fromEntries(Object.entries(a.dimensions.dimensions).map(([k, d]) => [k, {state: d.state, level: d.level, headline: d.headline}])), open_links: S[a.name].un, components_mapped: S[a.name].mapped + "/" + S[a.name].tot}))};
  const url = URL.createObjectURL(new Blob([JSON.stringify(out, null, 2)], {type: "application/json"})), l = h("a", {href: url, download: "discovery-summary.json"}); document.body.append(l); l.click(); l.remove(); setTimeout(() => URL.revokeObjectURL(url), 1000);
});

/* delegated navigation: any element with data-go behaves as a link (rows, cards) */
document.addEventListener("click", e => { const g = e.target.closest("[data-go]"); if (g && !e.target.closest("a,button,input,select")) location.hash = g.dataset.go; });
document.addEventListener("keydown", e => { if (e.key === "Enter") { const g = e.target.closest && e.target.closest("[data-go]"); if (g && e.target === g) location.hash = g.dataset.go; } });
