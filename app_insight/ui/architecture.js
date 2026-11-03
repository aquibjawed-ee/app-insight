/* architecture: v2 "Architecture Explorer". The canvas is laid out from the real graph edges of one application; nothing is drawn that is not an edge. */
const AK = {primary: ["arch-node primary", "Application / Service"], app: ["arch-node", "Application / Service"], ext: ["arch-node ext", "External System"], db: ["arch-node db", "Database / Storage"], queue: ["arch-node queue", "Queue / Topic"], node: ["arch-node node", "Deployment Node"], api: ["arch-node gateway", "API / Interface"], unres: ["arch-node unres", "Unresolved target"], more: ["arch-node more", "More"]};
const ASYNC = ["PUBLISHES_TO", "CONSUMES_FROM"], DATA = ["READS_FROM", "WRITES_TO"];
function nodeKind(n) {
  if (!n) return "ext";
  if (n.attrs && n.attrs.unresolved) return "unres";
  return {Application: "app", Database: "db", MessageBroker: "queue", Topic: "queue", InfrastructureResource: "node", ExternalSystem: "ext", Service: "ext", ApiEndpoint: "api", Module: "app"}[n.type] || "ext";
}
function nodeSubtitle(n) {
  if (!n) return "";
  const a = n.attrs || {};
  if (n.type === "Application") return kindOf(APPS[n.name] || {name: ""}) || "application";
  if (n.type === "Database" || n.type === "Cache") return [a.technology, a.identity === "connection" ? "shared connection" : "application-local"].filter(Boolean).join(" · ");
  if (n.type === "MessageBroker") return a.technology || a.family || "broker";
  if (n.type === "Topic") return (a.broker_family || "topic") + (a.cluster_verified === false ? " · cluster not verified" : "");
  if (n.type === "InfrastructureResource") return a.platform || "deployment";
  if (n.type === "ExternalSystem") return a.role || a.host || "external system";
  return n.type;
}
/* direct dependents of an application: callers, topic consumers, applications sharing a database (potential impact, not proof) */
function dependentsOf(app) {
  const E = D.portfolio.graph.edges, me = "app:" + app, out = new Set();
  for (const x of incoming(app)) if (x.e.source.startsWith("app:")) out.add(x.e.source.slice(4));
  const owned = new Set(E.filter(e => e.source === me && ["PUBLISHES_TO", "WRITES_TO"].includes(e.type)).map(e => e.target));
  for (const e of E) if (e.source !== me && e.source.startsWith("app:") && owned.has(e.target) && ["CONSUMES_FROM", "READS_FROM", "WRITES_TO"].includes(e.type)) out.add(e.source.slice(4));
  out.delete(app);
  return [...out];
}
function blastRadius(app) {
  const seen = new Set([app]), levels = []; let frontier = [app];
  for (let d = 0; d < 3; d++) { const next = []; for (const x of frontier) for (const y of dependentsOf(x)) if (!seen.has(y)) { seen.add(y); next.push(y); } levels.push(next); frontier = next; }
  return levels;
}
function callChains(app) {
  const E = D.portfolio.graph.edges, chains = [];
  const targetsOf = x => [...new Set(E.filter(e => e.type === "CALLS_API" && e.source === "app:" + x && e.target.startsWith("app:") && e.resolution.state === "resolved").map(e => e.target.slice(4)))];
  const walk = (path) => { const nx = targetsOf(path[path.length - 1]).filter(y => !path.includes(y)); if (!nx.length || path.length >= 4) { if (path.length > 1) chains.push(path); return; } nx.forEach(y => walk(path.concat(y))); };
  walk([app]);
  const up = []; const callersOf = x => [...new Set(E.filter(e => e.type === "CALLS_API" && e.target === "app:" + x && e.source.startsWith("app:")).map(e => e.source.slice(4)))];
  const walkUp = (path) => { const nx = callersOf(path[0]).filter(y => !path.includes(y)); if (!nx.length || path.length >= 4) { if (path.length > 1) up.push(path); return; } nx.forEach(y => walkUp([y].concat(path))); };
  walkUp([app]);
  return chains.concat(up).sort((a, b) => b.length - a.length || a.join().localeCompare(b.join())).slice(0, 5);
}
/* the model: nodes with a column, links with the graph edge ids behind them */
function archModel(app, mode, decl) {
  const G = D.portfolio.graph, E = G.edges, me = "app:" + app, nodes = [], links = [], byId = {};
  const mk = (id, o) => { if (!byId[id]) { byId[id] = Object.assign({id, w: 196, h: 66}, o); nodes.push(byId[id]); } return byId[id]; };
  const C = mk(me, {label: app, sub: kindOf(APPS[app]) || "application", kind: "primary", col: "c", w: 224, h: 70});
  const link = (a, b, e, kind, label) => { const k = a + ">" + b + ">" + kind, ex = links.find(l => l.key === k); if (ex) { ex.ids.push(e.id); ex.n++; if (["unresolved", "ambiguous"].includes((e.resolution || {}).state)) ex.state = e.resolution.state; } else links.push({key: k, from: a, to: b, kind, ids: [e.id], n: 1, label, state: (e.resolution || {}).state || "resolved"}); };
  const out = E.filter(e => e.source === me && !["CONTAINS", "EXPOSES_API"].includes(e.type) && (decl || e.basis !== "declared"));
  const eps = G.nodes.filter(n => n.type === "ApiEndpoint" && n.app === app);
  const addTarget = (e, col) => {
    const n = G.nodes.find(x => x.id === e.target) || NODES[e.target]; if (!n) return;
    const kind = nodeKind(n); if (mode === "deployment" && n.type !== "InfrastructureResource") return;
    if (mode === "data" && !["db", "queue"].includes(kind)) return;
    const c = col || (n.type === "InfrastructureResource" ? "b" : ["db", "queue"].includes(kind) ? "b" : "r");
    mk(n.id, {label: n.name, sub: nodeSubtitle(n), kind, col: c, node: n});
    const style = ASYNC.includes(e.type) ? "async" : DATA.includes(e.type) || ["db", "queue"].includes(kind) ? "data" : e.type === "DEPLOYED_ON" ? "deploy" : "sync";
    const a = e.attrs || {}, lab = e.type === "CALLS_API" ? (a.method && a.path ? "" : "") : "";
    link(me, n.id, e, style, lab);
  };
  if (mode !== "data" && mode !== "deployment") {
    if (eps.length) { const A = mk("api:" + app, {label: "API (" + eps.length + " endpoint" + (eps.length === 1 ? "" : "s") + ")", sub: [...new Set(eps.map(x => x.attrs.framework))].filter(Boolean).join(", ") || "HTTP interface", kind: "api", col: "t"}); links.push({key: "api", from: A.id, to: me, kind: "sync", ids: [], n: eps.length, label: "exposes", state: "resolved", api: true}); }
    for (const x of incoming(app)) { const sid = x.e.source; const sn = G.nodes.find(n => n.id === sid) || NODES[sid]; if (!sn) continue; mk(sid, {label: sn.name, sub: nodeSubtitle(sn), kind: nodeKind(sn), col: "l", node: sn}); link(sid, me, x.e, ASYNC.includes(x.e.type) ? "async" : "sync", ""); }
  }
  out.forEach(e => { if (mode === "deployment" ? e.type === "DEPLOYED_ON" : true) addTarget(e); });
  if (mode === "data") {   // other applications that touch the same stores and topics
    const mine = new Set(out.map(e => e.target));
    for (const e of E) if (e.source.startsWith("app:") && e.source !== me && mine.has(e.target) && [...ASYNC, ...DATA].includes(e.type)) { const sn = NODES[e.source]; mk(e.source, {label: sn.name, sub: "also uses " + nm(e.target), kind: "app", col: "r", node: sn}); link(e.source, e.target, e, ASYNC.includes(e.type) ? "async" : "data", ""); }
  }
  if (mode === "deployment") {
    for (const w of (APPS[app].resilience.workloads || []).slice(0, 6)) mk("w:" + w.name + w.kind, {label: w.name, sub: (w.kind || "workload") + (w.replicas != null ? " · " + w.replicas + " replica" + (w.replicas === 1 ? "" : "s") : ""), kind: "node", col: "b", w: 178}), links.push({key: "w" + w.name + w.kind, from: me, to: "w:" + w.name + w.kind, kind: "deploy", ids: [], n: 1, label: "", state: "resolved"});
  }
  return {nodes, links, byId, eps, C};
}
const CAP = {l: 6, r: 7, b: 6};
function archLayout(M) {
  const cols = {l: [], r: [], b: [], t: [], c: [M.C]}, hidden = {};
  for (const n of M.nodes) if (n !== M.C) (cols[n.col] || cols.r).push(n);
  for (const k of ["l", "r", "b"]) if (cols[k].length > CAP[k]) { hidden[k] = cols[k].slice(CAP[k] - 1); cols[k] = cols[k].slice(0, CAP[k] - 1); const ids = new Set(hidden[k].map(x => x.id)); M.nodes = M.nodes.filter(n => !ids.has(n.id)); const lk = M.links.filter(l => ids.has(l.from) || ids.has(l.to)); M.links = M.links.filter(l => !lk.includes(l)); const more = {id: "more:" + k, label: "+" + hidden[k].length + " more", sub: hidden[k].map(x => x.label).slice(0, 3).join(", ") + "…", kind: "more", col: k, w: 178, h: 62, hiddenIds: lk.flatMap(l => l.ids)}; cols[k].push(more); M.nodes.push(more); M.links.push({key: "more" + k, from: k === "l" ? more.id : M.C.id, to: k === "l" ? M.C.id : more.id, kind: "sync", ids: more.hiddenIds, n: more.hiddenIds.length, label: "", state: "resolved", more: true}); }
  const STEP = 88, X = {l: 16, c: 300, r: 590}, top = 24;
  const rowsL = cols.l.length, rowsR = cols.r.length, rows = Math.max(rowsL, rowsR, 1);
  const cy = top + 70 + ((rows - 1) * STEP) / 2;
  M.C.x = X.c; M.C.y = cy;
  cols.l.forEach((n, i) => { n.x = X.l; n.y = cy - ((rowsL - 1) * STEP) / 2 + i * STEP; });
  cols.r.forEach((n, i) => { n.x = X.r; n.y = cy - ((rowsR - 1) * STEP) / 2 + i * STEP; });
  if (cols.t.length) { cols.t[0].x = X.c + 24; cols.t[0].y = Math.max(8, cy - 120); }
  const bottomY = cy + 70 + 100, nb = cols.b.length, bw = 176, gap = 14, totalW = nb * bw + (nb - 1) * gap, bx0 = Math.max(X.l, X.c + 112 - totalW / 2);
  cols.b.forEach((n, i) => { n.w = bw; n.x = bx0 + i * (bw + gap); n.y = bottomY; });
  for (const n of M.nodes) { if (n.x == null) { n.x = X.r; n.y = top; } }
  const W = Math.max(820, bx0 + totalW + 16, X.r + 196 + 16), H = (nb ? bottomY + 62 : cy + 70) + 40;
  return {W, H, cols};
}
const anchor = (n, side) => side === "r" ? [n.x + n.w, n.y + n.h / 2] : side === "l" ? [n.x, n.y + n.h / 2] : side === "b" ? [n.x + n.w / 2, n.y + n.h] : [n.x + n.w / 2, n.y];
function linkPath(a, b) {
  let s, t, c1, c2;
  if (a.col === "b" && b.col === "c" || a.col === "t") { s = anchor(a, a.col === "t" ? "b" : "t"); t = anchor(b, a.col === "t" ? "t" : "b"); }
  else if (b.col === "b") { s = anchor(a, "b"); t = anchor(b, "t"); }
  else if (a.col === "b") { s = anchor(a, "t"); t = anchor(b, "b"); }
  else if (a.x < b.x) { s = anchor(a, "r"); t = anchor(b, "l"); } else { s = anchor(a, "l"); t = anchor(b, "r"); }
  const vertical = (b.col === "b" || a.col === "b" || a.col === "t");
  if (vertical) { const my = (s[1] + t[1]) / 2; c1 = [s[0], my]; c2 = [t[0], my]; } else { const mx = (s[0] + t[0]) / 2; c1 = [mx, s[1]]; c2 = [mx, t[1]]; }
  return {d: `M${s[0]},${s[1]} C${c1[0]},${c1[1]} ${c2[0]},${c2[1]} ${t[0]},${t[1]}`, mid: [(s[0] + t[0]) / 2, (s[1] + t[1]) / 2]};
}
const LK = {sync: ["#6e88ae", ""], async: ["#f39b22", "7 5"], data: ["#2f80ff", "7 5"], deploy: ["#9d87e6", "3 4"], bad: ["#d93049", "3 4"]};
function archSvg(M, L) {
  const defs = Object.entries(LK).map(([k, [c]]) => `<marker id="ah-${k}" viewBox="0 0 10 10" refX="9" refY="5" markerWidth="7" markerHeight="7" orient="auto-start-reverse"><path d="M0,0 L10,5 L0,10 z" fill="${c}"/></marker>`).join("");
  const body = M.links.map(l => {
    const a = M.byId[l.from] || M.nodes.find(n => n.id === l.from), b = M.byId[l.to] || M.nodes.find(n => n.id === l.to); if (!a || !b) return "";
    const p = linkPath(a, b), bad = ["unresolved", "ambiguous"].includes(l.state), st = LK[bad ? "bad" : l.kind] || LK.sync;
    const lab = bad ? l.state : l.api ? "" : l.n > 1 ? l.n + "×" : "";
    return `<g class="alink${bad ? " bad" : ""}" data-ids="${esc(l.ids.join(" "))}" tabindex="${l.ids.length ? 0 : -1}"><path d="${p.d}" fill="none" stroke="${st[0]}" stroke-width="2" ${st[1] ? `stroke-dasharray="${st[1]}"` : ""} marker-end="url(#ah-${bad ? "bad" : l.kind})"/><path d="${p.d}" fill="none" stroke="transparent" stroke-width="14"/>${lab ? `<text x="${p.mid[0]}" y="${p.mid[1] - 4}" text-anchor="middle" class="alab">${esc(lab)}</text>` : ""}</g>`;
  }).join("");
  return `<svg class="arch-svg" width="${L.W}" height="${L.H}" viewBox="0 0 ${L.W} ${L.H}" aria-hidden="false"><defs>${defs}</defs>${body}</svg>`;
}
function archNodeHtml(n, sel) {
  const c = AK[n.kind] || AK.ext;
  const head = n.kind === "primary" ? `<div class="node-top"><span class="appicon">${icon("box")}</span><div><div class="node-title">${esc(n.label)}</div><div class="node-sub">${esc(n.sub)}</div></div></div>` : `<div class="node-title">${esc(n.label)}</div><div class="node-sub">${esc(n.sub)}</div>`;
  return `<div class="${c[0]}${sel ? " sel" : ""}" role="button" tabindex="0" data-node="${esc(n.id)}" style="left:${Math.round(n.x)}px;top:${Math.round(n.y)}px;width:${n.w}px;min-height:${n.h}px" title="${esc(n.label + " · " + c[1])}">${head}</div>`;
}
/* side panel for the selected node */
const SRC_KIND = [["Build files", /(^|\/)(pom\.xml|build\.gradle(\.kts)?|settings\.gradle(\.kts)?|gradle\.properties|.*\.versions\.toml)$/], ["Deployment files", /(k8s|kubernetes|helm|charts?|deploy|nomad|compose|Dockerfile|\.ya?ml$)/i], ["Configuration files", /(application.*\.(ya?ml|properties)|\.env|config)/i], ["CI files", /(\.gitlab-ci|Jenkinsfile|\.github\/workflows|azure-pipelines|bitbucket-pipelines|circleci)/i], ["Source code", /\.(java|kt|groovy|scala)$/]];
function evidenceSources(app) {
  const paths = [], seen = new Set();
  for (const sec of Object.values(APPS[app].discovery)) if (sec && typeof sec === "object" && !Array.isArray(sec)) for (const f of Object.values(sec)) if (f && f.evidence) for (const ev of f.evidence) if (ev.path && !seen.has(ev.path)) { seen.add(ev.path); paths.push(ev.path); }
  for (const e of D.portfolio.graph.edges) if (e.source === "app:" + app) for (const ev of e.evidence || []) if (ev.path && ev.app === app && !seen.has(ev.path)) { seen.add(ev.path); paths.push(ev.path); }
  const rows = SRC_KIND.map(([l, rx]) => [l, paths.filter(p => rx.test(p)).length]);
  const known = rows.reduce((t, r) => t + r[1], 0);
  return {rows: rows.filter(r => r[1]), total: paths.length, other: Math.max(0, paths.length - known)};
}
function nodePanelHtml(M, id, app, tab) {
  const n = M.byId[id] || M.nodes.find(x => x.id === id) || M.C, isApp = n === M.C;
  const rel = D.portfolio.graph.edges.filter(e => (e.source === n.id || e.target === n.id) && e.type !== "CONTAINS");
  const eps = M.eps, depsOut = isApp ? relEdges(app) : rel, inc = isApp ? incoming(app) : [];
  const gaps = isApp ? findingsFor(app) : [];
  const tabs = [["overview", "Overview"], ["interfaces", "Interfaces (" + (isApp ? eps.length : 0) + ")"], ["deps", "Dependencies (" + (isApp ? depsOut.length + inc.length : rel.length) + ")"], ["findings", "Findings (" + (isApp ? gaps.length : rel.filter(e => ["unresolved", "ambiguous"].includes(e.resolution.state)).length) + ")"]];
  const tab_ = tab || "overview";
  const head = `<div class="panel-title"><div style="display:flex;align-items:center;gap:10px;min-width:0"><span class="appicon">${icon(isApp ? "box" : n.kind === "db" ? "database" : n.kind === "queue" ? "share" : "network")}</span><h2 style="overflow-wrap:anywhere">${esc(n.label)}</h2></div><span class="tag ${isApp ? "green" : n.kind === "unres" ? "red" : "gray"}">${isApp ? "Scanned" : esc((AK[n.kind] || AK.ext)[1])}</span></div><div class="tabs compact" role="tablist">${tabs.map(([k, l]) => `<button class="tab${k === tab_ ? " active" : ""}" role="tab" aria-selected="${k === tab_}" data-ptab="${k}">${esc(l)}</button>`).join("")}</div>`;
  let body = "";
  if (tab_ === "overview") {
    if (isApp) {
      const a = APPS[app], mix = evidenceMix([a]), tot = Object.values(mix).reduce((x, y) => x + y, 0), pct = tot ? Math.round(100 * mix.CONFIRMED / tot) : 0, src = evidenceSources(app);
      const crit = dim(a, "business_criticality"), ownv = (a.discovery.identity.owners || {}).value, own = Array.isArray(ownv) ? (ownv.length ? ownv : null) : ownv;
      body += `<div class="info-grid"><div class="info-box"><h4>Evidence coverage</h4><div style="display:flex;align-items:center;gap:12px"><div class="mini-ring big" style="--pct:${pct}"><span>${pct}%</span></div><b style="font-size:13px">facts confirmed</b></div><div class="desc" style="margin-top:8px">${mix.CONFIRMED} of ${tot} facts read from a cited line; the rest are inferred, not found or unknown</div></div><div class="info-box"><h4>Criticality</h4><span class="tag gray">${crit.state === "assessed" ? esc(crit.headline) : "Unknown"}</span><div class="desc" style="margin-top:10px;color:#627691">${crit.state === "assessed" ? "From the supplied criticality file" : "No verified criticality file was supplied, and it is never inferred from technology"}<br>${dependentsOf(app).length} application${dependentsOf(app).length === 1 ? "" : "s"} depend on it directly (graph)</div></div></div>
<div class="overview-card" style="padding:0;border:0"><div class="section-heading" style="margin-top:14px"><div><h2 style="font-size:14px">Basic information</h2></div></div><table class="simple-table"><tbody><tr><td>Application</td><td><b>${esc(app)}</b></td></tr><tr><td>Type</td><td>${esc(val(a, "stack.artifact_kind") || "—")}</td></tr><tr><td>Language</td><td>${esc([val(a, "stack.language"), val(a, "stack.java_version") ? "Java " + val(a, "stack.java_version") : null, val(a, "stack.spring_boot_version") ? "Spring Boot " + val(a, "stack.spring_boot_version") : null].filter(Boolean).join(" · ") || "—")}</td></tr><tr><td>Owner</td><td>${own ? esc(fmt(own)) : '<span class="tiny">not found (no CODEOWNERS)</span>'}</td></tr><tr><td>Deployment</td><td>${esc(deployText(a))}</td></tr><tr><td>Last scanned</td><td>${esc(fmtDate(D.generated))}</td></tr></tbody></table></div>
<div class="overview-card evidence-sources" style="padding:0;border:0"><div class="section-heading" style="margin-top:12px"><div><h2 style="font-size:14px">Evidence sources (${src.total})</h2></div><a class="linkbtn" href="#/app/${encodeURIComponent(app)}/evidence">View all ${icon("arrow-right")}</a></div>${src.rows.map(([l, c]) => `<div class="src-row"><span class="appicon">${icon("file")}</span><span>${esc(l)}</span><span class="tag gray">${c} file${c === 1 ? "" : "s"}</span><span class="muted-note">cited</span></div>`).join("")}${src.other ? `<div class="src-row"><span class="appicon">${icon("file")}</span><span>Other files</span><span class="tag gray">${src.other}</span><span class="muted-note">cited</span></div>` : ""}<p class="tiny" style="margin-top:8px">Files whose lines are cited as evidence. Every citation is re-read by <code>relate.py validate</code>.</p></div>`;
    } else {
      const at = n.node ? n.node.attrs || {} : {};
      body += `<div class="overview-card" style="padding:0;border:0"><table class="simple-table"><tbody><tr><td>Name</td><td><b>${esc(n.label)}</b></td></tr><tr><td>Type</td><td>${esc((AK[n.kind] || AK.ext)[1])}</td></tr>${Object.entries(at).filter(([k, v]) => v != null && typeof v !== "object" && k !== "unresolved").slice(0, 8).map(([k, v]) => `<tr><td>${esc(human(k))}</td><td>${esc(v)}</td></tr>`).join("")}<tr><td>Relationships</td><td>${rel.length}</td></tr></tbody></table></div>`;
    }
    body += `<div style="margin-top:12px"><button class="outline" data-evidence="${esc(n.id)}">Open evidence for ${isApp ? "this application" : "this component"}</button></div>`;
  } else if (tab_ === "interfaces") {
    body += isApp && eps.length ? `<table class="simple-table"><thead><tr><th>Method</th><th>Path</th></tr></thead><tbody>${eps.slice(0, 60).map(x => `<tr><td><span class="tag ${({GET: "green", POST: "blue", DELETE: "red"})[x.attrs.method] || "yellow"}">${esc(x.attrs.method)}</span></td><td style="overflow-wrap:anywhere">${esc(x.attrs.path)}</td></tr>`).join("")}</tbody></table>${eps.length > 60 ? `<p class="tiny">+${eps.length - 60} more (see the Discovery page)</p>` : ""}` : emptyState("No interfaces", isApp ? "No HTTP endpoints were found." : "Interfaces are listed for applications only.");
  } else if (tab_ === "deps") {
    const rowsH = [...(isApp ? inc.map(x => x.e) : []), ...depsOut.filter(e => e.type !== "EXPOSES_API")].slice(0, 40).map(e => `<div class="list-row"><span class="tag ${["unresolved", "ambiguous"].includes(e.resolution.state) ? "red" : "gray"}">${esc(human(e.type).toLowerCase())}</span><div><b>${esc(nm(e.source === n.id || e.source === "app:" + app ? e.target : e.source))}</b><div class="desc">${esc(edgeSentence(e))}</div></div><span class="tag ${["unresolved", "ambiguous"].includes(e.resolution.state) ? "yellow" : "green"}">${esc(e.resolution.state)}</span><button class="mini" data-edge="${esc(e.id)}">Evidence</button></div>`);
    body += rowsH.length ? `<div class="list">${rowsH.join("")}</div>` : emptyState("No dependencies found", "None were found in the files read.");
  } else {
    const items = isApp ? gaps : rel.filter(e => ["unresolved", "ambiguous"].includes(e.resolution.state)).map(e => ({id: "", title: edgeSentence(e), severity: "Medium", edge: e.id}));
    body += items.length ? `<div class="list">${items.slice(0, 20).map(f => `<div class="list-row"><span class="tag ${f.severity === "High" ? "red" : "yellow"}">${esc(f.severity)}</span><div><b>${esc(f.title)}</b></div><span></span>${f.id ? `<a class="mini" href="#/finding/${encodeURIComponent(f.id)}">Open</a>` : `<button class="mini" data-edge="${esc(f.edge)}">Evidence</button>`}</div>`).join("")}</div>` : emptyState("No findings", "No rule flagged this.");
  }
  return head + body;
}
function deployText(a) {
  const res = a.resilience || {}, bits = [], h2 = val(a, "stack.hosting"), c = val(a, "stack.container") || {};
  (res.platforms || []).forEach(x => bits.push(typeof x === "string" ? x : x.platform || x.name));
  (Array.isArray(h2) ? h2 : []).filter(x => x.role === "deployment target").forEach(x => bits.push(x.target));
  if (c.image_build || (c.dockerfiles || []).length) bits.push("containerised");
  const u = [...new Set(bits.filter(Boolean))];
  return u.length ? u.join(" · ") : "not found in the files read";
}
function pArchitecture(m, app, mode, decl) {
  mode = ["logical", "data", "deployment"].includes(mode) ? mode : "logical";
  if (!app || !APPS[app]) return archPortfolio(m);
  decl = decl === "decl"; const declN = D.portfolio.graph.edges.filter(e => e.source === "app:" + app && e.basis === "declared" && e.type === "DEPENDS_ON").length;
  const M = archModel(app, mode, decl), L = archLayout(M);
  const risks = archRisks(app), chains = callChains(app), lv = blastRadius(app), totalImpact = lv.reduce((t, x) => t + x.length, 0);
  appHead(m, app, "architecture");
  const nrel = M.links.reduce((t, l) => t + l.ids.length, 0);
  put(m, `<div class="view-intro"><p>Architecture explorer: built from ${nrel} cited relationship${nrel === 1 ? "" : "s"}. Nothing is drawn that is not an edge in the graph.</p></div>`);
  const seg = [["logical", "Logical view"], ["data", "Data flow"], ["deployment", "Deployment view"]];
  put(m, `<section class="card overview-card"><div class="toolbar"><div class="segmented" role="tablist">${seg.map(([k, l]) => `<button class="${k === mode ? "active" : ""}" role="tab" data-mode="${k}">${l}</button>`).join("")}<button disabled title="No runtime data was collected: this scan is static" class="disabled">Runtime view</button></div><div class="toolbar-right"><select class="filter" id="archShow" aria-label="Show"><option value="all">All components</option><option value="app">Applications</option><option value="db">Data stores</option><option value="queue">Messaging</option><option value="ext">External systems</option><option value="bad">Unresolved only</option></select>${declN ? `<label class="tiny" style="display:inline-flex;gap:6px;align-items:center"><input type="checkbox" id="archDecl"${decl ? " checked" : ""}> declared libraries (${declN})</label>` : ""}<input class="mini-search" id="archSearch" placeholder="Search in architecture..." aria-label="Search in architecture"><button class="ghost" id="zoomOut" aria-label="Zoom out">−</button><button class="ghost" id="zoomVal" aria-label="Fit to width">100%</button><button class="ghost" id="zoomIn" aria-label="Zoom in">+</button></div></div></section>`);
  const legend = [["#4188ff", "Application / Service"], ["#8a63f6", "API / Interface"], ["#22b67d", "Database / Storage"], ["#f4a12a", "Queue / Topic"], ["#98a9c0", "External System"], ["#bd9df8", "Deployment Node"]].map(([c, l]) => `<span class="legend-item-row"><span class="legend-chip" style="background:${c}"></span> ${l}</span>`).join("") + `<span class="legend-item-row"><span class="line-chip"></span> Synchronous call</span><span class="legend-item-row"><span class="line-chip dashed"></span> Asynchronous flow</span><span class="legend-item-row"><span class="line-chip blue"></span> Data access</span><span class="legend-item-row"><span class="line-chip red"></span> Unresolved / ambiguous</span>`;
  put(m, `<div class="arch-layout" style="margin-top:12px"><div><section class="arch-stage" id="archStage"><div class="legend-row">${legend}</div><div class="arch-scroll" id="archScroll"><div class="arch-canvas2" id="archCanvas" style="width:${L.W}px;height:${L.H}px">${archSvg(M, L)}${M.nodes.map(n => archNodeHtml(n, n === M.C)).join("")}</div></div>${M.nodes.length < 2 ? emptyState("No relationships found", "The files read for this application show no calls, data stores, topics or deployment targets.") : ""}</section></div><aside class="card sidepanel" id="archPanel" aria-live="polite"></aside></div>
<div class="arch-bottom">
<section class="card overview-card"><div class="section-heading"><div><h2>Dependency signals</h2><p>Where the graph is incomplete or resources are shared. These are facts about the evidence, not severity ratings.</p></div></div>${risks.length ? `<table class="simple-table"><thead><tr><th>Dependency</th><th>Type</th><th>Signal</th><th>Reason</th></tr></thead><tbody>${risks.slice(0, 6).map(r => `<tr><td>${esc(r.name)}</td><td>${esc(r.type)}</td><td><span class="tag ${r.tone}">${esc(r.signal)}</span></td><td>${esc(r.reason)}</td></tr>`).join("")}</tbody></table>${risks.length > 6 ? `<p class="tiny" style="margin-top:6px">+${risks.length - 6} more, see Dependencies in the side panel.</p>` : ""}` : emptyState("Nothing flagged", "Every relationship found is matched and no resource is shared.")}</section>
<section class="card overview-card"><div class="section-heading"><div><h2>Call chains</h2><p>Longest chains of matched calls through this application</p></div></div>${chains.length ? `<div class="list">${chains.map((c, i) => `<div class="list-row"><span class="tag gray">${i + 1}</span><div><b>${esc(c.join(" → "))}</b><div class="desc">${c.length - 1} hop${c.length === 2 ? "" : "s"} · matched calls only</div></div><span></span><span class="tag gray">${c.length - 1} hop${c.length === 2 ? "" : "s"}</span></div>`).join("")}</div>` : emptyState("No matched call chains", "This application has no calls matched to another analysed application.")}</section>
<section class="card overview-card"><div class="section-heading"><div><h2>Blast radius</h2><p>Potential impact by graph reachability, not proof of breakage</p></div></div><div style="padding:8px 0 0;text-align:center"><div class="ring" style="width:170px;height:170px;margin:0 auto;${totalImpact ? `background:conic-gradient(#ff6b6b 0 ${100 * lv[0].length / totalImpact}%,#f4a12a ${100 * lv[0].length / totalImpact}% ${100 * (lv[0].length + lv[1].length) / totalImpact}%,#cad4e0 ${100 * (lv[0].length + lv[1].length) / totalImpact}% 100%)` : "background:#e9edf3"}"><div class="ring-inner"><strong style="font-size:22px">${totalImpact}</strong><span>applications</span></div></div><div class="legend" style="margin-top:14px"><div class="legend-item"><span class="dot red"></span><span>Direct dependents</span><strong>${lv[0].length}</strong></div><div class="legend-item"><span class="dot" style="background:#f4a12a"></span><span>2nd level</span><strong>${lv[1].length}</strong></div><div class="legend-item"><span class="dot" style="background:#cad4e0"></span><span>3rd level</span><strong>${lv[2].length}</strong></div></div><p class="tiny" style="margin-top:10px">Callers, topic consumers and applications sharing a data store. Within the analysed applications only.</p></div></section>
</div>`);
  wireArch(m, M, L, app, mode);
}
function archRisks(app) {
  const E = D.portfolio.graph.edges, out = [], me = "app:" + app;
  for (const e of E.filter(x => x.source === me && ["unresolved", "ambiguous"].includes(x.resolution.state))) out.push({name: nm(e.target), type: nodeSubtitle(NODES[e.target]) || human(e.type), signal: e.resolution.state, tone: e.resolution.state === "unresolved" ? "red" : "yellow", reason: (e.resolution.reason || e.resolution.reasoning || "target could not be matched").slice(0, 90)});
  const mine = E.filter(x => x.source === me && ["READS_FROM", "WRITES_TO", "PUBLISHES_TO", "CONSUMES_FROM"].includes(x.type));
  for (const x of mine) { const others = [...new Set(E.filter(y => y.target === x.target && y.source !== me && y.source.startsWith("app:")).map(y => y.source.slice(4)))]; if (others.length) out.push({name: nm(x.target), type: (NODES[x.target] || {}).type === "Topic" ? "Messaging" : "Data store", signal: "shared", tone: "blue", reason: "also used by " + others.slice(0, 3).join(", ") + (others.length > 3 ? " +" + (others.length - 3) : "")}); }
  return out.filter((r, i, a) => a.findIndex(x => x.name === r.name && x.signal === r.signal) === i).sort((a, b) => (a.signal === "unresolved" ? 0 : 1) - (b.signal === "unresolved" ? 0 : 1));
}
function wireArch(m, M, L, app, mode) {
  let sel = M.C.id, ptab = "overview", zoom = 1;
  const panel = $("#archPanel"), canvas = $("#archCanvas"), scroll = $("#archScroll"), stage = $("#archStage");
  const drawPanel = () => { panel.innerHTML = nodePanelHtml(M, sel, app, ptab); panel.querySelectorAll("[data-ptab]").forEach(b => b.addEventListener("click", () => { ptab = b.dataset.ptab; drawPanel(); })); panel.querySelectorAll("[data-edge]").forEach(b => b.addEventListener("click", () => showEdges([b.dataset.edge]))); panel.querySelectorAll("[data-evidence]").forEach(b => b.addEventListener("click", () => { const id = b.dataset.evidence; if (id.startsWith("more:") || id.startsWith("w:") || id.startsWith("api:")) return toast("Select a component with relationships first"); showNode(id); })); };
  const applyZoom = () => { canvas.style.transform = "scale(" + zoom + ")"; canvas.style.transformOrigin = "0 0"; scroll.style.height = Math.round(L.H * zoom) + 8 + "px"; $("#zoomVal").textContent = Math.round(zoom * 100) + "%"; };
  const fit = () => { const w = scroll.clientWidth - 4; zoom = Math.max(.45, Math.min(M.nodes.length <= 8 ? 1.3 : 1, +(w / L.W).toFixed(2))); applyZoom(); };
  const select = id => { sel = id; ptab = "overview"; canvas.querySelectorAll("[data-node]").forEach(n => n.classList.toggle("sel", n.dataset.node === id)); drawPanel(); };
  canvas.querySelectorAll("[data-node]").forEach(n => { n.addEventListener("click", () => { if (n.dataset.node.startsWith("more:")) { const nd = M.byId[n.dataset.node] || M.nodes.find(x => x.id === n.dataset.node); return showEdges(nd.hiddenIds, nd.label + " (" + nd.sub + ")"); } select(n.dataset.node); }); n.addEventListener("keydown", e => { if (e.key === "Enter") n.click(); }); });
  canvas.querySelectorAll(".alink").forEach(g => { const ids = g.dataset.ids.split(" ").filter(Boolean); if (ids.length) { g.style.cursor = "pointer"; g.addEventListener("click", () => showEdges(ids)); g.addEventListener("keydown", e => { if (e.key === "Enter") showEdges(ids); }); } });
  $("#zoomIn").addEventListener("click", () => { zoom = Math.min(1.6, +(zoom + .1).toFixed(2)); applyZoom(); });
  $("#zoomOut").addEventListener("click", () => { zoom = Math.max(.4, +(zoom - .1).toFixed(2)); applyZoom(); });
  $("#zoomVal").addEventListener("click", fit);
  const sh = $("#archShow"), qs = $("#archSearch");
  const filt = () => { const kind = sh.value, t = qs.value.trim().toLowerCase(); canvas.querySelectorAll("[data-node]").forEach(n => { const nd = M.byId[n.dataset.node] || M.nodes.find(x => x.id === n.dataset.node); const isC = nd === M.C; let ok = isC || kind === "all" || nd.kind === kind || (kind === "bad" && nd.kind === "unres"); if (kind === "bad") ok = isC || nd.kind === "unres" || M.links.some(l => ["unresolved", "ambiguous"].includes(l.state) && (l.from === nd.id || l.to === nd.id)); if (t) ok = ok && (isC || (nd.label + " " + nd.sub).toLowerCase().includes(t)); n.style.opacity = ok ? 1 : .18; }); };
  sh.addEventListener("change", filt); qs.addEventListener("input", filt);
  const dc = $("#archDecl"); if (dc) dc.addEventListener("change", () => { location.hash = "#/architecture/" + encodeURIComponent(app) + "/" + mode + (dc.checked ? "/decl" : ""); });
  m.querySelectorAll("[data-mode]").forEach(b => b.addEventListener("click", () => { location.hash = "#/architecture/" + encodeURIComponent(app) + "/" + b.dataset.mode + (decl ? "/decl" : ""); }));
  drawPanel(); fit();
}
function archPortfolio(m) {
  const pick = `<div class="button-group"><label class="tiny" for="archPick">Open an application</label><select class="filter" id="archPick"><option value="">Choose…</option>${D.apps.map(a => `<option>${esc(a.name)}</option>`).join("")}</select></div>`;
  put(m, crumbs([["Architecture"]]) + pageHeading("Architecture", "The whole portfolio: how applications connect and what they share. Open one application for its diagram. Everything comes from cited graph edges.", pick) + recentLink());
  $("#archPick").addEventListener("change", e => { if (e.target.value) location.hash = "#/architecture/" + encodeURIComponent(e.target.value); });
  const shared = {};
  for (const e of D.portfolio.graph.edges) if (e.source.startsWith("app:") && ["READS_FROM", "WRITES_TO", "PUBLISHES_TO", "CONSUMES_FROM"].includes(e.type)) { const n = NODES[e.target]; if (n && !(n.attrs && n.attrs.unresolved)) (shared[e.target] = shared[e.target] || new Set()).add(e.source.slice(4)); }
  const sh = Object.entries(shared).filter(([, s]) => s.size > 1).sort((a, b) => b[1].size - a[1].size).slice(0, 12);
  const deg = D.apps.map(a => [a.name, S[a.name].rs.filter(e => e.type === "CALLS_API" || ASYNC.includes(e.type)).length + incoming(a.name).length]).sort((x, y) => y[1] - x[1]).slice(0, 12);
  put(m, `<div class="grid-2" style="grid-template-columns:1fr 1fr"><section class="card overview-card"><div class="section-heading"><div><h2>Most connected applications</h2><p>Calls and messages in and out</p></div></div><table class="simple-table"><thead><tr><th>Application</th><th>Relationships</th></tr></thead><tbody>${deg.map(([n, c]) => `<tr><td><a class="appname" href="#/architecture/${encodeURIComponent(n)}">${esc(n)}</a></td><td>${c}</td></tr>`).join("")}</tbody></table></section>
<section class="card overview-card"><div class="section-heading"><div><h2>Shared data stores and topics</h2><p>Used by more than one application, so they change together</p></div></div>${sh.length ? `<table class="simple-table"><thead><tr><th>Resource</th><th>Type</th><th>Applications</th></tr></thead><tbody>${sh.map(([id, s]) => `<tr><td>${esc(nm(id))}</td><td>${esc(NODES[id].type)}</td><td>${[...s].slice(0, 4).map(x => `<a href="#/architecture/${encodeURIComponent(x)}">${esc(x)}</a>`).join(", ")}${s.size > 4 ? " +" + (s.size - 4) : ""}</td></tr>`).join("")}</tbody></table>` : emptyState("None found", "No data store or topic is shared by more than one analysed application.")}</section></div>`);
  const FULL_MAP = D.portfolio.views.context && D.apps.length <= 12;
  if (!FULL_MAP) put(m, `<p class="tiny" style="margin-top:10px">A diagram of ${D.apps.length} applications would be unreadable, so ranked tables are shown. Open one application for its diagram.</p>`);
  if (FULL_MAP) { put(m, `<section class="card overview-card" style="margin-top:12px"><div class="section-heading"><div><h2>System context</h2><p>All analysed applications and their relationships</p></div></div><div id="ctxDiagram"></div></section>`); $("#ctxDiagram").append(diagram(D.portfolio.views.context), mermaidBtn(D.portfolio.views.context_mermaid, "context")); }
}
