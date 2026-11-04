#!/usr/bin/env python3
"""Build mock.html (real run) from the user's application-first mock plus real.js and extra.css.

    python3 -I build_real.py <run-dir>      -> mock.html (opens on the 6 real applications; the 300 view is a toggle)
"""
import os
import re
import subprocess
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
rd = lambda n: open(os.path.join(HERE, n)).read()
run = sys.argv[1]
subprocess.run([sys.executable, "-I", os.path.join(HERE, "real_data.py"), run, os.path.join(HERE, "data-real.js")], check=True)

app = rd("app.js")
PATCHES = [  # (old, new): each must match exactly once
    ("expanded:'checkout',current:'checkout'", "expanded:null,current:apps[0].id"),
    ("state.expanded=state.scale?null:'checkout'", "state.expanded=null"),
    ("${state.scale?'Use 12':'Test 300'} synthetic apps", "${state.scale?'Back to the '+allBase.length+' real applications':'Show 300 synthetic'}"),
    ("Repository-only assessment · Counts never include UNKNOWN, NOT_ASSESSED or NOT_APPLICABLE as passing or failing controls. One illustrative pending detector is tracked once as a tool limitation, not per application.", "${runNote()}<br>${pendingNote()}"),
    ("${ent(a.kind)} · Owner and business criticality not supplied", "${ent(a.kind)} · owners ${a.facts[1][1]==='not found'?'not found in the repository':ent(a.facts[1][1])} · business criticality not supplied"),
    ("Application details represent static repository evidence. No builds, tests, production probes or model assessments have been executed.", "${runNote()}"),
    ("<select class=\"choice\" id=\"qFind\"", "${entrySelect()}<select class=\"choice\" id=\"qFind\""),
    ("function render(){header();if(state.mode==='inventory')inventory();else if(state.mode==='detail')detail();else compare();renderDrawer()}", "function render(){header();if(state.mode==='inventory')inventory();else if(state.mode==='detail')detail();else if(state.mode==='estate')estate();else compare();renderDrawer()}"),
    ("$id('crumb').innerHTML=ent(crumb);", "if(state.mode==='estate')crumb='Estate';$id('crumb').innerHTML=ent(crumb);$id('navApps')?.classList.toggle('active',state.mode!=='estate');$id('navEstate')?.classList.toggle('active',state.mode==='estate');"),
    ("else if(initialHash==='compare'){state.mode='inventory'}", "else if(initialHash==='compare'){state.mode='inventory'}else if(initialHash.startsWith('estate')){state.mode='estate';state.estate=initialHash.split('/')[1]||'built'}"),
    ("Compare selected (0/5)</button></div></section>${demoBanner()}<section class=\"card\">", "Compare selected (0/5)</button></div></section>${demoBanner()}${onlyChip()}<section class=\"card\">"),
    ("<th>Connections</th><th style=\"width:65px\">Explore</th>", ""),
    ("rows+=`<tr><td colspan=\"8\" class=\"grouphead\">", "rows+=`<tr><td colspan=\"6\" class=\"grouphead\">"),
    ("'<tr><td colspan=\"8\"><div class=\"empty\">", "'<tr><td colspan=\"6\"><div class=\"empty\">"),
    ("Support reference not reviewed", "support dates are reference data, unreviewed"),
]
for old, new in PATCHES:
    assert app.count(old) == 1, old[:60]
    app = app.replace(old, new)
app = app.replace("${s.findings} findings", "${pl(s.findings,'finding')}")
app = app.replace("<div class=\"control-desc\">${ent(c.summary)}</div>", "<div class=\"control-desc\">${ent(tidy(c.summary))}</div>")
cut = app.index("document.addEventListener('keydown'")
js = rd("data-real.js") + "\n" + app[:cut] + "\n" + rd("real.js") + "\n" + rd("estate.js") + "\n" + app[cut:]
js = js.replace("</script", "<\\/script")

shell = rd("build.py")
tpl = shell[shell.index("'''") + 3: shell.rindex("'''")]
head, rest = tpl.split("<style>", 1)
_, body = rest.split("</style>", 1)
body = body.split("<script>", 1)[0]
head = head.replace("app-insight · Applications — application-first mock", "app-insight · Applications")
ESTATE_BTN = '<button class="side-link" id="navEstate" onclick="showEstate()"><svg viewBox="0 0 24 24" width="18" height="18" fill="none" stroke="currentColor"><path d="M3 21h18M5 21V9l7-5 7 5v12M9 21v-6h6v6"/></svg> Estate</button>'
for old, new in [('<button class="side-link active" onclick="showInventory()">', '<button class="side-link active" id="navApps" onclick="showInventory()">'),
                 ('Applications</button><div class="side-meta">', 'Applications</button>' + ESTATE_BTN + '<div class="side-meta">'),
                 ("● LOCAL · SYNTHETIC PREVIEW", "● LOCAL · READ ONLY"), ("Offline prototype", "Offline · nothing leaves this machine"),
                 ("Read-only · Example data", "Run " + os.path.basename(run.rstrip("/")))]:
    assert body.count(old) == 1, old
    body = body.replace(old, new)
html = head + "<style>" + rd("styles.css") + "\n" + rd("extra.css") + "</style>" + body + "<script>" + js + "</script></body></html>"
out = os.path.join(HERE, "mock.html")
open(out, "w").write(html)
print("wrote", out, len(html), "bytes")
