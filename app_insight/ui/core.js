/* core: DOM helper, data indexes, per-application numbers, filters, insights, evidence drawer. Layout lives in the screen modules. */
const esc = v => String(v == null ? "" : v).replace(/[&<>"']/g, c => ({"&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;"}[c]));
const $ = (s, r) => (r || document).querySelector(s);
function h(tag, attrs, ...kids) {
  const e = document.createElement(tag);
  for (const [k, v] of Object.entries(attrs || {})) { if (v == null || v === false) continue; if (k === "class") e.className = v; else if (k.startsWith("on")) e.addEventListener(k.slice(2), v); else e.setAttribute(k, v === true ? "" : v); }
  for (const c of kids.flat(9)) if (c != null && c !== false) e.append(c.nodeType ? c : document.createTextNode(String(c)));
  return e;
}
const svgBox = (svg, fit) => { const d = h("div", {class: "diagram" + (fit ? " fit" : "")}); d.innerHTML = svg; return d; }; // svg is escaped by graph.c4
const NODES = Object.fromEntries(D.portfolio.graph.nodes.map(n => [n.id, n]));
const EDGES = Object.fromEntries(D.portfolio.graph.edges.map(e => [e.id, e]));
const APPS = Object.fromEntries(D.apps.map(a => [a.name, a]));
const human = s => s.replace(/_/g, " ");
const nm = id => (NODES[id] ? NODES[id].name : id);
const info = t => h("i", {class: "info-i", tabindex: "0", "data-tip": t, "aria-label": t}, "i");
/* status vocabulary -> v2 tag colours. One place to change how states look. */
const TONE = {resolved: "ok", confirmed: "ok", assessed: "ok", yes: "ok", concern: "bad", unresolved: "bad", attention: "warn", ambiguous: "warn", partial: "warn", inferred: "warn", declared: "warn", unknown: "none", not_assessed: "none", not_applicable: "none", no: "none", info: "info", static_configured: "ok", mapped_with_assertions: "ok", mapped_no_assertion_seen: "warn", unverified: "none", CONFIRMED: "ok", INFERRED: "warn", NOT_FOUND: "none", UNKNOWN: "none", observed_runtime: "ok"};
const TAGCLS = {ok: "green", warn: "yellow", bad: "red", info: "blue", none: "gray"};
const GL = {ok: "✓", warn: "▲", bad: "!", none: "–", info: "•"};
const LBL = {not_assessed: "not assessed", not_applicable: "n/a", mapped_with_assertions: "mapped · assertion", mapped_no_assertion_seen: "mapped · no assertion", static_configured: "configured", NOT_FOUND: "not found", UNKNOWN: "unknown", CONFIRMED: "confirmed", INFERRED: "inferred", observed_runtime: "observed"};
const tagS = (tone, text, title) => `<span class="tag ${TAGCLS[tone] || "gray"}"${title ? ` title="${esc(title)}"` : ""}>${esc(text)}</span>`;
const pill = (k, t) => { const tone = TONE[k] || "none"; return h("span", {class: "tag " + TAGCLS[tone], title: k}, t || LBL[k] || human(k)); };
const tone = (cls, text, icon) => h("span", {class: "tag " + (TAGCLS[cls] || "gray")}, icon ? icon + " " : "", text);
const htmlEl = html => { const d = document.createElement("div"); d.innerHTML = html; return d.firstElementChild || d; };
function fmt(v) { if (v == null) return "—"; if (typeof v === "boolean") return v ? "yes" : "no"; if (Array.isArray(v)) return v.length ? v.map(x => (x && typeof x === "object") ? (x.technology || x.name || x.target || x.path || fmt(x)) : String(x)).join(", ") : "none"; if (typeof v === "object") return Object.entries(v).filter(([, x]) => x != null).map(([k, x]) => k + ": " + fmt(x)).join("; ") || "—"; return String(v); }
function evList(evs) { if (!evs || !evs.length) return h("div", {class: "tiny"}, "No file citation (derived or not found)."); return h("div", {}, evs.map(e => e.kind === "file" ? h("div", {}, h("div", {class: "tiny"}, (e.app ? e.app + " · " : "") + e.path), h("pre", {}, e.snippet)) : h("pre", {}, e.cmd + "\n" + e.snippet))); }
function factRow(label, f) { const row = h("div", {class: "row"}, h("div", {class: "k"}, label), h("div", {class: "v"}, fmt(f.value), f.note ? h("div", {class: "tiny"}, f.note) : null), pill(f.status)); return f.evidence && f.evidence.length ? h("div", {}, row, h("details", {}, h("summary", {}, "Evidence (" + f.evidence.length + ")"), evList(f.evidence))) : row; }
const val = (a, p) => { const [s, k] = p.split("."); return ((a.discovery[s] || {})[k] || {}).value; };
const dim = (a, k) => a.dimensions.dimensions[k];

/* ---------- derived per-application numbers ---------- */
function relEdges(app) { return D.portfolio.graph.edges.filter(e => e.source === "app:" + app && e.type !== "CONTAINS"); }
function incoming(app) {
  const mine = "app:" + app, out = [], E = D.portfolio.graph.edges;
  for (const e of E) if (e.type === "CALLS_API" && e.source !== mine && (e.target === mine || (NODES[e.target] && NODES[e.target].app === app))) out.push({e, why: "calls this application"});
  const pubs = new Set(E.filter(e => e.source === mine && e.type === "PUBLISHES_TO").map(e => e.target));
  for (const e of E) if (e.type === "CONSUMES_FROM" && pubs.has(e.target) && e.source !== mine) out.push({e, why: "consumes " + nm(e.target)});
  return out;
}
const S = {};
for (const a of D.apps) {
  const sn = a.safetynet.summary, tot = Object.values(sn).reduce((s, v) => s + v.mapped_with_assertions + v.mapped_no_assertion_seen + v.unverified, 0), mapped = Object.values(sn).reduce((s, v) => s + (v.direct != null ? v.direct : v.mapped_with_assertions + v.mapped_no_assertion_seen), 0), classLevel = Object.values(sn).reduce((s, v) => s + (v.class_level || 0), 0);
  const rs = relEdges(a.name), un = rs.filter(e => ["unresolved", "ambiguous"].includes(e.resolution.state)).length;
  S[a.name] = {tot, mapped, classLevel, rs, un, eps: D.portfolio.graph.nodes.filter(n => n.type === "ApiEndpoint" && n.app === a.name).length, blocking: a.discovery.gaps_and_risks.filter(g => g.severity === "BLOCKING").length, mat: a.discovery.maturity};
}
/* one row model per application: the same cells feed the table, the app tiles and the sort/filter logic */
const SEV = {bad: 3, warn: 2, info: 0, none: 1, ok: 0};
function cells(a) {
  const s = S[a.name], lc = dim(a, "technology_lifecycle"), sec = dim(a, "security_exposure"), res = dim(a, "operational_resilience"), java = val(a, "stack.java_version"), boot = val(a, "stack.spring_boot_version");
  const jst = (lc.values.java || {}).status, bend = (lc.values.spring_boot || {}).oss_status === "ended";
  const jv = (lc.values.java || {}).version, iss = [];
  if (jst === "out_of_support") iss.push("Java " + jv + " ended"); else if (jst === "extended_support_only") iss.push("Java " + jv + " extended only");
  if (bend) iss.push("Boot " + (boot || "?").split(".").slice(0, 2).join(".") + " ended");
  const lifeText = iss.length ? iss.join(" · ") : lc.state === "unknown" ? "version unknown" : (java ? "Java " + java : "") + " supported";
  const ha = res.values || {}, haN = (ha.present || []).length, haT = haN + (ha.absent || []).length + (ha.unknown || []).length;
  return [
    {k: "Lifecycle", cls: lc.level === "concern" ? "bad" : lc.level === "attention" ? "warn" : lc.state === "unknown" ? "none" : "ok", ic: lc.level === "concern" ? "!" : lc.level === "attention" ? "▲" : lc.state === "unknown" ? "?" : "✓",
      t: lifeText, tip: lc.headline, tab: "overview", flag: ["concern", "attention"].includes(lc.level), flagText: lc.level === "concern" ? "ended" : "extended"},
    {k: "Tests", cls: !s.tot ? "none" : s.mapped === s.tot ? "ok" : "warn", ic: !s.tot ? "–" : s.mapped === s.tot ? "✓" : "◐", t: s.tot ? s.mapped + "/" + s.tot + " mapped" + (s.classLevel ? " +" + s.classLevel + " by class" : "") : "nothing to map", tip: dim(a, "safety_net_strength").headline, tab: "safety", flag: s.tot > s.mapped},
    {k: "HA", cls: res.state === "not_assessed" ? "none" : res.level === "attention" ? "warn" : "ok", ic: res.state === "not_assessed" ? "–" : res.level === "attention" ? "▲" : "✓", t: res.state === "not_assessed" ? "no deploy files" : haN + "/" + haT + " checks", tip: res.headline, tab: "resilience", flag: res.state !== "not_assessed" && res.level === "attention"},
    {k: "Security", cls: sec.state === "assessed" ? (sec.level === "concern" ? "bad" : sec.level === "attention" ? "warn" : "ok") : "none", ic: sec.state === "assessed" ? "✓" : "–", t: sec.state === "assessed" ? "scanned" : "not scanned", tip: sec.headline, tab: "delivery", flag: sec.state !== "assessed"},
    {k: "Unmatched calls", cls: !s.rs.length ? "none" : s.un ? "warn" : "ok", ic: !s.rs.length ? "–" : s.un ? "?" : "✓", t: !s.rs.length ? "none found" : s.un ? s.un + " unmatched" : "all matched", tip: s.un ? s.un + " call(s) or message(s) could not be matched to a known application" : "Every call and message is matched or goes to an external system", tab: "integrations", flag: s.un > 0},
    {k: "Maturity", cls: "info", ic: "◔", t: Math.round(s.mat.score) + "%", tip: "Engineering practice: " + s.mat.band + " (" + s.mat.score + "%). Not a risk score.", tab: "checklist", flag: false}];
}
const lifeLevel = a => dim(a, "technology_lifecycle").level;

/* ---------- drawer ---------- */
const drawer = $("#drawer"), scrim = $("#scrim");
let lastFocus = null;
function closeDrawer() { drawer.classList.remove("open"); scrim.classList.remove("on"); drawer.setAttribute("aria-hidden", "true"); if (lastFocus && document.contains(lastFocus)) lastFocus.focus(); }
function openDrawer(title, ...body) { lastFocus = document.activeElement; drawer.replaceChildren(h("button", {class: "btn", onclick: closeDrawer}, "✕ Close"), h("h2", {}, title), ...body); drawer.classList.add("open"); scrim.classList.add("on"); drawer.setAttribute("aria-hidden", "false"); }
scrim.addEventListener("click", closeDrawer);
function edgeSentence(e) { const a = e.attrs || {}; return human(e.type).toLowerCase() + ": " + nm(e.source) + " → " + nm(e.target) + (a.method || a.path ? " " + (a.method || "") + " " + (a.path || "") : ""); }
function edgeBlock(e) {
  const r = e.resolution || {}, a = e.attrs || {};
  const kv = [["Found by", human(e.mechanism)], ["Basis", human(e.basis)], ["Confidence", e.confidence], ["Resolution", r.state + (r.strength ? " · " + r.strength + " identity" : "")]];
  const o = [h("h3", {style: "margin-top:12px"}, edgeSentence(e)), h("div", {class: "chips", style: "margin:8px 0"}, pill(r.state || "resolved"), pill(e.basis), pill(e.status)), ...kv.map(([k, v]) => h("div", {class: "row"}, h("div", {class: "k"}, k), h("div", {class: "v"}, v)))];
  if (r.reasoning || r.reason) o.push(h("p", {style: "margin-top:8px"}, h("b", {}, "Why: "), r.reasoning || r.reason));
  if (r.candidates) o.push(h("p", {}, h("b", {}, "Candidates (none chosen): "), r.candidates.map(nm).join(", ")));
  if (a.endpoint_note) o.push(h("p", {}, h("b", {}, "Contract: "), a.endpoint_note));
  if (e.note) o.push(h("p", {class: "tiny"}, e.note));
  o.push(h("h3", {style: "margin-top:12px"}, "Evidence"), evList(e.evidence));
  if (r.matched_evidence && r.matched_evidence.length) o.push(h("h3", {style: "margin-top:12px"}, "Identity evidence used"), evList(r.matched_evidence));
  return o;
}
function showEdges(ids, title) { const es = ids.map(i => EDGES[i]).filter(Boolean); openDrawer(title || es.length + " relationship" + (es.length === 1 ? "" : "s"), ...es.slice(0, 25).map(e => h("section", {}, edgeBlock(e))), es.length > 25 ? h("p", {class: "tiny"}, (es.length - 25) + " more not shown") : null); }
function showNode(id) { const n = NODES[id]; if (!n) return; const rel = D.portfolio.graph.edges.filter(e => e.source === id || e.target === id);
  openDrawer(n.name, pill("info", n.type), n.type === "Application" ? h("div", {}, h("h3", {style: "margin-top:12px"}, "Identity keys"), (n.attrs.identity_keys || []).map(k => h("div", {class: "row"}, h("div", {class: "k"}, k.kind), h("div", {class: "v"}, k.value + " · " + k.strength)))) : null,
    h("h3", {style: "margin-top:12px"}, "Relationships (" + rel.length + ")"), ...rel.slice(0, 40).map(e => h("div", {class: "item"}, h("div", {class: "body"}, h("div", {class: "d"}, edgeSentence(e))), pill(e.resolution.state), h("button", {class: "mini", onclick: () => showEdges([e.id])}, "Evidence"))),
    h("h3", {style: "margin-top:12px"}, "Evidence"), evList(n.evidence)); }
function wireSvg(root) {
  root.querySelectorAll(".edge").forEach(g => { const f = () => showEdges(g.dataset.edgeIds.split(" ").filter(Boolean)); g.addEventListener("click", f); g.addEventListener("keydown", e => { if (e.key === "Enter") f(); }); });
  root.querySelectorAll(".node[data-node]").forEach(g => { const f = () => { const id = g.dataset.node; if (id.startsWith("app:") && APPS[id.slice(4)]) location.hash = "#/app/" + id.slice(4) + "/overview"; else showNode(id); }; g.addEventListener("click", f); g.addEventListener("keydown", e => { if (e.key === "Enter") f(); }); });
}
function diagram(svg, opts) {
  opts = opts || {};
  const box = svgBox(svg, true), tog = h("input", {type: "checkbox"}), fitb = h("button", {class: "mini"}, "Actual size");
  tog.addEventListener("change", () => box.classList.toggle("hide-unres", tog.checked));
  fitb.addEventListener("click", () => { const f = box.classList.toggle("fit"); fitb.textContent = f ? "Actual size" : "Fit to width"; });
  wireSvg(box);
  return h("div", {}, h("div", {class: "dtool"}, h("label", {class: "tiny"}, tog, " Hide unresolved"), fitb, info("Click a line for its evidence, a box for details. Dashed red = unresolved or ambiguous (never guessed).")), box,
    h("div", {class: "dlegend"}, h("span", {}, h("i", {class: "sw"}), "configured"), h("span", {}, h("i", {class: "sw d"}), "inferred / declared"), h("span", {}, h("i", {class: "sw r"}), "unresolved / ambiguous")));
}

function mermaidBtn(text, name) {
  const copy = h("button", {class: "mini"}, "Copy Mermaid"), dl = h("button", {class: "mini"}, "Download .mmd");
  copy.addEventListener("click", () => { const done = () => { copy.textContent = "Copied ✓"; setTimeout(() => copy.textContent = "Copy Mermaid", 1500); };
    if (navigator.clipboard && window.isSecureContext) navigator.clipboard.writeText(text).then(done, () => fallback()); else fallback();
    function fallback() { const t = h("textarea", {style: "position:fixed;opacity:0"}); t.value = text; document.body.append(t); t.select(); try { document.execCommand("copy"); done(); } catch (e) { copy.textContent = "Copy failed"; } t.remove(); } });
  dl.addEventListener("click", () => { const url = URL.createObjectURL(new Blob([text], {type: "text/plain"})), l = h("a", {href: url, download: name + ".mmd"}); document.body.append(l); l.click(); l.remove(); setTimeout(() => URL.revokeObjectURL(url), 1000); });
  return h("div", {class: "dtool", style: "margin-top:10px"}, copy, dl, h("span", {class: "tiny"}, "Paste into mermaid.live, GitHub or GitLab markdown. The diagram above is already rendered."));
}
const goApps = f => { location.hash = "#/apps" + (f ? "?f=" + encodeURIComponent(f) : ""); };
/* filter vocabulary: every KPI, insight and chart bar deep-links into the table with one of these */
const FILTERS = {
  lifecycle: ["Support ended or extended only", a => ["concern", "attention"].includes(lifeLevel(a))], ended: ["Vendor support ended", a => lifeLevel(a) === "concern"], extended: ["Extended support only", a => lifeLevel(a) === "attention"],
  tests: ["Components with no mapped test", a => S[a.name].tot > S[a.name].mapped], ha: ["HA basics missing in deployment files", a => cells(a)[2].flag], nodeploy: ["No deployment files", a => dim(a, "operational_resilience").state === "not_assessed"],
  security: ["Not scanned for vulnerabilities", a => dim(a, "security_exposure").state !== "assessed"], unmatched: ["Has unmatched calls", a => S[a.name].un > 0]};
function filterLabel(t) { if (FILTERS[t]) return FILTERS[t][0]; const [k, v] = t.split(":"); return ({java: "Java ", boot: "Spring Boot ", lang: "Language ", db: "Data store ", broker: "Broker "}[k] || k + " ") + v; }
function filterTest(t) {
  if (FILTERS[t]) return FILTERS[t][1];
  const [k, v] = t.split(":");
  if (k === "java") return a => (val(a, "stack.java_version") || "?") === v; if (k === "boot") return a => { const b = val(a, "stack.spring_boot_version"); return (b ? b.split(".")[0] + ".x" : "none") === v; };
  if (k === "lang") return a => (val(a, "stack.language") || "unknown") === v;
  if (k === "db" || k === "broker") return a => D.portfolio.graph.edges.some(e => e.source === "app:" + a.name && NODES[e.target] && NODES[e.target].attrs && NODES[e.target].attrs.technology === v && NODES[e.target].type === (k === "db" ? "Database" : "MessageBroker"));
  return () => true;
}
function insights() {
  const A = D.apps, N = A.length, out = [], n = f => A.filter(FILTERS[f][1]).length;
  const add = (lv, f, text) => { out.push({lv, f, text}); };
  const ended = n("ended"), ext = n("extended"), un = A.filter(FILTERS.unmatched[1]), unCalls = Object.values(S).reduce((t, v) => t + v.un, 0), tests = n("tests"), unm = Object.values(S).reduce((t, v) => t + v.tot - v.mapped, 0), ha = n("ha"), nod = n("nodeploy"), sec = n("security");
  if (ended) add("bad", "ended", [h("b", {}, ended), " of " + N + " applications use a Java or Spring Boot version whose vendor support has ended"]);
  if (ext) add("warn", "extended", [h("b", {}, ext), " of " + N + " applications are only on extended (paid) vendor support"]);
  if (ha) add("warn", "ha", [h("b", {}, ha), " applications are missing replicas, anti-affinity or a disruption budget in their deployment files"]);
  if (unCalls) add("warn", "unmatched", [h("b", {}, unCalls), " calls or messages in " + un.length + (un.length === 1 ? " application" : " applications") + " could not be matched to a known application"]);
  if (tests) add("warn", "tests", [h("b", {}, tests), " applications have components with no mapped test (", h("b", {}, unm), " components in total; unverified, not untested)"]);
  if (sec) add("none", "security", [h("b", {}, sec), " of " + N + " applications have not been scanned for vulnerabilities, so exposure is unknown"]);
  if (nod) add("none", "nodeploy", [h("b", {}, nod), " applications have no deployment files in their repository, so HA could not be checked"]);
  const sharedDb = D.portfolio.graph.nodes.filter(x => x.type === "Database" && x.attrs.identity === "connection" && new Set(D.portfolio.graph.edges.filter(e => e.target === x.id && e.source.startsWith("app:")).map(e => e.source)).size > 1).length;
  if (sharedDb) out.push({lv: "info", href: "#/map", text: [h("b", {}, sharedDb), " databases are shared by more than one application, so they change together"]});
  return out;
}
