from __future__ import annotations

import os
import re

from evidence import cmd_ev, fact, file_ev, read_lines, redact, run


VERSION = "0.6.0"

CODEOWNERS = ("CODEOWNERS", ".github/CODEOWNERS", "docs/CODEOWNERS", ".gitlab/CODEOWNERS")


def _owners(ctx):
    """Owners named on the catch-all rule if there is one, otherwise on the first rule of the CODEOWNERS file."""
    name = next((n for n in CODEOWNERS if n in ctx.fileset), None)
    if not name:
        return fact([], "NOT_FOUND", [], "no CODEOWNERS file")
    lines = read_lines(ctx.repo, name) or []
    rules = [(i, l) for i, l in enumerate(lines, 1) if l.strip() and not l.strip().startswith("#")]
    pick = next(((i, l) for i, l in rules if l.split()[0] == "*"), rules[0] if rules else None)
    owners = [t for t in (pick[1].split()[1:] if pick else []) if not t.startswith("#")]
    if not owners:
        return fact([], "NOT_FOUND", [file_ev(name, 1, lines[0] if lines else "")], "CODEOWNERS names no owner")
    return fact(owners[:5], "CONFIRMED", [file_ev(name, pick[0], lines[pick[0] - 1])],
                "owners on the %s rule of %s" % ("catch-all" if pick[1].split()[0] == "*" else "first", name))

README_NAMES = ("README.md", "README.MD", "Readme.md", "readme.md", "README.markdown", "README.rst", "README.txt", "README")
ABOUT_LINES, ABOUT_CHARS = 5, 700
_MD_LINK = re.compile(r"\[([^\]]+)\]\([^)]*\)")


def _clean(line: str) -> str:
    line = _MD_LINK.sub(r"\1", line)
    line = re.sub(r"<[^>]+>|[*_`]{1,3}", "", line)
    return redact(line.strip())


def _about(ctx):
    """First descriptive lines of the root README: headings, badges, HTML, tables, code and lists are skipped."""
    name = next((n for n in README_NAMES if n in ctx.fileset), None)
    if not name:
        return fact(None, "NOT_FOUND", [], "no README in the repository root")
    lines = read_lines(ctx.repo, name) or []
    # a setext heading is a line underlined with === or ---: "Office Integration" over "=====" is a title, not a description
    setext = {i for i in range(1, len(lines)) if lines[i - 1].strip() and re.match(r"^\s*(=+|-{3,})\s*$", lines[i])}
    out, first, fence, headings, titles = [], None, False, 0, []
    for i, raw in enumerate(lines, 1):
        t = raw.strip()
        if i in setext and not fence:
            raw, t = "# " + t, "# " + t
        if raw[:1] in (" ", "\t") and t:
            continue  # indented: list continuation or code, never the description
        if t.startswith("#") and not fence:
            headings += 1
            titles.append((i, re.sub(r"^#+\s*", "", t)))
            if headings > 1 and not re.match(r"^#+\s*(about|overview|introduction|description|summary|what is)\b", t, re.I):
                break  # first section after the title: the intro is over (or there never was one)
            if out:
                break
            continue
        if t.startswith("```") or t.startswith("~~~"):
            fence = not fence
            continue
        skip = (fence or not t or t.startswith(("#", "<!--", "|", ">", "- ", "* ", "+ ", "=", "-", "[!["))
                or "![" in t or t.startswith("<") or re.match(r"^\d+[.)] ", t))
        if skip:
            if out and (not t or t.startswith("#")):
                break  # the first paragraph ended
            continue
        c = _clean(t)
        if not c:
            continue
        first = first or i
        out.append(c)
        if len(out) >= ABOUT_LINES or sum(map(len, out)) >= ABOUT_CHARS:
            break
    if not out:
        # no paragraph, but a title that is a sentence ("Micro service for uploading files into babylon") describes the application
        said = next(((i, _clean(h)) for i, h in titles[:2] if len(h.split()) >= 4 and _clean(h)), None)
        if said:
            return fact([said[1]], "CONFIRMED", [file_ev(name, said[0], lines[said[0] - 1])], "the README's heading describes the application; it has no intro paragraph")
        return fact(None, "NOT_FOUND", [file_ev(name, 1, lines[0] if lines else "")], "README has no descriptive text")
    return fact(out, "CONFIRMED", [file_ev(name, first, lines[first - 1])], "first lines of %s, markup removed" % name)

_USERINFO = re.compile(r"^(\w+://)[^/@\s]+@")
_SSH = re.compile(r"^(?:ssh://)?(?:[\w.-]+@)?([\w.-]+)[:/](.+?)(?:\.git)?/?$")
_HTTP = re.compile(r"^https?://([\w.-]+)(?::\d+)?/(.+?)(?:\.git)?/?$")


def _web(remote: str):
    """(web host, 'org/repo', note) for a git remote, or None. SSH aliases are not real hosts: a host that merely
    contains 'github' is taken to be github.com and the result is labelled inferred."""
    m = _HTTP.match(remote) or _SSH.match(remote)
    if not m:
        return None
    host, path = m.group(1).lower(), m.group(2)
    if host in ("github.com", "gitlab.com", "bitbucket.org"):
        return host, path, None
    for apex in ("github.com", "gitlab.com", "bitbucket.org"):
        if host.endswith("." + apex):  # <alias>.github.com is the usual multi-account SSH alias form
            return apex, path, "host %r looks like an SSH alias; assumed to be %s" % (host, apex)
    if "github" in host:
        return "github.com", path, "host %r looks like an SSH alias; assumed to be github.com" % host
    return host, path, "host taken from the remote as written"


def _seen_host(ctx, org: str):
    """A host that README or CI files use in https links under the same organisation: stronger than guessing."""
    from evidence import grep_files
    files = [n for n in README_NAMES if n in ctx.fileset] + list(ctx.ci_files)
    rx = r"https?://([\w.-]+)/" + re.escape(org) + r"/"
    for e in grep_files(ctx.repo, files, rx, 5):
        m = re.search(rx, e["snippet"])
        if m:
            return m.group(1).lower(), e
    return None


def _links(ctx, remote_fact) -> dict:
    out = {}
    w = _web(remote_fact["value"]) if remote_fact["value"] else None
    if not w:
        out["repository_url"] = fact(None, "NOT_FOUND", note="no usable origin remote")
        out["pipeline_url"] = fact(None, "NOT_FOUND", note="no usable origin remote")
        return out
    host, path, note = w
    extra = []
    if note:  # the remote's host is not trustworthy as a web host; look for the real one in the repo's own links
        seen = _seen_host(ctx, path.split("/")[0])
        if seen:
            host, ev0 = seen
            note, extra = "host taken from a link in the repository", [ev0]
    out["repository_url"] = fact("https://%s/%s" % (host, path), "INFERRED", remote_fact["evidence"] + extra,
                                 "derived from the git remote" + ("; " + note if note else ""))
    ci = ctx.ci_files
    pick = next((f for f in ci if f == ".gitlab-ci.yml"), None) or next((f for f in ci if f.startswith(".github/workflows/")), None) \
        or next((f for f in ci if f == ".circleci/config.yml"), None)
    url = None
    if pick == ".gitlab-ci.yml":
        url = "https://%s/%s/-/pipelines" % (host, path)
    elif pick and pick.startswith(".github/workflows/") and host == "github.com":
        url = "https://github.com/%s/actions" % path
    elif pick == ".circleci/config.yml" and host in ("github.com", "bitbucket.org"):
        url = "https://app.circleci.com/pipelines/%s/%s" % ("github" if host == "github.com" else "bitbucket", path)
    if url:
        out["pipeline_url"] = fact(url, "INFERRED", remote_fact["evidence"] + extra + [file_ev(pick, 1, (read_lines(ctx.repo, pick) or [""])[0])],
                                   "derived from the git remote and the CI file" + ("; " + note if note else ""))
    else:
        out["pipeline_url"] = fact(None, "NOT_FOUND", note="no CI system with a derivable pipeline URL")
    return out


def detect(ctx) -> dict:
    repo = ctx.repo
    out = {}
    rc, sha = run(["git", "rev-parse", "HEAD"], repo)
    is_git = rc == 0 and bool(sha)
    out["git_head"] = fact(sha, "CONFIRMED", [cmd_ev(["git", "rev-parse", "HEAD"], sha)]) if is_git \
        else fact(None, "NOT_FOUND", note="not a git repository or no commits")
    rc, url = run(["git", "remote", "get-url", "origin"], repo)
    url = _USERINFO.sub(r"\1", url) if rc == 0 else url  # never keep credentials embedded in an https remote
    out["git_remote"] = fact(url, "CONFIRMED", [cmd_ev(["git", "remote", "get-url", "origin"], url)]) \
        if rc == 0 and url else fact(None, "NOT_FOUND", note="no origin remote")
    out.update(_links(ctx, out["git_remote"]))
    out["about"] = _about(ctx)
    rc, st = run(["git", "status", "--porcelain", "--", ".", ":(exclude).modernise"], repo)
    n = len([l for l in st.splitlines() if l.strip()]) if rc == 0 else None
    out["working_tree_clean"] = fact({"clean": n == 0, "changed_files": n}, "CONFIRMED",
                                     [cmd_ev(["git", "status", "--porcelain"], "%d changed files" % n)],
                                     "facts describe the working tree, not only the commit in git_head") if n is not None \
        else fact(None, "NOT_FOUND", [], "not a git repository")
    out["owners"] = _owners(ctx)
    rc, br = run(["git", "rev-parse", "--abbrev-ref", "HEAD"], repo)
    out["git_branch"] = fact(br, "CONFIRMED", [cmd_ev(["git", "rev-parse", "--abbrev-ref", "HEAD"], br)]) \
        if rc == 0 and br else fact(None, "NOT_FOUND")
    if out["git_remote"]["value"]:
        name = re.sub(r"\.git$", "", out["git_remote"]["value"].rstrip("/").split("/")[-1].split(":")[-1])
        out["app_id"] = fact(name, "CONFIRMED", out["git_remote"]["evidence"], "basename of origin URL")
    else:
        out["app_id"] = fact(os.path.basename(os.path.abspath(repo)), "INFERRED", [],
                             "no origin remote; using directory name")
    mods = []
    ev = []
    for p in ctx.poms:
        mods.append(os.path.dirname(p) or ".")
        ev.append(file_ev(p, 1, open(os.path.join(repo, p), encoding="utf-8", errors="replace").readline()))
    for g in ([] if ctx.gradle_settings else ctx.gradle):  # with a settings file, only its include()s are modules
        mods.append(os.path.dirname(g) or ".")
        ev.append(file_ev(g, 1, (open(os.path.join(repo, g), encoding="utf-8", errors="replace").readline() or "")))
    gm = ctx.gradle_modules()
    for d, (f, i, ln) in sorted(gm.items()):
        mods.append(d)
        ev.insert(0, file_ev(f, i, ln))
    mods = sorted(set(mods))
    out["modules"] = fact(mods, "CONFIRMED" if mods else "NOT_FOUND", ev[:20],
                          "directories holding a pom.xml / build.gradle(.kts)")
    return out
