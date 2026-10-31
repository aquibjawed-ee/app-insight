/* start: promo line, icons that sit in static markup, router */
$("#promoSub").textContent = (D.client ? D.client + " · " : "") + D.apps.length + " applications · static scan, evidence-led";
$("#searchIc").innerHTML = icon("search"); $("#exportIc").innerHTML = icon("export");
window.addEventListener("hashchange", route); route();
