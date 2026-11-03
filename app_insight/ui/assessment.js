/* assessment: one application's aspect trace, in the order of the v2 "Assessment" mock: scorecard of aspects -> each aspect's controls
   (state, evidence level, what was found, evidence, finding, remedy) -> recommendations and missing proof -> deployment and test detail.
   No score and no weighting: an aspect's status is the worst of its controls, and "not assessed" never counts as in place. */
const ACOLOR = {red: ["#ffeff1", "#ff5365"], yellow: ["#fff7e7", "#d98c04"], green: ["#e7f9f1", "#0b8a5e"], teal: ["#e3f5f1", "#1d7f6c"], gray: ["#eef2f7", "#6a7f9a"]};
function aspectTile(name, a) {
  const c = ACOLOR[(ASTATUS[a.status] || ASTATUS.not_assessed)[0]], asp = ASP[a.id];
  return `<a class="score-tile" href="#/assessment/${encodeURIComponent(name)}/${a.id}"><div class="score-top"><span class="iconwrap" style="background:${c[0]};color:${c[1]}">${icon(asp.icon)}</span>${statusTag(a.status)}</div><h3>${esc(a.title)}</h3><p>${esc(a.question)}</p><div class="dimension-meta"><span>${esc(coverageText(a))}</span></div></a>`;
}
const LEVEL = {declared: "declared", configured: "configured", enforced: "enforced in CI", verified: "verified"};
function controlRow(name, c) {
  const ev = (c.evidence || []).length, fid = c.finding;
  return `<tr class="ctl-${c.state.toLowerCase()}"><td><b>${esc(c.title)}</b>${c.severity ? `<div style="margin-top:3px">${sevTag(SEVL[c.severity])}</div>` : ""}</td><td>${cstateTag(c.state)}${c.level ? `<div class="tiny" style="margin-top:3px">${esc(LEVEL[c.level] || c.level)}</div>` : ""}</td><td class="ctl-summary">${esc(c.summary || "")}${c.searched ? `<div class="tiny" style="margin-top:3px">${esc(searchedText(c.searched))}</div>` : ""}</td>
<td>${ev ? `<button class="mini" data-ctl="${esc(c.id)}">${ev} line${ev === 1 ? "" : "s"}</button>` : c.facts.length ? `<button class="mini" data-ctl="${esc(c.id)}">facts</button>` : '<span class="tiny">—</span>'}</td>
<td>${fid ? `<a class="linkbtn" href="#/finding/${encodeURIComponent(fid)}">Finding ${icon("arrow-right")}</a><div class="chips" style="margin-top:4px">${(c.remedies || []).map(normR).slice(0, 2).map(remedyChip).join("")}</div>` : ""}</td></tr>`;
}
function aspectSection(name, a) {
  const live = a.controls.filter(c => c.state !== "NOT_APPLICABLE"), na = a.controls.filter(c => c.state === "NOT_APPLICABLE");
  const open = ["issues", "gaps"].includes(a.status);
  return `<details class="aspect-block" id="asp-${a.id}"${open ? " open" : ""}><summary>${wsHead({ws: wsOfAspect(a.id)}, `<span class="tiny">${esc(coverageText(a))}</span>${statusTag(a.status)}`)}</summary>
${live.length ? `<table class="simple-table trace"><thead><tr><th>Control</th><th>State</th><th>What was found</th><th>Evidence</th><th>Finding and remedy</th></tr></thead><tbody>${live.map(c => controlRow(name, c)).join("")}</tbody></table>` : ""}
${na.length ? `<div class="tiny na-line">Not applicable: ${na.map(c => `${esc(c.title)} (${esc(c.summary)})`).join("; ")}</div>` : ""}</details>`;
}
const AREA = {build: ["build file", "build files"], ci: ["CI file", "CI files"], config: ["configuration file", "configuration files"], deploy: ["deployment file", "deployment files"],
  main_source: ["source file", "source files"], test_source: ["test source file", "test source files"], docs: ["documentation file", "documentation files"]};
/* where a "not found" looked: "searched 3 build files and 1 CI file" or "the whole repository"; an area with no files says none exist */
function searchedText(s) {
  const parts = s.in.map(x => x.area === "repo" ? "the whole repository" : x.count ? `${x.count} ${AREA[x.area][x.count === 1 ? 0 : 1]}` : `no ${AREA[x.area][1]} (none exist)`);
  return "Searched " + (parts.length > 1 ? parts.slice(0, -1).join(", ") + " and " + parts[parts.length - 1] : parts[0]);
}
function searchedEl(s) {
  return h("div", {}, h("h3", {style: "margin-top:12px"}, "Where it looked"), h("p", {class: "tiny"}, "For " + s.for + "."),
    ...s.in.map(x => h("div", {class: "tiny", style: "margin-top:4px"}, x.area === "repo" ? "The whole repository" : x.count ? `${x.count} ${AREA[x.area][x.count === 1 ? 0 : 1]}: ${x.files.join(", ")}${x.count > x.files.length ? ", …" : ""}` : `No ${AREA[x.area][1]} exist in the repository`)));
}
function blindSpots(a) {
  const b = ((a.aspects.scope || {}).blind_spots) || [];
  return b.length ? `<section class="card overview-card" style="margin-top:12px"><div class="section-heading"><div><h2>Outside this scan</h2><p>The repository names these, but their content is not in it. A control that would be read there is shown as undecided, not missing.</p></div></div><table class="simple-table"><tbody>${b.map(x => `<tr><td>${esc(x.what)}</td><td class="tiny">${x.at.map(esc).join(", ")}</td></tr>`).join("")}</tbody></table></section>` : "";
}
function showControl(a, c) {
  openDrawer(c.title, h("div", {class: "chips", style: "margin:6px 0"}, htmlEl(cstateTag(c.state)), c.level ? h("span", {class: "tag blue"}, LEVEL[c.level] || c.level) : null), h("p", {class: "sub"}, c.summary),
    h("p", {class: "tiny"}, D.catalogue.states[c.state] || ""), c.facts.length ? h("div", {}, h("h3", {style: "margin-top:12px"}, "Facts it was read from"),
      ...c.facts.map(p => { const f = p.split(".").reduce((o, x) => o && o[x], a.discovery) || {}; return h("div", {}, h("div", {class: "tiny", style: "margin-top:8px"}, p), f.status ? pill(f.status) : null, f.note ? h("p", {class: "tiny"}, f.note) : null); })) : null,
    c.searched ? searchedEl(c.searched) : null, h("h3", {style: "margin-top:12px"}, "Evidence"), evList(c.evidence), c.fix ? h("div", {}, h("h3", {style: "margin-top:12px"}, "Fix"), h("p", {}, c.fix)) : null);
}
/* one row per remedy for this application, merged across aspects, main remedies first */
function recommendations(fs) {
  const by = {};
  workstreamsOf(fs).forEach(w => w.remedies.forEach(r => { const e = by[r.k] = by[r.k] || Object.assign({}, r, {ws: [], issues: new Set(), sev: "Info", main: false}); e.ws.push(w.ws.t); r.issues.forEach(x => e.issues.add(x)); e.main = e.main || r.main;
    w.issues.filter(i => i.remedies.some(x => x.k === r.k)).forEach(i => { if (SEVRANK[i.severity] < SEVRANK[e.sev]) e.sev = i.severity; }); }));
  return Object.values(by).sort((x, y) => y.main - x.main || !!y.cmd - !!x.cmd || SEVRANK[x.sev] - SEVRANK[y.sev] || y.issues.size - x.issues.size);
}
function pAssessment(m, name, focus) {
  const a = APPS[name];
  if (!a) { put(m, crumbs([["Assessment"]]) + emptyState("Unknown application", "")); return; }
  CUR = name;
  const asps = aspectsOf(name), fs = allFindings().filter(f => f.app === name), enc = encodeURIComponent(name), ctx = a.aspects.context, prof = a.aspects.profile;
  const st = s => asps.filter(x => x.status === s).length;
  appHead(m, name, "assessment");
  put(m, `<div class="view-intro"><div><p>How it is doing in every aspect that matters for production readiness, and what to do about it. Read from files only: configured is not tested, enforced or observed.</p><div class="chips" style="margin-top:8px"><span class="tag blue">${esc(prof.kind)}</span>${Object.values(ctx).map(c => `<span class="tag gray" title="${esc(c.headline)}">${esc(c.title)}: ${esc(c.state.replace("_", " "))}</span>`).join("")}${a.source && a.source.team ? `<span class="tag gray">team: ${esc(a.source.team)}</span>` : ""}${critOf(a) ? `<span class="tag violet">criticality: ${esc(critOf(a))}</span>` : ""}${(a.aspects.failures || []).length ? `<span class="tag red" title="The controls these feed are not assessed">failed: ${esc(a.aspects.failures.join("; "))}</span>` : ""}</div></div><div class="last-updated">Assessed on<br><b>${esc(fmtDate(D.generated))}</b><br><span class="tiny">catalogue ${esc(D.catalogue.version)}</span></div></div>`);
  const counts = [[st("issues"), "red", "with issues"], [st("gaps"), "yellow", "with gaps"], [st("in_place"), "green", "in place"], [st("in_place_partly_checked"), "teal", "in place where checked"], [st("not_assessed"), "gray", "not assessed"], [st("not_applicable"), "gray", "not applicable"]].filter(x => x[0]).map(([n, c, l]) => `<span class="tag ${c}">${n} ${l}</span>`).join("");
  put(m, `<section class="card overview-card"><div class="section-heading"><div><h2>Aspect scorecard</h2><p>${asps.length} aspects, each the worst of its own controls. There is no combined score.</p></div><div class="tinyrow">${counts}</div></div><div class="score-grid">${asps.map(x => aspectTile(name, x)).join("")}</div></section>`);
  put(m, blindSpots(a));
  put(m, `<section class="card overview-card" style="margin-top:12px"><div class="section-heading"><div><h2>Controls by aspect</h2><p>The trace: each control's state, how strongly it was shown, what was read, the evidence lines, and the finding and remedy when it is not in place.</p></div></div>${asps.map(x => aspectSection(name, x)).join("")}</section>`);
  const recs = recommendations(fs), miss = asps.flatMap(x => x.controls.filter(c => ["NOT_ASSESSED", "UNKNOWN"].includes(c.state)).map(c => [x.title, c]));
  put(m, `<div class="grid-2eq" style="margin-top:12px"><section class="card overview-card"><div class="section-heading"><div><h2>Recommendations</h2><p>From the client's remedy packs (${esc(D.remedy_packs.map(p => p.title).join(", "))}). No effort or value is estimated.</p></div><a class="linkbtn" href="#/roadmap">Roadmap ${icon("arrow-right")}</a></div>${recs.length ? `<table class="simple-table recs"><thead><tr><th>#</th><th>Recommendation</th><th>Aspect</th><th>Addresses</th></tr></thead><tbody>${recs.map((r, i) => `<tr><td>${i + 1}</td><td><b>${esc(r.t)}</b><div style="margin-top:4px">${remedyChip(r)}</div></td><td class="tiny">${r.ws.map(esc).join(", ")}</td><td><div class="tinyrow">${sevTag(r.sev)}<span class="tiny">${r.issues.size} control${r.issues.size === 1 ? "" : "s"}</span></div><div class="tiny" style="margin-top:4px">${[...r.issues].slice(0, 3).map(esc).join("; ")}${r.issues.size > 3 ? "; …" : ""}</div></td></tr>`).join("")}</tbody></table>` : emptyState("Nothing to recommend", "Every applicable control that was assessed is in place.")}</section>
<section class="card overview-card"><div class="section-heading"><div><h2>Missing proof</h2><p>Controls that apply but could not be decided; settle these before planning</p></div></div>${miss.length ? `<table class="simple-table"><thead><tr><th>Aspect</th><th>Control</th><th>Why</th></tr></thead><tbody>${miss.map(([ar, c]) => `<tr><td class="tiny">${esc(ar)}</td><td><b>${esc(c.title)}</b></td><td class="tiny">${esc(c.summary)}</td></tr>`).join("")}</tbody></table>` : emptyState("Nothing missing", "")}</section></div>`);
  put(m, `<section class="card overview-card" style="margin-top:12px"><div class="section-heading"><div><h2>Deployment and test detail</h2><p>Every check behind Deployment & availability and the Testing safety net, per workload and component</p></div></div><div id="dimDetail"></div></section>`);
  const res = dim(a, "operational_resilience"), sn = dim(a, "safety_net_strength");
  $("#dimDetail").append(h("details", {class: "dim-detail"}, h("summary", {}, "HA and resilience · ", h("span", {class: "tiny"}, res.headline)), haSection(a)), h("details", {class: "dim-detail"}, h("summary", {}, "Safety net · ", h("span", {class: "tiny"}, sn.headline)), safetySection(a)));
  const byId = Object.fromEntries(controlsOf(name).map(c => [c.id, c]));
  m.querySelectorAll("[data-ctl]").forEach(b => b.addEventListener("click", () => showControl(a, byId[b.dataset.ctl])));
  if (focus && $("#asp-" + focus)) { const el = $("#asp-" + focus); el.open = true; setTimeout(() => el.scrollIntoView({block: "start"}), 0); }
}
const RST = {present: ["green", "In place"], absent: ["yellow", "Not in the files read"], unknown: ["gray", "Unknown"], default: ["gray", "Platform default"], partial: ["yellow", "Some workloads"], not_applicable: ["gray", "N/A"], not_assessed: ["gray", "Not assessed"]};
function haSection(a) {
  const r = a.resilience, card = h("section", {class: "card overview-card", id: "ha"});
  if (r.state !== "assessed") { card.innerHTML = `<div class="section-heading"><div><h2>HA and resilience</h2><p>Read from Kubernetes, Helm, Nomad or Compose files in the repository</p></div></div>${emptyState("Not assessed", r.reason + " HA settings are only read from deployment files in this repository.")}`; return card; }
  const rel = r.summary.filter(c => !["not_applicable", "not_assessed"].includes(c.state)), c = k => rel.filter(x => x.state === k).length;
  card.innerHTML = `<div class="section-heading"><div><h2>HA and resilience</h2><p>“Not in the files read” is not “not in production”: a platform repository, cluster policy or cloud setting may add it.</p></div></div><div class="tinyrow" style="margin-bottom:10px">${r.platforms.map(p => `<span class="tag blue">${esc({kubernetes: "Kubernetes", nomad: "Nomad", compose: "Docker Compose"}[p] || p)}</span>`).join("")}<span class="tag ${r.eks.detected ? "green" : "gray"}">${r.eks.detected ? "EKS hints found" : "no EKS hint"}</span><span class="tiny">${c("present")} of ${rel.length} checks in place · ${r.workloads.length} workload(s) read</span></div>`;
  for (const g of r.groups) { const cs = r.summary.filter(x => x.group === g && x.state !== "not_applicable"); if (!cs.length) continue;
    card.append(h("details", {open: true}, h("summary", {}, g, " ", h("span", {class: "tiny"}, cs.filter(x => x.state === "present").length + "/" + cs.length)), ...cs.map(x => { const t = RST[x.state] || RST.unknown; return h("div", {class: "item"}, h("div", {class: "body"}, h("div", {class: "t"}, x.title, info(x.why)), x.notes && x.notes.length ? h("div", {class: "d"}, x.notes[0]) : null), h("span", {class: "tag " + t[0]}, t[1]), x.evidence.length ? h("button", {class: "mini", onclick: () => openDrawer(x.title, h("p", {class: "sub"}, x.why), evList(x.evidence))}, "Evidence") : null); }))); }
  card.append(h("details", {}, h("summary", {}, "Limitations"), h("ul", {}, r.limitations.map(x => h("li", {}, x)))));
  return card;
}
function safetySection(a) {
  const sn = a.safetynet, r = sn.repository_level, T = a.discovery.tests, ci = (T.ci_test_execution || {}).value, card = h("section", {class: "card overview-card", id: "safety"});
  const defs = [["unit_tests", "Unit"], ["integration_tests", "Integration"], ["acceptance_tests", "Acceptance"], ["contract_tests", "Contract"], ["performance_tests", "Performance"]];
  const rows = defs.map(([k, l]) => { const f = T[k] || {}, v = f.value || {}, found = ["CONFIRMED", "INFERRED"].includes(f.status), ext = (v.external || []).length; const detail = found ? [v.test_classes ? v.test_classes + " test classes" : null, v.feature_files ? v.feature_files + " feature files" : null, v.contract_files ? v.contract_files + " contract files" : null, v.artefacts ? v.artefacts + " load-test files" : null].filter(Boolean).join(" · ") || "present" : ext ? "triggered from another pipeline" : "nothing matched";
    return `<tr><td><b>${l}</b></td><td><span class="tag ${found ? "green" : ext ? "yellow" : "gray"}">${found ? "Found" : ext ? "External only" : f.status === "UNKNOWN" ? "Unknown" : "Not found"}</span></td><td>${esc(detail)}</td><td>${(f.evidence || []).length ? `<button class="mini" data-tt="${k}">Evidence</button>` : ""}</td></tr>`; }).join("");
  const Q = [["test_exists", "Test exists"], ["runs_automatically", "Runs in CI"], ["passes", "Passes"], ["coverage_measured", "Coverage measured"], ["coverage_threshold_enforced", "Threshold enforced"]];
  const kinds = {api_endpoint: "API endpoints", message_consumer: "Message consumers", message_publisher: "Message publishers", database_path: "Database paths", downstream_http: "Downstream HTTP calls"};
  const bars = Object.entries(kinds).filter(([k]) => sn.summary[k]).map(([k, t]) => { const s = sn.summary[k], tot = s.mapped_with_assertions + s.mapped_no_assertion_seen + s.unverified; if (!tot) return ""; return `<div style="margin:10px 0"><div style="display:flex;justify-content:space-between"><b>${t}</b><span class="tiny">${s.direct != null ? s.direct : s.mapped_with_assertions + s.mapped_no_assertion_seen}/${tot} mapped to a route${s.class_level ? " · +" + s.class_level + " by class" : ""}</span></div><div class="confidence-strip"><i style="width:${100 * s.mapped_with_assertions / tot}%;background:#19b97d"></i><i style="width:${100 * s.mapped_no_assertion_seen / tot}%;background:#f2b01e"></i><i style="width:${100 * s.unverified / tot}%;background:#cfd8e5"></i></div></div>`; }).join("");
  card.innerHTML = `<div class="section-heading"><div><h2>Safety net</h2><p>Test types found, what runs in CI, and which discovered components have a test mapped to them. Unverified never means untested; nothing is executed, so “passes” is always unknown.</p></div></div><table class="simple-table"><thead><tr><th>Test type</th><th>Status</th><th>Detail</th><th></th></tr></thead><tbody>${rows}</tbody></table><div class="tinyrow" style="margin:10px 0">Run automatically in CI: <span class="tag ${ci === "enabled" ? "green" : ci === "disabled" ? "red" : "gray"}">${ci === "enabled" ? "yes" : ci === "disabled" ? "tests disabled" : "unknown"}</span>${Q.map(([k, l]) => { const st = r[k].state; return `<span class="tag ${st === "yes" ? "green" : st === "no" ? "yellow" : "gray"}">${l}: ${st === "yes" ? "found" : st === "no" ? "not found" : "unknown"}</span>`; }).join("")}</div>${bars || emptyState("Nothing to map", "No endpoints, consumers, publishers, database paths or downstream calls were discovered.")}`;
  card.querySelectorAll("[data-tt]").forEach(b => b.addEventListener("click", () => { const f = T[b.dataset.tt] || {}; openDrawer(b.dataset.tt.replace("_", " "), h("p", {class: "sub"}, f.note || ""), evList(f.evidence)); }));
  const comps = sn.components.filter(c => c.classification === "unverified").slice(0, 25);
  if (comps.length) card.append(h("details", {}, h("summary", {}, "Unverified components (" + sn.components.filter(c => c.classification === "unverified").length + ")"), ...comps.map(c => h("div", {class: "item"}, h("div", {class: "body"}, h("div", {class: "t"}, c.label), h("div", {class: "d"}, c.explanation)), pill("unverified")))));
  card.append(h("details", {}, h("summary", {}, "Limitations"), h("ul", {}, sn.limitations.map(x => h("li", {}, x)))));
  return card;
}
