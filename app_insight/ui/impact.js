/* impact: change-impact assessments (impact.v1) in v2 cards. Confirmed = a cited rule matched literal text. Downstream = graph reachability, not proof of breakage. */
function pImpact(m) {
  put(m, crumbs([["Change impact"]]) + pageHeading("Change impact", "What would a change touch? Confirmed means a cited rule matched literal text in cited files. Downstream is graph reachability: it may matter there, it does not say it breaks."));
  if (!D.impacts.length) { put(m, emptyState("No impact assessment has been run", "Example: relate.py impact --out <dir> --scenario java_runtime --to 17")); return; }
  for (const r of D.impacts) {
    const sc = r.scenario, title = human(sc.type) + " " + Object.entries(sc).filter(([k]) => !["type", "apps"].includes(k)).map(([k, v]) => k + "=" + v).join(" ");
    const rv = r.rules_review || {}, rvText = rv.status === "reviewed" ? "reviewed by " + rv.reviewed_by + " " + rv.reviewed_at : "reference data not reviewed";
    const card = h("section", {class: "card overview-card", style: "margin-bottom:14px"});
    card.innerHTML = `<div class="section-heading"><div><h2>${esc(title)}</h2><p>rules v${esc(r.rules_version)} · ${esc(rvText)}</p></div></div><div class="kpi-grid" style="grid-template-columns:repeat(4,minmax(0,1fr));margin-bottom:12px">${[["#fa5264", "#ffedf0", "alert-triangle", "Confirmed", r.confirmed_incompatibilities.length, "incompatibilities"], ["#f2b01e", "#fff7e7", "clock", "Potential risks", r.potential_risks.length, "behavioural"], ["#287bff", "#e7f0ff", "network", "Downstream", r.downstream_impact.length, "components reachable"], ["#8b9bb2", "#eef2f7", "info", "Unknowns", r.unknowns.length, "missing evidence"]].map(([c, bg, ic, t, v, s]) => `<article class="kpi"><span class="iconwrap" style="background:${bg};color:${c}">${icon(ic)}</span><div class="kpi-info"><div class="kpi-title">${t}</div><div class="kpi-value">${v}</div><div class="delta-label">${s}</div></div></article>`).join("")}</div>`;
    const sec = (t, items, fn, open) => h("details", {open: open && items.length}, h("summary", {}, t, " ", h("span", {class: "tiny"}, items.length)), items.length ? items.map(fn) : h("div", {class: "tiny"}, "None."));
    card.append(
      sec("Confirmed incompatibilities", r.confirmed_incompatibilities, f => h("div", {class: "item"}, h("i", {class: "ico bad"}, "!"), h("div", {class: "body"}, h("div", {class: "t"}, f.app + " · " + f.rule_id), h("div", {class: "d"}, f.message), f.remediation ? h("div", {class: "tiny"}, "Fix: " + f.remediation) : null, f.reference ? h("div", {class: "tiny"}, f.reference) : null, evList(f.evidence))), true),
      sec("Potential behavioural risks", r.potential_risks, f => h("div", {class: "item"}, h("i", {class: "ico warn"}, "▲"), h("div", {class: "body"}, h("div", {class: "t"}, f.app + " · " + f.rule_id), h("div", {class: "d"}, f.message), evList(f.evidence)))),
      sec("Affected components", r.affected_components, c => h("div", {class: "row"}, h("div", {class: "k"}, nm(c.component)), h("div", {class: "v"}, c.why))),
      sec("Potential downstream impact", r.downstream_impact, d => h("div", {class: "item"}, h("div", {class: "body"}, h("div", {class: "t"}, d.name), h("div", {class: "d"}, d.because + " · " + d.hops + " hop(s)")), pill(d.path_confidence === "reduced" ? "inferred" : "confirmed", d.path_confidence === "reduced" ? "path has inferred links" : "path as discovered"), h("button", {class: "mini", onclick: () => showEdges(d.via, "Path to " + d.name)}, "Path"))),
      sec("Required verification", r.required_verification, v => h("div", {class: "item"}, h("div", {class: "body"}, h("div", {class: "d"}, v.what)), v.safety_net ? pill(v.safety_net.classification) : pill("unknown", "no safety-net data"))),
      sec("Unknowns and missing evidence", r.unknowns, u => h("div", {class: "row"}, h("div", {class: "k"}, u.what), h("div", {class: "v"}, u.why))));
    m.append(card);
  }
}
