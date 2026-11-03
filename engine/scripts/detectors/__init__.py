"""Detector packs. Each module exposes detect(ctx) -> {fact_key: fact}. Order is fixed in ALL."""
from __future__ import annotations

import os
import re
from typing import List


class Ctx:
    """Shared, read-only view of the repo. Everything is derived from the sorted file walk."""

    CI_NAMES = (".gitlab-ci.yml", "Jenkinsfile", "azure-pipelines.yml", "bitbucket-pipelines.yml",
                ".circleci/config.yml")

    # Directories whose contents describe documentation, samples, benchmarks or developer tooling, not the application
    AUX_DIR = re.compile(r"(^|/)(?:[\w.-]*[-_])?(?:docs?|documentation|samples?|examples?|snippets?|demos?|archetype-resources|"
                         r"benchmarks?|jmh|fixtures?|__fixtures__|testdata|test-data)(?:[-_][\w.-]*)?/|(^|/)\.(?:devcontainer|gitpod|vscode|idea)/", re.I)
    # a module that only holds tests (okhttp's maven-tests, ktor's test, bff's test/journey): its src/main is test code
    TEST_MODULE = re.compile(r"(^|/)(?:[\w.-]*[-_]tests?|tests?[-_][\w.-]+|tests?|testing|its?|[\w.-]*-it-[\w.-]*)(/|$)", re.I)
    TEST_SRC_DIR = re.compile(r"/src/(?:test|integration-test|[A-Za-z0-9_]*Tests?)/")
    SOURCE_EXT = (".java", ".kt", ".groovy", ".scala")

    # Kotlin Multiplatform source sets (src/jvmMain, src/commonTest) and the <platform>/src, <platform>/test layout
    _PLAT = r"(?:common|jvm|js|native|posix|nix|darwin|ios|desktop|android|wasm\w*)"
    SRC_MAIN = re.compile(r"/src/main/|/src/(?![A-Za-z0-9_]*[Tt]est|jmh/|[A-Za-z0-9_]*[Bb]ench)[A-Za-z0-9_]+/(?:java|kotlin)/|/%s/src/" % _PLAT)
    SRC_TEST = re.compile(r"/src/(?:test|integrationTest|integration-test|intTest|it|[a-z][A-Za-z0-9]*Test)/|/%s/tests?/" % _PLAT)

    @classmethod
    def _aux(cls, f: str) -> bool:
        """Not the application: under a docs/samples/examples/benchmarks directory, or (for files that are not source code,
        e.g. a pom, Dockerfile or descriptor) inside a test source set. Only the directories above src/ count for source
        files: a Java package named `example` (com/example/...) is not a samples directory."""
        p = "/" + f
        if f.endswith(cls.SOURCE_EXT):
            head = p.split("/src/")[0] if "/src/" in p else os.path.dirname(p)
            return bool(cls.AUX_DIR.search(head + "/"))
        return bool(cls.AUX_DIR.search(os.path.dirname(p) + "/") or cls.TEST_SRC_DIR.search(p))

    @classmethod
    def _test_module(cls, f: str) -> bool:
        p = "/" + f
        head = p.split("/src/")[0] if "/src/" in p else os.path.dirname(p)
        return bool(cls.TEST_MODULE.search(head + "/"))

    def __init__(self, repo: str):
        from evidence import walk, grep_files, read_lines
        self.repo = repo
        self.files: List[str] = walk(repo)
        self.fileset = set(self.files)
        # build files under docs/samples/examples/snippets describe documentation, not the application: set aside, and
        # counted so the result can say so
        self.aux_build_files = [f for f in self.files if self._aux(f)
                                and (os.path.basename(f) == "pom.xml" or re.search(r"\.gradle(\.kts)?$", f))]
        main_files = [f for f in self.files if not self._aux(f)]
        self.poms = [f for f in main_files if os.path.basename(f) == "pom.xml"]
        # any *.gradle(.kts) except settings: settings.gradle may rename a module's build file (buildFileName)
        self.gradle = [f for f in main_files if re.search(r"\.gradle(\.kts)?$", f)
                       and not os.path.basename(f).startswith("settings.")]
        self.gradle_settings = [f for f in self.files if os.path.basename(f) in ("settings.gradle", "settings.gradle.kts")]
        self.build_files = self.poms + self.gradle
        self.ci_files = [f for f in self.files if f in self.CI_NAMES
                         or re.match(r"\.github/workflows/[^/]+\.ya?ml$", f)
                         or re.search(r"(^|/)[^/]*Jenkinsfile[^/]*$", f)  # Jenkinsfile, jenkins/X.Jenkinsfile
                         or re.match(r"jenkins/[^/]+\.groovy$", f)
                         or re.search(r"(^|/)\.teamcity/settings\.kts$", f)]
        # Resolve gitlab `include: local:` one level so jobs defined there are scanned too.
        extra: List[str] = []
        for f in self.ci_files:
            if f.endswith(".gitlab-ci.yml"):
                for e in grep_files(repo, [f], r"local:\s*['\"]?/?([^'\"\s]+)", limit=50):
                    m = re.search(r"local:\s*['\"]?/?([^'\"\s]+)", e["snippet"])
                    if m and m.group(1) in self.fileset and m.group(1) not in self.ci_files + extra:
                        extra.append(m.group(1))
        self.ci_files += extra
        self.mvn_config = [f for f in self.files if f in (".mvn/maven.config", ".mvn/jvm.config")]
        self.props = [f for f in self.files if re.search(
            r"(^|/)application[^/]*\.(properties|ya?ml)$", f) and "src/main" in f]
        # <sourceDirectory>/<testSourceDirectory> declared in a pom (e.g. guava: src, test) replace src/main, src/test.
        # Maven reads them relative to each module's own directory, so a parent pom's setting applies to every child
        # module whose <parent> resolves to it. A parent resolves the way Maven does it: <relativePath>, default ../pom.xml,
        # and only when that pom's artifactId equals the child's <parent><artifactId>.
        self.pom_src_dirs: dict = {"main": [], "test": []}
        info = {}
        for pth in self.poms:
            txt = "\n".join((read_lines(repo, pth) or [])[:400])
            par = re.search(r"<parent>(.*?)</parent>", txt, re.S)
            par_aid = re.search(r"<artifactId>\s*([^<\s]+)\s*<", par.group(1)) if par else None
            rel = re.search(r"<relativePath>\s*([^<]*?)\s*<", par.group(1)) if par else None
            own = re.sub(r"<parent>.*?</parent>", "", txt, flags=re.S)
            aid = re.search(r"<artifactId>\s*([^<\s]+)\s*<", own)
            dirs = [(m.group(1), m.group(2).strip()) for m in re.finditer(r"<(sourceDirectory|testSourceDirectory)>\s*([^<$]+?)\s*<", own)]
            parent_path = None
            if par_aid:
                rp = rel.group(1) if rel is not None and rel.group(1) else "../pom.xml"
                cand = os.path.normpath(os.path.join(os.path.dirname(pth), rp))
                cand = os.path.join(cand, "pom.xml") if not cand.endswith(".xml") else cand
                parent_path = cand.replace(os.sep, "/")
            info[pth] = (aid.group(1) if aid else None, par_aid.group(1) if par_aid else None, parent_path, dirs)
        children = {}
        for pth, (_, par_aid, parent_path, _) in info.items():
            if parent_path in info and info[parent_path][0] == par_aid:
                children.setdefault(parent_path, []).append(pth)

        self.pom_children = children  # parent pom path -> pom paths whose <parent> resolves to it

        def descendants(pth):
            return [c for ch in children.get(pth, []) for c in [ch] + descendants(ch)]
        for pth, (_, _, _, dirs) in info.items():
            for tag, val in dirs:
                kind = "test" if tag == "testSourceDirectory" else "main"
                for target in [pth] + descendants(pth):
                    d = os.path.normpath(os.path.join(os.path.dirname(target), val)).replace(os.sep, "/")
                    if not d.startswith("..") and d != "." and d not in self.pom_src_dirs[kind]:
                        self.pom_src_dirs[kind].append(d)
        # An Ant project (root build.xml, no root pom, no Gradle) is not a Maven project because publishing poms sit in a
        # subdirectory: those poms stay known for their source directories above, but are no longer "the build"
        self.nested_poms: List[str] = []
        if "pom.xml" not in self.fileset and "build.xml" in self.fileset and not self.gradle \
                and any("<project" in ln for ln in (read_lines(repo, "build.xml") or [])[:60]):
            self.nested_poms, self.poms = self.poms, []
            self.build_files = self.gradle
        in_dir = lambda f, ds: any(f.startswith(d + "/") for d in ds)
        self.src_main_java = [f for f in main_files if f.endswith((".java", ".kt")) and not self._test_module(f)
                              and (self.SRC_MAIN.search("/" + f) or in_dir(f, self.pom_src_dirs["main"]))]
        self.src_test = [f for f in main_files if (self.SRC_TEST.search("/" + f) and "/src/main/" not in "/" + f)
                         or in_dir(f, self.pom_src_dirs["test"])]
        self.test_sources = [f for f in self.src_test if f.endswith((".java", ".kt", ".groovy", ".scala"))]
        self.deploy_files = [f for f in main_files if re.search(
            r"\.(nomad|hcl)$|(^|/)(k8s|kubernetes|deploy|helm|charts?|manifests?)/.*\.ya?ml$|(^|/)values[^/]*\.ya?ml$"
            r"|(^|/)Chart\.ya?ml$|(^|/)docker-compose[^/]*\.ya?ml$", f)]

    def ci_jobs(self) -> List[dict]:
        """CI jobs with their file/line, stage, trigger target project and whether they have a script.
        GitLab-style top-level jobs, or keys two spaces under a top-level `jobs:` (CircleCI, GitHub Actions)."""
        from evidence import read_lines
        reserved = {"stages", "variables", "include", "default", "workflow", "image", "cache", "services", "before_script",
                    "after_script", "pipeline", "on", "env", "jobs", "permissions", "name", "version", "orbs", "workflows"}
        out = []
        for f in [x for x in self.ci_files if x.endswith((".yml", ".yaml"))]:
            lines = read_lines(self.repo, f) or []
            nested = any(re.match(r"^jobs:\s*$", ln) for ln in lines)
            ind = 2 if nested else 0
            pat = re.compile(r"^%s([A-Za-z0-9_][A-Za-z0-9_.-]*):\s*$" % (" " * ind))
            in_jobs = not nested
            starts = []
            for i, ln in enumerate(lines):
                if nested and re.match(r"^jobs:\s*$", ln):
                    in_jobs = True
                    continue
                if nested and in_jobs and re.match(r"^\S", ln):
                    in_jobs = False
                m = pat.match(ln) if in_jobs else None
                if m and m.group(1) not in reserved and not m.group(1).startswith("."):
                    starts.append((i, m.group(1)))
            for n, (i, name) in enumerate(starts):
                end = starts[n + 1][0] if n + 1 < len(starts) else len(lines)
                blk = [l for l in lines[i + 1:end]]
                text = "\n".join(blk)
                stage = re.search(r"^\s+stage:\s*[\"']?([\w.-]+)", text, re.M)
                trig = re.search(r"^\s+trigger:\s*\n(?:\s+\w+:.*\n)*?\s+project:\s*[\"']?([^\"'\s]+)", text + "\n", re.M)
                out.append({"file": f, "line": i + 1, "text": lines[i], "name": name,
                            "stage": stage.group(1) if stage else None,
                            "trigger_project": trig.group(1) if trig else None,
                            "has_script": bool(re.search(r"^\s+(script|steps|run):", text, re.M))})
        return out

    def gradle_modules(self):
        """(dir, evidence line) for each project included by settings.gradle(.kts), honouring projectDir overrides."""
        from evidence import read_lines
        mods = {}
        for f in self.gradle_settings:
            lines = read_lines(self.repo, f) or []
            base = os.path.dirname(f)
            dirs = {}
            for i, ln in enumerate(lines, 1):
                if ln.strip().startswith("//"):
                    continue
                m = re.search(r"project\(\s*[\"']:?([\w:.-]+)[\"']\s*\)\.projectDir\s*=\s*(?:file|File)\(\s*[\"']([^\"']+)[\"']", ln)
                if m:
                    dirs[m.group(1)] = m.group(2)
            for i, ln in enumerate(lines, 1):
                if ln.strip().startswith("//"):
                    continue
                m = re.match(r"\s*include\s*\(?\s*(.+?)\)?\s*$", ln)
                if not m:
                    continue
                for name in re.findall(r"[\"']:?([\w:.-]+)[\"']", m.group(1)):
                    d = dirs.get(name) or name.replace(":", "/")
                    mods["/".join(x for x in (base, d) if x)] = (f, i, ln)
            mods.setdefault(base or ".", (f, 1, lines[0] if lines else ""))
        return mods

    def module_dirs(self) -> List[str]:
        """Directories that hold a build file or are included by settings.gradle; "." is the repository root."""
        if not hasattr(self, "_module_dirs"):
            ds = {os.path.dirname(f) or "." for f in self.poms + self.gradle}
            ds |= set(self.gradle_modules())
            self._module_dirs = sorted(ds)
        return self._module_dirs

    def module_of(self, path: str) -> str:
        """Nearest enclosing module directory of a repo-relative path (longest prefix); "." when none matches."""
        best = "."
        for d in self.module_dirs():
            if d != "." and (path == d or path.startswith(d + "/")) and len(d) > len(best if best != "." else ""):
                best = d
        return best

    def ci_scripts(self):
        """Repository scripts that a CI file calls (`./go build`, `bash util/deploy.sh`), one level deep, small files only.
        What CI does inside them is not traced: callers must treat a hit in one as INFERRED, never CONFIRMED."""
        if getattr(self, "_ci_scripts", None) is not None:
            return self._ci_scripts
        from evidence import grep_files
        found = []
        for e in grep_files(self.repo, self.ci_files, r"(?:^|[\s:&;|'\"-])(?:\./|bash\s+|sh\s+)([\w./-]+)", 400):
            for m in re.finditer(r"(?:^|[\s:&;|'\"-])(?:\./|bash\s+|sh\s+)([\w./-]+)", e["snippet"]):
                rel = os.path.normpath(m.group(1)).replace(os.sep, "/")
                if rel in self.fileset and rel not in self.ci_files and rel not in found \
                        and os.path.basename(rel) not in ("gradlew", "mvnw") and not self._aux(rel) \
                        and os.path.getsize(os.path.join(self.repo, rel)) <= 65536:
                    found.append(rel)
        self._ci_scripts = sorted(found)[:20]
        return self._ci_scripts

    def default_goal_ci(self):
        """CI lines that run Maven with options only (no goal), when the root pom's <defaultGoal> names a lifecycle phase.
        Returns (ci_lines, pom_line) or None. Without the pom line a goal-less `mvn` proves nothing, so it returns None."""
        from evidence import grep_files
        root = [f for f in self.poms if f == "pom.xml"]
        goal = grep_files(self.repo, root, r"<defaultGoal>[^<]*\b(test|verify|package|install)\b", 1)
        if not goal:
            return None
        lines = [e for e in grep_files(self.repo, self.ci_files, r"(?:^|[\s:&;|-])(?:\./)?mvnw?(?:\s|$)", 20)
                 if not [t for t in re.split(r"\s+", re.split(r"mvnw?", e["snippet"], 1)[-1].strip()) if t and not t.startswith("-")]]
        return (lines, goal[0]) if lines else None

    def unresolved_ci_includes(self) -> List[dict]:
        """Remote/project/template includes whose content this scan cannot see."""
        from evidence import grep_files
        return grep_files(self.repo, [f for f in self.ci_files if f.endswith(".gitlab-ci.yml")],
                          r"^\s*-?\s*(project|remote|template):", limit=20)
