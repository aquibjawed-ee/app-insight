/* aspects: the one taxonomy every page reads. Per application, aspects.json carries aspects -> controls -> evidence -> finding -> remedy;
   D.catalogue carries the aspect list, order and state meanings. Nothing is decided in the browser: states, severities and remedies
   come from the engine and the client's remedy packs. */
const ASPECTS = D.catalogue.aspects;
const ASP = Object.fromEntries(ASPECTS.map(a => [a.id, a]));
const aspectsOf = name => APPS[name].aspects.aspects;
const controlsOf = name => aspectsOf(name).flatMap(a => a.controls);
const ASTATUS = {issues: ["red", "Issues"], gaps: ["yellow", "Gaps"], in_place: ["green", "In place"], in_place_partly_checked: ["teal", "In place where checked"], not_assessed: ["gray", "Not assessed"], not_applicable: ["gray", "N/A"]};
const CSTATE = {PRESENT: ["green", "In place"], PARTIAL: ["yellow", "Partial"], ABSENT: ["red", "Not found"], ISSUE: ["red", "Issue"], UNKNOWN: ["gray", "Unknown"], NOT_APPLICABLE: ["gray", "N/A"], NOT_ASSESSED: ["gray", "Not assessed"]};
const SEVL = {high: "High", medium: "Medium", low: "Low", info: "Info"};
const statusTag = s => `<span class="tag ${(ASTATUS[s] || ASTATUS.not_assessed)[0]}">${(ASTATUS[s] || ASTATUS.not_assessed)[1]}</span>`;
const cstateTag = s => `<span class="tag ${(CSTATE[s] || CSTATE.UNKNOWN)[0]}" title="${esc(D.catalogue.states[s] || "")}">${(CSTATE[s] || CSTATE.UNKNOWN)[1]}</span>`;
const wsOfAspect = id => { const a = ASP[id] || {id, title: id, icon: "pie", question: "", why_first: ""}; return {k: a.id, t: a.title, ic: a.icon, goal: a.question, why: a.why_first, order: a.order}; };
/* a remedy from a pack, in the shape the pages use: k is unique across packs */
const normR = r => ({k: r.pack + ":" + r.key, cmd: r.cmd, t: r.title, d: r.does, pack: r.pack});
const remedyChip = r => r.cmd ? `<code class="cmd" title="${esc(r.d)}">${esc(r.cmd)}</code>` : `<span class="tag gray" title="${esc(r.d)}">${esc(r.t)}</span>`;
const remedyCards = rs => rs.length ? `<div class="remedy-grid">${rs.map((r, i) => `<div class="remedy-card${i ? "" : " lead"}">${r.cmd ? `<code class="cmd">${esc(r.cmd)}</code>` : '<span class="tag gray">manual step</span>'}<b>${esc(r.t)}</b><p>${esc(r.d)}</p></div>`).join("")}</div>` : "";
const fixOf = f => ({ws: wsOfAspect(f.aspect), remedies: (f.control.remedies || []).map(normR), fix: f.control.fix});
/* findings -> aspects -> issues (one per control) and remedies (one per pack entry), each with the applications affected */
function workstreamsOf(fs) {
  const by = {};
  for (const f of fs) {
    const x = fixOf(f), w = by[x.ws.k] = by[x.ws.k] || {ws: x.ws, issues: {}, remedies: {}, apps: new Set(), high: 0};
    const i = w.issues[f.type] = w.issues[f.type] || {type: f.type, title: f.title, severity: f.severity, fix: x.fix, remedies: x.remedies, findings: []};
    i.findings.push(f); w.apps.add(f.app); if (f.severity === "High") w.high++;
    if (SEVRANK[f.severity] < SEVRANK[i.severity]) i.severity = f.severity;
    x.remedies.forEach((r, n) => { const e = w.remedies[r.k] = w.remedies[r.k] || Object.assign({apps: new Set(), issues: new Set(), main: false}, r); e.apps.add(f.app); e.issues.add(f.title); if (!n) e.main = true; });
  }
  return Object.values(by).sort((a, b) => a.ws.order - b.ws.order).map(x => { x.issues = Object.values(x.issues).sort((a, b) => SEVRANK[a.severity] - SEVRANK[b.severity] || b.findings.length - a.findings.length || a.title.localeCompare(b.title)); x.remedies = Object.values(x.remedies).sort((a, b) => b.main - a.main || !!b.cmd - !!a.cmd || b.apps.size - a.apps.size); return x; });
}
const wsHead = (w, right, short) => `<div class="ws-head"><span class="small-icon ws-${w.ws.k}">${icon(w.ws.ic)}</span><div><b>${esc(w.ws.t)}</b>${short ? "" : `<div class="tiny">${esc(w.ws.goal)}</div>`}</div>${right || ""}</div>`;
/* aspect rollup across applications: how many are in each status */
function aspectCounts(apps, id) { const c = {issues: 0, gaps: 0, in_place: 0, in_place_partly_checked: 0, not_assessed: 0, not_applicable: 0}; apps.forEach(a => { const x = aspectsOf(a.name).find(y => y.id === id); c[x ? x.status : "not_assessed"]++; }); return c; }
const coverageText = a => { const c = a.coverage; return c.applicable ? `${c.present} of ${c.applicable} in place${c.applicable - c.assessed ? " · " + (c.applicable - c.assessed) + " not assessed" : ""}` : "does not apply"; };
