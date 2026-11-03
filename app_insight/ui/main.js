/* start: promo line, icons that sit in static markup, router */
$("#promoSub").textContent = (D.client ? D.client + " · " : "") + D.apps.length + " applications · static scan, evidence-led";
{ const v = D.verify || {}, fails = D.apps.filter(a => (a.aspects.failures || []).length).length;
  $("#gateTag").innerHTML = `<span class="tag red" title="Not for client use: results are not yet validated or reviewed">${esc(D.gate || "Internal: not validated")}</span> `
    + `<span class="tag ${v.ok === true ? "green" : v.ok === false ? "red" : "gray"}" title="${esc(Object.entries(v.failed_rules || {}).map(([k, x]) => k + " " + x.rule + " (" + x.count + ")").join("; ") || "every cited line re-read, every count recomputed")}">Verify: ${esc(v.state || "not run")}</span> `
    + (fails ? `<span class="tag yellow" title="A detector failed: the controls it feeds are not assessed">${fails} with a failed detector</span> ` : ""); }
$("#searchIc").innerHTML = icon("search"); $("#exportIc").innerHTML = icon("export");
window.addEventListener("hashchange", route); route();
