"""The local review page (design 8.1): Python's own HTTP server, bound to 127.0.0.1 on a free port, answering only requests that
carry this session's token and name this server as their Host, so no other web page (and no DNS rebinding) can read or drive it.
Every action goes through review.Review, the same functions `review --record` uses. Nothing is fetched from anywhere.
"""
from __future__ import annotations

import hmac
import json
import secrets
import threading
import time
from http.server import BaseHTTPRequestHandler, HTTPServer
from urllib.parse import parse_qs, urlparse

from . import client_file as CF
from . import review as RV

MAX_BODY = 64 * 1024
HEADERS = {"Content-Security-Policy": "default-src 'none'; script-src 'unsafe-inline'; style-src 'unsafe-inline'; connect-src 'self'; base-uri 'none'; form-action 'none'; frame-ancestors 'none'",
           "Referrer-Policy": "no-referrer", "X-Content-Type-Options": "nosniff", "X-Frame-Options": "DENY", "Cache-Control": "no-store"}


class Server(HTTPServer):
    def __init__(self, rv, port=0):
        self.rv, self.token, self.lock = rv, secrets.token_urlsafe(24), threading.Lock()
        self.shown = {}  # key -> when the page fetched it: the time per item is measured here, not reported by the page
        super().__init__(("127.0.0.1", port), Handler)
        self.hosts = {"127.0.0.1:%d" % self.server_port, "localhost:%d" % self.server_port}

    @property
    def url(self):
        return "http://127.0.0.1:%d/?t=%s" % (self.server_port, self.token)


class Handler(BaseHTTPRequestHandler):
    server_version = "app-insight-review"

    def log_message(self, *a):  # requests carry the token in the first URL: never logged
        pass

    def _send(self, code, body, ctype="application/json"):
        data = body.encode() if isinstance(body, str) else json.dumps(body).encode()
        self.send_response(code)
        self.send_header("Content-Type", ctype + "; charset=utf-8")
        self.send_header("Content-Length", str(len(data)))
        for k, v in HEADERS.items():
            self.send_header(k, v)
        self.end_headers()
        self.wfile.write(data)

    def _allowed(self, q):
        if self.headers.get("Host") not in self.server.hosts:
            self._send(421, {"error": "wrong host"})
            return False
        tok = self.headers.get("X-Review-Token") or (q.get("t") or [""])[0]
        if not hmac.compare_digest(tok.encode(), self.server.token.encode()):
            self._send(403, {"error": "no or wrong session token"})
            return False
        origin = self.headers.get("Origin")
        if origin and origin.split("//", 1)[-1] not in self.server.hosts:
            self._send(403, {"error": "cross-origin request"})
            return False
        return True

    def do_GET(self):
        u = urlparse(self.path)
        q = parse_qs(u.query)
        if not self._allowed(q):
            return
        rv = self.server.rv
        with self.server.lock:
            if u.path == "/":
                return self._send(200, PAGE.replace("__TOKEN__", self.server.token), "text/html")
            if u.path == "/api/state":
                return self._send(200, rv.state())
            if u.path == "/api/item":
                k = (q.get("key") or [""])[0]
                if k not in rv.results:
                    return self._send(404, {"error": "no such result"})
                self.server.shown[k] = time.monotonic()
                return self._send(200, rv.item(k))
            if u.path == "/api/screen":
                app, asp = (q.get("app") or [""])[0], (q.get("aspect") or [""])[0]
                s = next((x for x in rv.bulk_screens() if x["app"] == app and x["aspect"] == asp), None)
                if not s:
                    return self._send(404, {"error": "no such screen"})
                self.server.shown["screen:%s:%s" % (app, asp)] = time.monotonic()
                return self._send(200, dict(s, items=[rv.item(k) for k in s["keys"]]))
        self._send(404, {"error": "not found"})

    def do_POST(self):
        u = urlparse(self.path)
        if not self._allowed({}):
            return
        if self.headers.get("Content-Type", "").split(";")[0] != "application/json":
            return self._send(415, {"error": "JSON only"})
        n = int(self.headers.get("Content-Length") or 0)
        if n > MAX_BODY:
            return self._send(413, {"error": "too large"})
        try:
            body = json.loads(self.rfile.read(n) or b"{}")
        except ValueError:
            return self._send(400, {"error": "not JSON"})
        rv, srv = self.server.rv, self.server
        with srv.lock:
            try:
                if u.path == "/api/outcome":
                    t0 = srv.shown.pop(body.get("key"), None)
                    res = rv.record(body, seconds=time.monotonic() - t0 if t0 else 0)
                elif u.path == "/api/audit":
                    t0 = srv.shown.pop(body.get("key"), None)
                    res = rv.audit(body, seconds=time.monotonic() - t0 if t0 else 0)
                elif u.path == "/api/bulk":
                    t0 = srv.shown.pop("screen:%s:%s" % (body.get("app"), body.get("aspect")), None)
                    res = rv.bulk(body.get("app"), body.get("aspect"), body.get("keys"), seconds=time.monotonic() - t0 if t0 else 0)
                elif u.path == "/api/publish":
                    res = CF.publish(rv)
                elif u.path == "/api/stop":
                    threading.Thread(target=srv.shutdown, daemon=True).start()
                    return self._send(200, {"stopped": True})
                else:
                    return self._send(404, {"error": "not found"})
            except RV.Refused as e:
                return self._send(409, {"error": str(e)})
            except (KeyError, TypeError, ValueError) as e:
                return self._send(400, {"error": "bad request (%s)" % type(e).__name__})
        self._send(200, {"result": res, "state": rv.state()})


def serve(rv, port=0, open_browser=True, out=None):
    import sys
    srv = Server(rv, port)
    print("review page: %s  (this machine only; the link holds this session's token; Ctrl+C or Finish to stop)" % srv.url, file=out or sys.stderr)
    if open_browser:
        import webbrowser
        webbrowser.open(srv.url)
    try:
        srv.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        srv.server_close()


PAGE = r"""<!doctype html><html lang="en"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width, initial-scale=1">
<title>app-insight · review</title><style>
:root{--bg:#f2f7fc;--card:#fff;--text:#11213a;--muted:#6e819e;--line:#dfe8f2;--blue:#126cf4;--amber:#a65a00;--red:#c3283a}
@media (prefers-color-scheme: dark){:root{--bg:#0f1824;--card:#16212f;--text:#e3ebf5;--muted:#93a4ba;--line:#2a3a4e;--blue:#5aa2ff;--amber:#f0a040;--red:#ff7a88}}
*{box-sizing:border-box}body{margin:0;background:var(--bg);color:var(--text);font:13px/1.45 -apple-system,BlinkMacSystemFont,"Segoe UI",Arial,sans-serif}
main{max-width:1000px;margin:0 auto;padding:16px}.card{background:var(--card);border:1px solid var(--line);border-radius:10px;padding:14px;margin-top:12px}
h1{font-size:18px;margin:0}h2{font-size:15px;margin:0 0 6px}.muted{color:var(--muted);font-size:12px}pre{white-space:pre-wrap;background:var(--bg);border-radius:6px;padding:6px 8px;margin:3px 0;font-size:12px}
button{font:inherit;border:1px solid var(--line);background:var(--card);color:var(--text);border-radius:6px;padding:7px 11px;margin:3px 4px 3px 0;cursor:pointer}button.primary{background:var(--blue);color:#fff;border-color:var(--blue)}
kbd{border:1px solid var(--line);border-radius:3px;padding:0 4px;font-size:11px;color:var(--muted)}select,input,textarea{font:inherit;background:var(--card);color:var(--text);border:1px solid var(--line);border-radius:6px;padding:6px}
textarea{width:100%;min-height:52px}.bar{height:8px;background:var(--line);border-radius:999px;overflow:hidden}.bar i{display:block;height:100%;background:var(--blue)}
.tag{display:inline-block;border-radius:999px;padding:1px 8px;font-weight:700;font-size:12px;border:1px solid var(--line)}.gap{color:var(--amber)}.issue{color:var(--red)}
.row{display:flex;gap:8px;flex-wrap:wrap;align-items:center}.err{color:var(--red);font-weight:600}label{margin-right:10px}
</style></head><body><main>
<div class="row" style="justify-content:space-between"><h1>Consultant review</h1><span class="muted" id="who"></span></div>
<div class="card"><div class="row" style="justify-content:space-between"><b id="prog"></b><span class="muted" id="plan"></span></div><div class="bar"><i id="pbar" style="width:0"></i></div><div id="block" class="muted"></div></div>
<div class="card" id="view"></div>
<div class="card muted">Keys: <kbd>c</kbd> confirm · <kbd>r</kbd> remedy confirmed · <kbd>x</kbd> correct · <kbd>g</kbd> gap stated · <kbd>d</kbd> dispute · <kbd>u</kbd> cannot confirm · <kbd>t</kbd> stated by the team · <kbd>n</kbd> next · <kbd>b</kbd> back · <kbd>a</kbd> confirm the aspect screen · <kbd>p</kbd> publish client file</div>
</main><script>
"use strict";
const T = "__TOKEN__";
const esc = v => String(v == null ? "" : v).replace(/[&<>"']/g, c => ({"&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;"}[c]));
let S = null, Q = [], at = 0, cur = null, scr = null, form = null;
async function api(path, body) {
  const r = await fetch(path, body ? {method: "POST", headers: {"Content-Type": "application/json", "X-Review-Token": T}, body: JSON.stringify(body)} : {headers: {"X-Review-Token": T}});
  const j = await r.json(); if (!r.ok) throw new Error(j.error || r.status); return j;
}
function queue() {  /* must-review one by one, then the aspect screens, then possible issues, then the audit sample */
  return [].concat(S.must.map(m => ({t: "item", key: m.key, done: m.done})), S.screens.map(s => ({t: "screen", app: s.app, aspect: s.aspect, title: s.title, done: !s.open})),
    S.optional.map(o => ({t: "item", key: o.key, done: o.done, optional: true})), S.audit.map(k => ({t: "audit", key: k, done: false})));
}
async function load(stay) {
  S = await api("/api/state"); Q = queue();
  const done = Q.filter(q => q.done).length;
  document.getElementById("who").textContent = "reviewer " + (S.reviewer || "-") + (S.auditor ? " · second person " + S.auditor : "") + " · run " + S.run;
  document.getElementById("prog").textContent = "must-review " + S.must.filter(m => m.done).length + " of " + S.must.length + " · aspect screens " + S.screens.filter(s => !s.open).length + " of " + S.screens.length + (S.auditor ? " · audit " + S.audit.length + " left" : "");
  document.getElementById("pbar").style.width = (Q.length ? 100 * done / Q.length : 100) + "%";
  document.getElementById("plan").textContent = "about " + S.plan.projected_min + " min left";
  document.getElementById("block").innerHTML = S.blockers.map(b => "<div class=err>" + esc(b) + "</div>").join("") + S.firings.map(f => "<div>Stop rule fired on " + esc(f.controls.join(", ")) + (f.cleared ? " (cleared)" : ": review these one by one") + "</div>").join("");
  if (!stay) { at = Q.findIndex(q => !q.done); if (at < 0) at = Q.length; }
  show();
}
function ev(i) {
  return (i.evidence.length ? i.evidence.map(e => "<div class=muted>" + esc(e.kind === "file" ? e.path + ":" + e.line_start : e.cmd || "") + "</div><pre>" + esc(e.snippet || "") + "</pre>").join("") : "<div class=muted>No line cited.</div>")
    + (i.searched ? "<div class=muted>Searched for " + esc(i.searched.for) + " in " + esc((i.searched.in || []).map(w => w.area + " (" + w.count + ")").join(", ")) + "</div>" : "")
    + (i.remedies.length ? "<div class=muted>Remedy: " + i.remedies.map(r => esc(r.cmd || r.title)).join("; ") + "</div>" : "")
    + (i.reference ? "<div class=muted>Reference data: " + esc(i.reference.status) + ", as of " + esc(i.reference.as_of) + "</div>" : "");
}
async function show() {
  const v = document.getElementById("view"); cur = scr = null;
  if (at >= Q.length) { v.innerHTML = "<h2>Nothing left in the queue</h2><p class=muted>" + (S.published ? "Client file written: " + esc(S.published.file) : "Publish the client file when ready.") + "</p><button class=primary onclick='pub()'>Publish client file</button> <button onclick='stop()'>Finish</button>"; return; }
  const q = Q[at];
  if (q.t === "screen") {
    scr = await api("/api/screen?app=" + encodeURIComponent(q.app) + "&aspect=" + encodeURIComponent(q.aspect));
    v.innerHTML = "<h2>" + esc(q.app) + " · " + esc(q.title) + ": confirm with its aspect</h2><p class=muted>In place and not applicable results outside the must-review set. Open any you doubt one by one instead.</p>"
      + scr.items.map(i => "<div class=card><b>" + esc(i.title) + "</b> <span class=tag>" + esc(i.label) + "</span>" + (i.outcome ? " <span class=muted>(" + esc(i.mode) + ")</span>" : "") + "<div class=muted>" + esc(i.summary) + "</div>" + ev(i) + "</div>").join("")
      + "<button class=primary onclick='bulk()'>Confirm these " + scr.open.length + " (a)</button> <button onclick='nav(1)'>Next (n)</button>";
    return;
  }
  cur = await api("/api/item?key=" + encodeURIComponent(q.key));
  const i = cur, cls = i.state === "ISSUE" ? "issue" : i.gap ? "gap" : "";
  v.innerHTML = "<div class=muted>" + (q.t === "audit" ? "Audit sample (second person) · " : q.optional ? "Optional · " : "") + esc(i.app) + " · " + esc(i.aspect) + " · severity " + esc(i.severity) + (i.why.length ? " · why: " + esc(i.why.join("; ")) : "") + "</div>"
    + "<h2>" + esc(i.title) + " <span class='tag " + cls + "'>" + esc(i.label) + "</span>" + (i.level ? " <span class=muted>" + esc(i.level) + "</span>" : "") + "</h2><div>" + esc(i.summary) + "</div>" + ev(i)
    + (i.earlier ? "<div class=card><b>Earlier outcome</b>: " + esc(i.earlier.outcome) + (i.earlier.state ? " (" + esc(i.earlier.state) + ")" : "") + " · " + esc(i.earlier.note || "") + " · " + esc(i.earlier.reviewer) + ", " + esc((i.earlier.at || "").slice(0, 10)) + " (run " + esc(i.earlier.run) + ")</div>" : "")
    + (i.outcome ? "<div class=card>Recorded: <b>" + esc(i.outcome.outcome) + "</b> by " + esc(i.outcome.reviewer) + " (" + esc(i.mode) + ")</div>" : "")
    + "<div class=card id=form></div>";
  outcome("confirmed");
}
const REQ = {corrected: ["state", "reason"], disputed: ["reason"], team_stated: ["answer", "who", "state"]};
function outcome(o) {
  form = o; const i = cur, f = document.getElementById("form"); if (!f) return;
  const opts = (m, sel) => Object.entries(m).map(([k, t]) => "<option value='" + esc(k) + "'" + (k === sel ? " selected" : "") + ">" + esc(t) + "</option>").join("");
  const allow = {confirmed: i.state !== "NOT_ASSESSED", corrected: true, gap_stated: ["PRESENT", "NOT_APPLICABLE", "UNKNOWN"].includes(i.state), disputed: i.gap, cannot_confirm: true, team_stated: i.undecided};
  const names = {confirmed: "Confirm (c)", corrected: "Correct (x)", gap_stated: "Gap stated (g)", disputed: "Dispute (d)", cannot_confirm: "Cannot confirm (u)", team_stated: "Stated by the team (t)"};
  f.innerHTML = "<div class=row>" + Object.keys(names).filter(k => allow[k]).map(k => "<button class='" + (k === o ? "primary" : "") + "' onclick=\"outcome('" + k + "')\">" + names[k] + "</button>").join("") + "</div>"
    + (o === "confirmed" && i.gap ? "<label><input type=checkbox id=rem> remedy confirmed (r)</label>" : "")
    + (["corrected", "team_stated"].includes(o) ? "<label>state <select id=state>" + opts(S.states, i.state) + "</select></label>" : "")
    + (o !== "confirmed" ? "<label>reason <select id=reason><option value=''>none</option>" + opts(S.reasons) + "</select></label>" : "")
    + (o === "team_stated" ? "<label>answer <input id=answer size=40></label><label>who <input id=who2 size=18></label>" : "")
    + (o !== "confirmed" ? "<div><textarea id=note placeholder='Note (redacted when saved)'></textarea></div><div><input id=evid size=60 placeholder='Evidence: path:line, or outside the repository (optional)'></div>" : "")
    + "<div class=row><button class=primary onclick='save()'>Save and next (Enter)</button><span id=msg class=err></span></div>";
}
const val = id => { const e = document.getElementById(id); return e ? (e.type === "checkbox" ? e.checked : e.value) : undefined; };
async function save() {
  const q = Q[at], b = {key: cur.key, outcome: form, state: val("state"), reason: val("reason") || undefined, note: val("note") || undefined, answer: val("answer"), who: val("who2"), evidence: val("evid") || undefined, remedy_confirmed: val("rem")};
  try { await api(q.t === "audit" ? "/api/audit" : "/api/outcome", b); await load(); } catch (e) { document.getElementById("msg").textContent = e.message; }
}
async function bulk() { try { await api("/api/bulk", {app: scr.app, aspect: scr.aspect}); await load(); } catch (e) { alert(e.message); } }
async function pub() { try { const r = await api("/api/publish", {}); alert(r.result.ok ? "Client file written: " + r.result.path + (r.result.not_available.length ? " (not available: " + r.result.not_available.join(", ") + ")" : "") : "Not written: " + (r.result.refused.concat(r.result.problems.map(p => p.rule + " in " + p.where))).join("; ")); await load(true); } catch (e) { alert(e.message); } }
async function stop() { await api("/api/stop", {}); document.getElementById("view").innerHTML = "<h2>Review saved. You can close this page.</h2>"; }
function nav(d) { at = Math.max(0, Math.min(Q.length, at + d)); show(); }
document.addEventListener("keydown", e => {
  if (["INPUT", "TEXTAREA", "SELECT"].includes(e.target.tagName)) { if (e.key === "Enter" && e.target.tagName !== "TEXTAREA" && cur) save(); return; }
  const k = e.key, m = {c: "confirmed", x: "corrected", g: "gap_stated", d: "disputed", u: "cannot_confirm", t: "team_stated"};
  if (cur && m[k]) { outcome(m[k]); e.preventDefault(); }
  else if (k === "r" && document.getElementById("rem")) document.getElementById("rem").checked = !document.getElementById("rem").checked;
  else if (k === "Enter" && cur) save(); else if (k === "n") nav(1); else if (k === "b") nav(-1); else if (k === "a" && scr) bulk(); else if (k === "p") pub();
});
load().catch(e => { document.getElementById("view").textContent = "Could not load the review: " + e.message; });
</script></body></html>
"""
