"""Where the repositories come from: local paths, or lists of local paths and remote URLs in .csv, .tsv, .xlsx or .txt.

A list file may have a header row. The column holding the repository is the first one named url, repo, repository,
git, git_url, clone_url, path or location (any case); without such a header the first column is used. Optional
columns: name, branch (or ref), team, criticality. Lines in .txt files are "<url-or-path> [branch]"; # starts a comment.

Remote repositories are cloned shallow into the client workspace with the user's own git credentials (SSH agent or
credential helper). Nothing is stored by this tool and git is never allowed to prompt, so a missing credential fails
that one repository instead of hanging the run. A URL that carries a credential (user:token@, a token as the user name, a
token in the query) is refused before anything is fetched, and only its masked form is ever kept: git would otherwise write
it into the clone's .git/config, and the run record would hold it.
"""
from __future__ import annotations

import csv
import hashlib
import io
import os
import re
import subprocess
import zipfile
from concurrent.futures import ThreadPoolExecutor
from xml.etree import ElementTree

REMOTE = re.compile(r"^(?:https?://|ssh://|git://|git@[^:]+:)")
# user info in an http(s)/git URL (a token is often passed as the user name), a password in an ssh URL, a token in the query
_CRED_USER = re.compile(r"^((?:https?|git|ftp)://)([^/@\s]+)@", re.I)
_CRED_SSH = re.compile(r"^(ssh://[^/@:\s]*):([^/@\s]*)@", re.I)
_CRED_QUERY = re.compile(r"(?i)([?&](?:private_token|access_token|token|password|passwd|pwd|key|apikey|api_key|secret)=)[^&\s]+")
REFUSED = "refused: the URL carries a credential; remove it and use your SSH agent or git credential helper"


def credentialed(spec):
    return bool(_CRED_USER.match(spec) or _CRED_SSH.match(spec) or _CRED_QUERY.search(spec))


def mask(spec):
    """The URL with any credential replaced: the only form of a credentialed URL that is kept or printed."""
    spec = _CRED_USER.sub(lambda m: m.group(1) + "[REDACTED]@", spec)
    spec = _CRED_SSH.sub(lambda m: m.group(1) + ":[REDACTED]@", spec)
    return _CRED_QUERY.sub(lambda m: m.group(1) + "[REDACTED]", spec)


REPO_COLS = ("url", "repo", "repository", "git", "git_url", "clone_url", "repo_url", "repository_url", "path", "location")


class Source:
    def __init__(self, spec, name=None, branch=None, team=None, criticality=None, row=None):
        spec = spec.strip()
        self.remote = bool(REMOTE.match(spec))
        self.path, self.status, self.error, self.commit, self.changed_files = None, "pending", None, None, None
        if self.remote and credentialed(spec):  # never fetched, never stored as given
            spec, self.status, self.error = mask(spec), "failed", REFUSED
        self.spec, self.name, self.branch, self.team, self.criticality, self.row = spec, name or None, branch or None, team or None, criticality or None, row
        self._slug = None

    def slug(self):
        """The clone folder: host and full path for a remote (teamA/payments/api and teamB/payments/api never share one)."""
        if self._slug:
            return self._slug
        if self.name:
            return re.sub(r"[^\w.-]+", "_", self.name)
        s = re.sub(r"\.git$", "", self.spec.rstrip("/"))
        if not self.remote:
            return os.path.basename(os.path.abspath(s))
        s = re.sub(r"^[a-z][a-z0-9+.-]*://", "", s, flags=re.I)
        s = re.sub(r"^[^@/]*@", "", s)
        return re.sub(r"[^\w.-]+", "_", "__".join(p for p in re.split(r"[/:]", s) if p))

    def as_dict(self):
        return {"spec": self.spec, "name": self.name, "branch": self.branch, "team": self.team, "criticality": self.criticality, "remote": self.remote,
                "path": self.path, "status": self.status, "error": self.error, "commit": self.commit, "changed_files": self.changed_files, "row": self.row}


def _rows_to_sources(rows, origin):
    rows = [[(c or "").strip() for c in r] for r in rows if any((c or "").strip() for c in r)]
    if not rows:
        return []
    head = [h.lower().replace(" ", "_") for h in rows[0]]
    col = next((head.index(c) for c in REPO_COLS if c in head), None)
    if col is None:
        col, body, head = 0, rows, []
    else:
        body = rows[1:]
    get = lambda r, *names: next((r[head.index(n)] for n in names if n in head and head.index(n) < len(r) and r[head.index(n)]), None)  # noqa: E731
    out = []
    for i, r in enumerate(body, start=2 if head else 1):
        if col < len(r) and r[col] and not r[col].startswith("#"):
            out.append(Source(r[col], get(r, "name", "app", "application"), get(r, "branch", "ref"), get(r, "team", "owner"), get(r, "criticality", "tier"), "%s:%d" % (origin, i)))
    return out


def _xlsx_rows(path):
    """First worksheet of an .xlsx as rows of strings, read with the standard library (no openpyxl needed)."""
    ns = {"m": "http://schemas.openxmlformats.org/spreadsheetml/2006/main"}
    with zipfile.ZipFile(path) as z:
        shared = []
        if "xl/sharedStrings.xml" in z.namelist():
            for si in ElementTree.fromstring(z.read("xl/sharedStrings.xml")).findall("m:si", ns):
                shared.append("".join(t.text or "" for t in si.iter("{%s}t" % ns["m"])))
        sheets = sorted(n for n in z.namelist() if re.match(r"xl/worksheets/sheet\d+\.xml$", n))
        if not sheets:
            return []
        root = ElementTree.fromstring(z.read(sheets[0]))
    rows = []
    for row in root.iter("{%s}row" % ns["m"]):
        cells = {}
        for c in row.findall("m:c", ns):
            ref = re.match(r"([A-Z]+)", c.get("r", "A"))
            idx = 0
            for ch in ref.group(1):
                idx = idx * 26 + ord(ch) - 64
            v = c.find("m:v", ns)
            if c.get("t") == "s" and v is not None:
                text = shared[int(v.text)]
            elif c.get("t") == "inlineStr":
                text = "".join(t.text or "" for t in c.iter("{%s}t" % ns["m"]))
            else:
                text = v.text if v is not None else ""
            cells[idx - 1] = text or ""
        if cells:
            rows.append([cells.get(i, "") for i in range(max(cells) + 1)])
    return rows


def read_list(path):
    ext = os.path.splitext(path)[1].lower()
    if ext == ".xlsx":
        return _rows_to_sources(_xlsx_rows(path), os.path.basename(path))
    with open(path, encoding="utf-8-sig") as fh:
        text = fh.read()
    if ext in (".csv", ".tsv"):
        return _rows_to_sources(list(csv.reader(io.StringIO(text), delimiter="\t" if ext == ".tsv" else ",")), os.path.basename(path))
    out = []
    for i, ln in enumerate(text.splitlines(), start=1):
        ln = ln.split("#", 1)[0].strip() if not ln.strip().startswith("http") else re.sub(r"\s+#.*$", "", ln.strip())
        if ln:
            parts = ln.split()
            out.append(Source(parts[0], branch=parts[1] if len(parts) > 1 else None, row="%s:%d" % (os.path.basename(path), i)))
    return out


def expand(args):
    """Command-line inputs -> sources. An argument is a list file, a directory holding repositories, a repository, or a URL."""
    out = []
    for a in args:
        if REMOTE.match(a):
            out.append(Source(a))
        elif os.path.isfile(a):
            out.extend(read_list(a))
        elif os.path.isdir(os.path.join(a, ".git")) or not os.path.isdir(a):
            out.append(Source(a))
        else:  # a folder of repositories
            subs = sorted(os.path.join(a, d) for d in os.listdir(a) if os.path.isdir(os.path.join(a, d, ".git")))
            out.extend(Source(s) for s in subs) if subs else out.append(Source(a))
    seen, uniq = set(), []
    for s in out:
        key = s.spec if s.remote else os.path.abspath(s.spec)
        if key not in seen:
            seen.add(key)
            uniq.append(s)
    slugs = [s.slug() for s in uniq if s.remote]
    for s in uniq:  # two sources that would share a clone folder (the same list name twice) get a suffix from their URL
        if s.remote and slugs.count(s.slug()) > 1:
            s._slug = "%s--%s" % (s.slug(), hashlib.sha1(s.spec.encode()).hexdigest()[:8])
    return uniq


def _git(args, cwd=None, timeout=900):
    env = dict(os.environ, GIT_TERMINAL_PROMPT="0", GIT_ASKPASS="echo", SSH_ASKPASS="echo", GCM_INTERACTIVE="never")
    return subprocess.run(["git"] + args, cwd=cwd, env=env, capture_output=True, text=True, timeout=timeout)


def _head(path):
    r = _git(["rev-parse", "HEAD"], cwd=path, timeout=30)
    return r.stdout.strip() if r.returncode == 0 else None


def _changed(path):
    r = _git(["status", "--porcelain"], cwd=path, timeout=30)
    return len([l for l in r.stdout.splitlines() if l.strip()]) if r.returncode == 0 else None


def fetch(src, repos_dir, update=True):
    """Make one source available on disk. Local paths are used where they are; remote ones are cloned or refreshed."""
    if src.error == REFUSED:
        return src
    try:
        if not src.remote:
            p = os.path.abspath(os.path.expanduser(src.spec))
            if not os.path.isdir(p):
                src.status, src.error = "failed", "local path not found"
                return src
            src.path, src.status, src.commit = p, "local", _head(p)
            src.changed_files = _changed(p)  # the scan reads the working tree: uncommitted changes mean it is not exactly the commit
            return src
        dest = os.path.join(repos_dir, src.slug())
        if os.path.isdir(os.path.join(dest, ".git")):
            if update:
                r = _git(["fetch", "--depth", "1", "origin", src.branch or "HEAD"], cwd=dest)
                if r.returncode == 0:
                    r = _git(["reset", "--hard", "FETCH_HEAD"], cwd=dest)
                src.status = "updated" if r.returncode == 0 else "stale"
                if r.returncode != 0:
                    src.error = "update failed, using the previous clone: " + (r.stderr.strip().splitlines() or ["?"])[-1]
            else:
                src.status = "cached"
        else:
            os.makedirs(repos_dir, exist_ok=True)
            r = _git(["clone", "--depth", "1", "--single-branch"] + (["--branch", src.branch] if src.branch else []) + [src.spec, dest])
            if r.returncode != 0:
                src.status, src.error = "failed", (r.stderr.strip().splitlines() or ["git clone failed"])[-1]
                return src
            src.status = "cloned"
        src.path, src.commit = dest, _head(dest)
    except subprocess.TimeoutExpired:
        src.status, src.error = "failed", "git timed out"
    return src


def fetch_all(sources, repos_dir, jobs=4, update=True, progress=None):
    def one(s):
        fetch(s, repos_dir, update)
        if progress:
            progress(s)
        return s
    with ThreadPoolExecutor(max_workers=max(1, jobs)) as ex:
        return list(ex.map(one, sources))
