/* applications: shared table (v2 ".applications"), sorting, flagged filters, pagination. Used by the Dashboard preview and the Applications page. */
const COLS = [["Application", null], ["Technology stack", null], ["Lifecycle", 0], ["Tests", 1], ["HA", 2], ["Security", 3], ["Unmatched calls", 4], ["Evidence", null]];
const sevOf = a => cells(a).reduce((t, c) => t + (c.cls === "bad" ? 100 : c.cls === "warn" ? 10 : 0), 0);
/* share of this application's facts that were read from a cited line (CONFIRMED). A coverage figure, not a quality score. */
const _evp = {};
const evPct = a => { if (_evp[a.name] == null) { const c = evidenceMix([a]), t = Object.values(c).reduce((x, y) => x + y, 0); _evp[a.name] = t ? Math.round(100 * c.CONFIRMED / t) : 0; } return _evp[a.name]; };
function techOf(a) {
  const out = [], j = val(a, "stack.java_version"), b = val(a, "stack.spring_boot_version"), l = val(a, "stack.language");
  if (j) out.push("Java " + j); if (b) out.push("Spring Boot " + String(b).split(".").slice(0, 2).join(".")); if (l && /kotlin/.test(l)) out.push("Kotlin");
  const seen = new Set();
  for (const e of S[a.name].rs) { const n = NODES[e.target], t = n && n.attrs && n.attrs.technology; if (t && (n.type === "Database" || n.type === "MessageBroker") && !seen.has(t)) { seen.add(t); out.push(t); } }
  return out;
}
const stackHtml = (a, max) => { const t = techOf(a), shown = t.slice(0, max || 5); return t.length ? `<div class="stack">${shown.map(x => `<span>${esc(x)}</span>`).join("")}${t.length > shown.length ? `<span title="${esc(t.slice(shown.length).join(", "))}">+${t.length - shown.length}</span>` : ""}</div>` : '<span class="tiny">—</span>'; };
const cellHtml = c => `<span class="cell ${c.cls}" title="${esc(c.tip)}"><i>${esc(c.ic)}</i>${esc(c.t)}</span>`;
const kindOf = a => [val(a, "stack.artifact_kind"), val(a, "stack.language")].filter(Boolean).join(" · ");
function cmp(key, dir) {
  const mul = dir === "asc" ? 1 : -1;
  const f = key === "severity" ? a => sevOf(a) : key === "Application" ? a => a.name.toLowerCase() : key === "Technology stack" ? a => parseFloat(val(a, "stack.java_version")) || 0 : key === "Evidence" ? a => evPct(a)
    : a => { const c = cells(a)[COLS.find(x => x[0] === key)[1]]; return (SEV[c.cls] || 0) * 1000 + (key === "Unmatched calls" ? S[a.name].un : key === "Tests" ? S[a.name].tot - S[a.name].mapped : 0); };
  return (x, y) => { const p = f(x), q = f(y); return p < q ? -mul : p > q ? mul : x.name.localeCompare(y.name); };
}
function appRow(a) {
  const cs = cells(a), href = "#/app/" + encodeURIComponent(a.name) + "/overview", p = evPct(a);
  return `<tr tabindex="0" data-go="${esc(href)}"><td><a class="appname" href="${esc(href)}"><span class="appicon">${icon(val(a, "stack.artifact_kind") === "library" ? "package" : "box")}</span>${esc(a.name)}</a><div class="tiny" style="margin-left:34px">${esc(kindOf(a))}</div></td><td>${stackHtml(a)}</td>${cs.slice(0, 5).map(c => `<td>${cellHtml(c)}</td>`).join("")}<td><span class="progress" title="Share of this application's facts read from a cited line"><i style="width:${p}%"></i></span>${p}%</td></tr>`;
}
function appTable(rows, st) {
  const head = COLS.map(([k, ci]) => {
    const flagged = ci != null ? D.apps.filter(a => cells(a)[ci].flag).length : 0, on = st.sort === k;
    const label = st.noSort ? esc(k) : `<button class="thb" data-sort="${esc(k)}">${esc(k)}${on ? (st.dir === "asc" ? " ▲" : " ▼") : ""}</button>`;
    return `<th scope="col" aria-sort="${on ? (st.dir === "asc" ? "ascending" : "descending") : "none"}">${label}${ci != null && flagged && st.onFlag ? `<button class="thf${st.flags && st.flags.includes(k) ? " on" : ""}" data-flag="${esc(k)}" title="Show only the ${flagged} flagged">${flagged} flagged</button>` : ""}</th>`;
  }).join("");
  const body = rows.length ? rows.map(appRow).join("") : `<tr><td colspan="${COLS.length}"><div class="empty">No application matches the current filters.</div></td></tr>`;
  const wrap = htmlEl(`<div class="table-scroll"><table class="applications"><thead><tr>${head}</tr></thead><tbody>${body}</tbody></table></div>`);
  wrap.querySelectorAll("[data-sort]").forEach(b => b.addEventListener("click", ev => { ev.stopPropagation(); st.onSort && st.onSort(b.dataset.sort); }));
  wrap.querySelectorAll("[data-flag]").forEach(b => b.addEventListener("click", ev => { ev.stopPropagation(); st.onFlag && st.onFlag(b.dataset.flag); }));
  return wrap;
}
function parseQuery(q) { const o = {}; (q || "").split("&").filter(Boolean).forEach(kv => { const [k, v] = kv.split("="); o[k] = decodeURIComponent(v || ""); }); return o; }
function pApps(m, query) {
  const Q = parseQuery(query);
  const st = {flags: [], sort: Q.s || "severity", dir: Q.d || "desc", q: Q.q || "", page: +(Q.p || 1)};
  let fl = (Q.f || "").split(",").filter(Boolean);
  const save = () => { const parts = []; if (fl.length) parts.push("f=" + encodeURIComponent(fl.join(","))); if (st.q) parts.push("q=" + encodeURIComponent(st.q)); if (st.sort !== "severity" || st.dir !== "desc") parts.push("s=" + encodeURIComponent(st.sort), "d=" + st.dir); history.replaceState(null, "", "#/apps" + (parts.length ? "?" + parts.join("&") : "")); };
  const holder = h("div", {}), chips = h("div", {class: "chips"}), info1 = h("div", {class: "tiny"}), pager = h("div", {class: "pager"});
  const colOf = {Lifecycle: "lifecycle", Tests: "tests", HA: "ha", Security: "security", "Unmatched calls": "unmatched"};
  const search = h("input", {type: "search", placeholder: "Filter " + D.apps.length + " applications by name, language or version…", value: st.q, class: "tsearch", "aria-label": "Filter applications"});
  const draw = () => {
    const tests = fl.map(filterTest); let xs = D.apps.filter(a => tests.every(t => t(a)) && (!st.q || [a.name, val(a, "stack.language"), val(a, "stack.java_version"), val(a, "stack.spring_boot_version")].join(" ").toLowerCase().includes(st.q.toLowerCase())));
    xs.sort(cmp(st.sort, st.dir));
    const pages = Math.max(1, Math.ceil(xs.length / PAGE)); st.page = Math.min(st.page, pages);
    const slice = xs.slice((st.page - 1) * PAGE, st.page * PAGE);
    st.flags = fl.map(f => Object.keys(colOf).find(k => colOf[k] === f)).filter(Boolean);
    chips.replaceChildren(...Object.entries(FILTERS).filter(([k]) => !["ended", "extended"].includes(k)).map(([k, [l]]) => h("button", {class: "chipbtn" + (fl.includes(k) ? " on" : ""), onclick: () => { fl = fl.includes(k) ? fl.filter(x => x !== k) : fl.concat(k); st.page = 1; draw(); }}, l, " ", h("small", {}, D.apps.filter(FILTERS[k][1]).length))),
      ...fl.filter(f => !FILTERS[f] || ["ended", "extended"].includes(f)).map(f => h("button", {class: "chipbtn on", onclick: () => { fl = fl.filter(x => x !== f); draw(); }}, filterLabel(f), " ✕")));
    info1.replaceChildren("Showing ", h("b", {}, xs.length), " of " + D.apps.length + " applications", ...((fl.length || st.q) ? [h("button", {class: "mini", style: "margin-left:10px", onclick: () => { fl = []; st.q = ""; search.value = ""; st.page = 1; draw(); }}, "Clear filters")] : []));
    holder.replaceChildren(appTable(slice, Object.assign(st, {onSort: k => { if (st.sort === k) st.dir = st.dir === "asc" ? "desc" : "asc"; else { st.sort = k; st.dir = k === "Application" || k === "Technology stack" ? "asc" : "desc"; } draw(); },
      onFlag: k => { const f = colOf[k]; fl = fl.includes(f) ? fl.filter(x => x !== f) : fl.concat(f); st.page = 1; draw(); }})));
    pager.replaceChildren(h("span", {class: "tiny"}, xs.length ? (st.page - 1) * PAGE + 1 + "–" + Math.min(st.page * PAGE, xs.length) + " of " + xs.length : ""), h("span", {class: "tinyrow"}, h("button", {class: "mini", disabled: st.page <= 1, onclick: () => { st.page--; draw(); }}, "‹ Prev"), h("span", {class: "tiny"}, "Page " + st.page + " / " + pages), h("button", {class: "mini", disabled: st.page >= pages, onclick: () => { st.page++; draw(); }}, "Next ›")));
    pager.hidden = pages <= 1; save();
  };
  search.addEventListener("input", () => { st.q = search.value; st.page = 1; draw(); });
  draw();
  put(m, crumbs([["Applications"]]) + pageHeading("All applications", "Worst first. Click a column heading to sort, a “flagged” count to filter, a row to open it.") + recentLink());
  const card = h("section", {class: "card apps-panel"}, h("div", {style: "margin-bottom:10px"}, search), chips, h("div", {style: "margin:10px 0"}, info1), holder, pager);
  m.append(card);
}
