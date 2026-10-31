/* findings: a finding is one control in a gap state (ISSUE, ABSENT, PARTIAL) for one application, read from aspects.json.
   List = issues (one per control) grouped by aspect, or by application; detail = v2 "Finding & Evidence" page. Severity is the
   control's own from the catalogue. No risk score, owner, CVE or status workflow exists, so none is shown. */
let _FIND = null;
function allFindings() {
  if (_FIND) return _FIND;
  const out = [];
  for (const a of D.apps) for (const asp of aspectsOf(a.name)) for (const c of asp.controls) if (c.finding)
    out.push({id: c.finding, type: c.id, app: a.name, title: c.title, state: c.state, severity: SEVL[c.severity] || "Medium", category: ASP[asp.id].title, aspect: asp.id, control: c});
  return (_FIND = out);
}
const SEVRANK = {High: 0, Medium: 1, Low: 2, Info: 3};
const findingsFor = app => allFindings().filter(f => f.app === app).sort((a, b) => SEVRANK[a.severity] - SEVRANK[b.severity] || a.title.localeCompare(b.title));
const sevTag = s => `<span class="tag ${s === "High" ? "red" : s === "Medium" ? "yellow" : s === "Low" ? "gray" : "blue"}">${esc(s)}</span>`;
function pFindings(m, query) {
  const Q = parseQuery(query), all = allFindings();
  let sev = Q.s || "", cat = Q.c || "", type = Q.t || "", text = Q.q || "", view = Q.v === "app" ? "app" : "issue";
  put(m, crumbs([["Findings"]]) + pageHeading("Findings", "One row per control that is not in place, grouped by aspect, with the applications it was raised for and the fix. “Not found” means nothing was found in the files read; the control may exist elsewhere."));
  const cats = ASPECTS.filter(w => all.some(f => f.category === w.title)).map(w => w.title);
  const seg = (id, opts, cur) => `<div class="segmented" id="${id}">${opts.map(([k, l]) => `<button data-v="${k}" class="${k === cur ? "active" : ""}">${l}</button>`).join("")}</div>`;
  put(m, `<section class="card overview-card"><div class="toolbar"><div class="tinyrow">${seg("fView", [["issue", "By issue"], ["app", "By application"]], view)}${seg("fSev", [["", "All"], ["High", "High"], ["Medium", "Medium"], ["Low", "Low"], ["Info", "Info"]], sev)}</div><div class="toolbar-right"><select class="filter" id="fCat" aria-label="Aspect"><option value="">All aspects</option>${cats.map(c => `<option${c === cat ? " selected" : ""}>${esc(c)}</option>`).join("")}</select><input class="mini-search" id="fText" placeholder="Filter issues or applications..." value="${esc(text)}" aria-label="Filter findings"></div></div><div id="fBody"></div></section>`);
  const draw = () => {
    const xs = all.filter(f => (!sev || f.severity === sev) && (!cat || f.category === cat) && (!type || f.type === type) && (!text || (f.title + " " + f.app + " " + f.category).toLowerCase().includes(text.toLowerCase())));
    const ws = workstreamsOf(xs), nIssues = ws.reduce((t, w) => t + w.issues.length, 0), nApps = new Set(xs.map(f => f.app)).size, tTitle = type && (all.find(f => f.type === type) || {title: type}).title;
    const head = `<div class="tiny" style="margin:10px 0"><b>${nIssues}</b> issue${nIssues === 1 ? "" : "s"} across <b>${nApps}</b> application${nApps === 1 ? "" : "s"} (${xs.length} findings)${type ? ` · only “${esc(tTitle)}” <button class="mini" id="clrT">Show all issues</button>` : ""}</div>`;
    const body = !xs.length ? emptyState("No finding matches", "Clear a filter to see more.") : view === "issue"
      ? ws.map(w => `<section class="ws-group">${wsHead(w, `<span class="tiny">${w.issues.length} issue${w.issues.length === 1 ? "" : "s"} · ${w.apps.size} application${w.apps.size === 1 ? "" : "s"}</span>`)}<table class="simple-table issue-table"><thead><tr><th>Severity</th><th>Issue</th><th>Applications</th><th>Fix</th></tr></thead><tbody>${w.issues.map(i => issueRow(i, !!type)).join("")}</tbody></table></section>`).join("")
      : byApp(xs);
    $("#fBody").innerHTML = head + body;
    const c = $("#clrT"); if (c) c.addEventListener("click", () => { type = ""; draw(); });
    $("#fBody").querySelectorAll("[data-type]").forEach(b => b.addEventListener("click", () => { type = b.dataset.type; draw(); }));
    history.replaceState(null, "", "#/gaps" + (sev || cat || type || text || view === "app" ? "?" + [view === "app" && "v=app", sev && "s=" + encodeURIComponent(sev), cat && "c=" + encodeURIComponent(cat), type && "t=" + encodeURIComponent(type), text && "q=" + encodeURIComponent(text)].filter(Boolean).join("&") : ""));
  };
  const wireSeg = (id, set) => $("#" + id).querySelectorAll("button").forEach(b => b.addEventListener("click", () => { set(b.dataset.v); $("#" + id).querySelectorAll("button").forEach(x => x.classList.toggle("active", x === b)); draw(); }));
  wireSeg("fView", v => { view = v; }); wireSeg("fSev", v => { sev = v; });
  $("#fCat").addEventListener("change", e => { cat = e.target.value; draw(); });
  $("#fText").addEventListener("input", e => { text = e.target.value; draw(); });
  draw();
}
/* one issue = one rule; each application chip opens that application's finding */
function issueRow(i, all) {
  const fs = i.findings.slice().sort((a, b) => a.app.localeCompare(b.app)), max = all ? fs.length : 5;
  const chips = fs.slice(0, max).map(f => `<a class="appchip" href="#/finding/${encodeURIComponent(f.id)}" title="Open this finding for ${esc(f.app)}">${esc(f.app)}</a>`).join("") + (fs.length > max ? `<button class="appchip more" data-type="${esc(i.type)}">+${fs.length - max} more</button>` : "");
  return `<tr><td>${sevTag(i.severity)}</td><td><b>${esc(i.title)}</b><div style="margin-top:4px">${[...new Set(fs.map(f => f.state))].map(cstateTag).join(" ")}</div></td><td><div class="chips"><b class="appcount">${fs.length}</b>${chips}</div></td><td><div class="fix">${esc(i.fix)}</div><div class="chips" style="margin-top:4px">${i.remedies.map(remedyChip).join("")}</div></td></tr>`;
}
function byApp(xs) {
  const by = {}; xs.forEach(f => (by[f.app] = by[f.app] || []).push(f));
  const apps = Object.keys(by).sort((a, b) => by[b].filter(f => f.severity === "High").length - by[a].filter(f => f.severity === "High").length || by[b].length - by[a].length || a.localeCompare(b));
  return apps.slice(0, 50).map(n => { const fs = by[n].sort((a, b) => SEVRANK[a.severity] - SEVRANK[b.severity] || a.title.localeCompare(b.title)), hi = fs.filter(f => f.severity === "High").length;
    return `<details class="app-group"${apps.length <= 3 ? " open" : ""}><summary><span class="appname">${esc(n)}</span><span class="tiny">${fs.length} finding${fs.length === 1 ? "" : "s"}${hi ? " · " + hi + " high" : ""}</span><a class="linkbtn" href="#/assessment/${encodeURIComponent(n)}">Assessment ${icon("arrow-right")}</a></summary>${appFindingGroups(fs)}</details>`; }).join("") + (apps.length > 50 ? `<p class="tiny" style="margin-top:8px">First 50 of ${apps.length} applications. Narrow the filters to see the rest.</p>` : "");
}
/* one application's findings, grouped by workstream: used by Findings (by application), Discovery and Assessment */
function appFindingGroups(fs, max) {
  if (!fs.length) return emptyState("No findings", "No rule flagged this application.");
  return workstreamsOf(fs).map(w => `<div class="ws-block">${wsHead(w)}${w.issues.slice(0, max || 99).map(i => { const f = i.findings[0]; return `<a class="issue-line" href="#/finding/${encodeURIComponent(f.id)}">${sevTag(i.severity)}<span class="row-main">${esc(i.title)}</span>${i.remedies.slice(0, 1).map(remedyChip).join("")}</a>`; }).join("")}${max && w.issues.length > max ? `<div class="tiny" style="padding:4px 0 0 36px">+${w.issues.length - max} more</div>` : ""}</div>`).join("");
}
/* what the detail page needs, read from the control: what was found, how it was decided, evidence, what is unproven, the fix */
function findingDetail(f) {
  const c = f.control, fx = fixOf(f), ev = (c.evidence || []).map(e => ({e, status: e.status || "CONFIRMED", note: ""}));
  const missing = [];
  if (c.state === "ABSENT") missing.push("Whether it exists outside this repository (a shared pipeline, platform team, remote CI template or platform repository)");
  if (c.level !== "enforced" && c.level !== "verified") missing.push("Whether it runs and is enforced, not only configured");
  missing.push("Behaviour at run time: nothing was built, run or queried");
  return {summary: c.summary, rule: `${c.id} is ${(CSTATE[c.state] || [, c.state])[1].toLowerCase()}: ${D.catalogue.states[c.state] || ""}${c.facts.length ? " Read from " + c.facts.join(", ") + "." : ""}`,
    description: ev.length ? "The lines this decision was read from." : "This finding rests on the absence of a fact: the files were searched and nothing was found.",
    ev, why: [c.summary].concat(c.facts.map(p => "fact: " + p)), missing, remed: [c.fix || fx.fix], refs: [], fx};
}
function pFinding(m, id) {
  const f = allFindings().find(x => x.id === id);
  if (!f) { put(m, crumbs([["Findings", "#/gaps"], ["Unknown finding"]]) + emptyState("Unknown finding", "It may belong to a different analysis. Return to the list.")); return; }
  CUR = f.app; const a = APPS[f.app], d = findingDetail(f);
  const mix = {CONFIRMED: 0, INFERRED: 0, NOT_FOUND: 0, UNKNOWN: 0}; d.ev.forEach(x => { const k = ["CONFIRMED", "INFERRED", "NOT_FOUND"].includes(x.status) ? x.status : "UNKNOWN"; mix[k]++; });
  const tot = d.ev.length, sim = allFindings().filter(x => x.type === f.type && x.app !== f.app);
  const bannerTone = f.severity === "High" ? "red" : f.severity === "Medium" ? "yellow" : "blue";
  put(m, crumbs([["Findings", "#/gaps"], [f.title]]));
  put(m, `<div class="banner-critical" style="${f.severity === "High" ? "" : "background:#fff7e7;border-color:#f6d9a0;color:#8a5a00"}"><div><span class="tag ${bannerTone}" style="margin-right:10px">${esc(f.severity)}</span> ${f.severity === "High" ? "A high-severity control is not in place. Verify the facts below before planning work." : "A control is not fully in place. It is an observation from the files read, not an incident."}</div><div>Finding &nbsp;<b>${esc(f.type)}</b></div></div>`);
  put(m, `<div class="finding-layout"><div><section class="card finding-main"><div class="entity-head" style="margin-bottom:0"><div><h1>${esc(f.title)}</h1><p>${esc(d.summary)}</p></div><div class="last-updated">Analysed<br><b>${esc(fmtDate(D.generated))}</b></div></div><div class="title-kv"><div class="meta-item"><b>Aspect</b><span>${esc(f.category)}</span></div><div class="meta-item"><b>Application</b><span><a href="#/app/${encodeURIComponent(f.app)}/overview">${esc(f.app)}</a></span></div><div class="meta-item"><b>Owner</b><span>${[].concat((a.discovery.identity.owners || {}).value || []).length ? esc(fmt(a.discovery.identity.owners.value)) : '<span class="tiny">not found</span>'}</span></div><div class="meta-item"><b>Status</b><span>${cstateTag(f.state)}</span></div><div class="meta-item"><b>Same finding</b><span><b style="font-size:24px;color:#20395e">${sim.length + 1}</b> application${sim.length ? "s" : ""}</span></div><div class="meta-item"><b>Evidence items</b><span>${tot}</span></div></div></section>
<section class="card overview-card" style="margin-top:12px"><div class="section-heading"><div><h2>Finding details</h2></div></div><div class="detail-grid"><div class="detail-card"><h4>What was found</h4><p>${esc(d.summary)}</p></div><div class="detail-card"><h4>How it was decided</h4><p>${esc(d.rule || d.description)}</p></div><div class="detail-card"><h4>Business impact</h4><p>${esc((APPS[f.app].aspects.context.business_criticality || {}).headline || "Not assessed. Business criticality is never inferred from technology.")}</p></div><div class="detail-card"><h4>Recommended fix</h4><p>${esc(d.fx.fix)}</p></div></div></section>
<section class="card overview-card evidence-section"><div class="section-heading"><div><h2>Evidence</h2><p>${esc(d.description)}</p></div></div>${tot ? `<table class="evidence-table"><thead><tr><th>File path</th><th>Line</th><th>Observation</th><th>Status</th><th>Freshness</th></tr></thead><tbody>${d.ev.slice(0, 25).map(x => `<tr><td style="overflow-wrap:anywhere">${esc(x.e.path || x.e.cmd || "")}</td><td>${esc(x.e.line_start || "")}</td><td><code>${esc((x.e.snippet || "").slice(0, 160))}</code>${x.note ? `<br><span class="muted-note">${esc(x.note)}</span>` : ""}</td><td><span class="tag ${x.status === "CONFIRMED" ? "green" : x.status === "INFERRED" ? "violet" : "gray"}">${esc(x.status.toLowerCase().replace("_", " "))}</span></td><td>Analysed ${esc(D.generated.slice(0, 10))}</td></tr>`).join("")}</tbody></table>${tot > 25 ? `<p class="tiny" style="margin-top:6px">First 25 of ${tot}.</p>` : ""}` : emptyState("No file citation", "This finding rests on the absence of a fact: the detector searched and found nothing. See what proof is missing below.")}
<div class="support-cards"><div class="support-box yellow"><h4>Why this finding was raised</h4>${d.why.length ? `<ul class="bullet-list">${d.why.slice(0, 8).map(x => `<li>${esc(x)}</li>`).join("")}</ul>` : `<p>${esc(d.rule || d.description)}</p>`}</div><div class="support-box purple"><h4>What proof is still missing</h4><ul class="bullet-list">${d.missing.map(x => `<li>${esc(x)}</li>`).join("")}</ul></div></div></section>
<section class="card overview-card" style="margin-top:12px"><div class="section-heading"><div><h2>Remediation</h2><p>Part of the <a href="#/assessment/${encodeURIComponent(f.app)}/${encodeURIComponent(f.aspect)}">${esc(d.fx.ws.t)}</a> aspect. ${esc((D.remedy_packs[0] || {}).note || "")}</p></div></div>${remedyCards(d.fx.remedies)}${d.remed.length > 1 ? `<ul class="bullet-list" style="margin-top:10px">${d.remed.slice(1).map(x => `<li>${esc(x)}</li>`).join("")}</ul>` : ""}${sim.length ? `<div style="margin-top:12px"><div class="tiny" style="margin-bottom:6px">The same issue in ${sim.length} other application${sim.length === 1 ? "" : "s"}; one run per repository</div><div class="chips">${sim.slice(0, 30).map(x => `<a class="appchip" href="#/finding/${encodeURIComponent(x.id)}">${esc(x.app)}</a>`).join("")}${sim.length > 30 ? `<a class="appchip more" href="#/gaps?t=${encodeURIComponent(f.type)}">+${sim.length - 30} more</a>` : ""}</div></div>` : ""}</section></div>
<aside class="panel-stack"><section class="card sidebar-card"><div class="section-heading"><div><h2>Classification</h2></div></div><div class="class-list"><div class="class-row"><span class="label">Technology</span><b>${esc([val(a, "stack.language"), val(a, "stack.spring_boot_version") ? "Spring Boot" : null].filter(Boolean).join(" · ") || "—")}</b></div><div class="class-row"><span class="label">Rule</span><b>${esc(f.type)}</b></div></div></section>
<section class="card sidebar-card"><div class="section-heading"><div><h2>Evidence confidence</h2></div></div><div class="confidence-strip">${tot ? [["CONFIRMED", "#19b97d"], ["INFERRED", "#8d65f4"], ["NOT_FOUND", "#b5c0cf"], ["UNKNOWN", "#dfe5ee"]].map(([k, c]) => `<i style="width:${100 * mix[k] / tot}%;background:${c}"></i>`).join("") : `<i style="width:100%;background:#dfe5ee"></i>`}</div><div class="score-list">${[["green", "Confirmed", "CONFIRMED"], ["violet", "Inferred", "INFERRED"], ["", "Not found", "NOT_FOUND"], ["", "Unknown", "UNKNOWN"]].map(([c, l, k]) => `<div class="score-line"><span class="dot ${c}"></span><span>${l}</span><b>${mix[k]} (${tot ? Math.round(100 * mix[k] / tot) : 0}%)</b></div>`).join("")}</div></section>
<section class="card sidebar-card"><div class="section-heading"><div><h2>Quick links</h2></div></div><div class="quick-links"><a href="#/app/${encodeURIComponent(f.app)}/overview">View in application ${icon("arrow-right")}</a><a href="#/assessment/${encodeURIComponent(f.app)}">Open in Assessment ${icon("arrow-right")}</a><a href="#/architecture/${encodeURIComponent(f.app)}">Architecture explorer ${icon("arrow-right")}</a></div></section></aside></div>`);
}
