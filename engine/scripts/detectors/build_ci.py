from __future__ import annotations

import os
import re

from evidence import fact, grep_files, read_lines, file_ev

RESERVED = {"stages", "variables", "include", "default", "workflow", "image", "cache", "services",
            "before_script", "after_script", "pipeline", "on", "env", "jobs", "permissions", "name"}
BUILD_CMD = r"(?:^|[\s:&;|_\"'=-])(?:\./)?(?:mvnw?|gradlew?)\s+[^\n]*"


def _system(f: str) -> str:
    if f.endswith(".gitlab-ci.yml"):
        return "gitlab-ci"
    if f.startswith(".github/workflows/"):
        return "github-actions"
    if ".teamcity/" in f:
        return "teamcity"
    if "Jenkinsfile" in f or f.startswith("jenkins/"):
        return "jenkins"
    return {"Jenkinsfile": "jenkins", "azure-pipelines.yml": "azure-pipelines",
            "bitbucket-pipelines.yml": "bitbucket", ".circleci/config.yml": "circleci"}.get(f, "unknown")


VERSION = "0.2.0"


def detect(ctx) -> dict:
    r = ctx.repo
    out = {}
    systems = sorted({_system(f) for f in ctx.ci_files})
    ev = []
    for f in ctx.ci_files[:10]:
        ls = read_lines(r, f) or [""]
        ev.append(file_ev(f, 1, ls[0]))
    named = [] if systems else grep_files(r, [f for f in ("README.md", "README", "README.adoc", "README.rst") if f in ctx.fileset],
                                          r"(?i)\b(?:jenkins|teamcity|bamboo|circleci|travis|buildkite|github actions|gitlab ci)\b", 1)
    # a runbook in which a person runs the deploy (ansible-playbook, kubectl apply, helm upgrade, a promote script) is evidence too:
    # the deploy is not automated, whatever pipeline builds the artefact
    docs = [f for f in ctx.files if re.match(r"(?i)(?:readme|runbook|deploy(?:ment)?|release)[^/]*\.(?:md|adoc|rst|txt)$", os.path.basename(f))
            and not ctx._aux(f)][:8]
    manual = grep_files(r, docs, r"^\s*(?:\$\s*)?(?:ansible-playbook\s|kubectl\s+(?:apply|rollout)\b|helm\s+(?:upgrade|install|rollback)\b|\S*/promote\s)", 2)
    out["manual_deploy_documented"] = fact(bool(manual), "CONFIRMED" if manual else "NOT_FOUND", manual,
                                           "the documentation has a person run the deploy by hand" if manual else None)
    out["ci_system"] = fact(systems, "CONFIRMED", ev) if systems else \
        fact(["external"], "INFERRED", named, "no CI definition in the repository; the README names a CI server outside it") if named else \
        fact([], "NOT_FOUND", [], "no CI definition (.gitlab-ci.yml, Jenkinsfile, .github/workflows, ...) found")
    out["ci_files"] = fact(ctx.ci_files, "CONFIRMED" if ctx.ci_files else "NOT_FOUND", ev)
    # Jobs: top-level keys (GitLab) or keys indented 2 under a top-level `jobs:` (CircleCI, GitHub Actions)
    jobs, jev = [], []
    for f in [x for x in ctx.ci_files if x.endswith((".yml", ".yaml"))]:
        lines = read_lines(r, f) or []
        nested = any(re.match(r"^jobs:\s*$", ln) for ln in lines)
        in_jobs = False
        for i, ln in enumerate(lines, 1):
            if nested:
                if re.match(r"^jobs:\s*$", ln):
                    in_jobs = True
                    continue
                if in_jobs and re.match(r"^\S", ln):
                    in_jobs = False
                m = re.match(r"^  ([A-Za-z0-9_][A-Za-z0-9_.-]*):\s*$", ln) if in_jobs else None
            else:
                m = re.match(r"^([A-Za-z0-9_][A-Za-z0-9_.:/ -]*):\s*$", ln)
                m = m if m and m.group(1) not in RESERVED else None
            if m:
                jobs.append(m.group(1))
                jev.append(file_ev(f, i, ln))
    out["jobs"] = fact(sorted(set(jobs)), "CONFIRMED" if jobs else "NOT_FOUND", jev[:30])
    stages, sev = [], []
    for f in [x for x in ctx.ci_files if x.endswith(".gitlab-ci.yml")]:
        lines, on = read_lines(r, f) or [], False
        for i, ln in enumerate(lines, 1):
            if re.match(r"^stages:\s*$", ln):
                on = True
            elif on and re.match(r"^\s+-\s*\S", ln):
                stages.append(re.sub(r"^\s*-\s*", "", ln).strip())
                sev.append(file_ev(f, i, ln))
            elif on and not re.match(r"^\s*(#.*)?$", ln):
                on = False
    out["stages"] = fact(stages, "CONFIRMED" if stages else "NOT_FOUND", sev)
    inc = grep_files(r, [f for f in ctx.ci_files if f.endswith(".gitlab-ci.yml")],
                     r"^\s*-?\s*(local|project|remote|template):", 20)
    out["includes"] = fact([e["snippet"] for e in inc], "CONFIRMED" if inc else "NOT_FOUND", inc)
    unres = ctx.unresolved_ci_includes()
    out["unresolved_includes"] = fact(len(unres), "CONFIRMED" if unres else "NOT_FOUND", unres,
                                      "project/remote/template includes are not fetched (offline scan); "
                                      "jobs defined there are invisible")
    scripts = ctx.ci_scripts()
    note_s = "found only inside a script that CI calls (%s); which of its commands CI runs was not traced" % ", ".join(scripts[:3])

    def stage(rx, cmd_files=None, flags=re.I):
        """(evidence, status, note): CONFIRMED when a CI file itself shows it, INFERRED when only a script CI calls does."""
        hit = grep_files(r, cmd_files if cmd_files is not None else ctx.ci_files, rx, 5, flags=flags, continuation=True)
        if hit:
            return hit, "CONFIRMED", None
        hit = grep_files(r, scripts, rx, 5, flags=flags, continuation=True)
        return (hit, "INFERRED", note_s) if hit else ([], None, None)

    def put(key, hit, st, note, extra=None):
        out[key] = fact(bool(hit), st if hit else ("UNKNOWN" if unres else "NOT_FOUND"), hit, note or extra)

    hit, st, note = stage(BUILD_CMD + r"\b(package|install|build|assemble|compile|verify|test|check)\b")
    dg = ctx.default_goal_ci()  # `mvn --batch-mode` alone runs the pom's <defaultGoal>
    if not hit and dg:
        hit, st, note = dg[0][:3] + [dg[1]], "CONFIRMED", None
    if not hit:  # Jenkins pipelines name the step: stage('Build')
        hit, st, note = stage(r"\bstage\s*\(\s*['\"][^'\"]*[Bb]uild")
    put("build_step", hit, st, note)
    # a deployment: a deploy job/stage or a deploy tool. Not a case-insensitive "release" (an env var RELEASE_ID), not a
    # Maven `deploy` goal (that publishes), and not a throwaway test cluster (kind/minikube)
    DEPLOY = (r"^deploy[\w-]*:\s*$|^  deploy[\w-]*:\s*$|^\s+stage:\s*['\"]?deploy|nomad\s+job\s+run|kubectl\s+(?:apply|set image)"
              r"|helm\s+(?:upgrade|install)|\bstage\s*\(\s*['\"][^'\"]*[Dd]eploy")
    test_cluster = r"kind-action|kind\s+create\s+cluster|minikube\s+start|k3d\s+cluster\s+create"
    dep_files = [f for f in ctx.ci_files if not grep_files(r, [f], test_cluster, 1)]
    hit, st, note = stage(DEPLOY, dep_files, flags=0)
    put("deploy_step", hit, st, note)
    PUB = r"bintrayUpload|artifactory|publishTo|nexus|(?:mvnw?|gradlew?)\s+[^\n]*\b(?:deploy|publish\w*)\b|docker\s+push|npm\s+publish|\bjib\b"
    hit, st, note = stage(PUB)
    put("publish_step", hit, st, note, "publishes a build artefact (library/image) - not the same as deploying a service")
    ver = grep_files(r, ctx.build_files, r"CIRCLE_BUILD_NUM|CI_PIPELINE_IID|BUILD_NUMBER|GITHUB_RUN_NUMBER|BUILD_ID", 3)
    if not ver:  # the number reaches the artefact through the CI file: a -P/-D property, an image tag, a version argument
        ver = [e for e in grep_files(r, ctx.ci_files, r"\$\{?(CI_PIPELINE_I?ID|GITHUB_RUN_NUMBER|BUILD_NUMBER|CIRCLE_BUILD_NUM)\b", 12)
               if re.search(r"-P\w+=|-D\w+=|[Tt]ag|[Vv]ersion|IMAGE|image|:\$", e["snippet"])][:3]
    out["artifact_version_from_ci"] = fact(bool(ver), "CONFIRMED" if ver else "NOT_FOUND", ver,
                                           "artefact version is derived from the CI build number (not a git tag)")
    # a release that a pushed tag triggers, or a version derived from the tag: tags exist, but the pipeline did not create them
    trig = grep_files(r, ctx.ci_files, r"^\s{2,8}tags:\s*(?:\[|$|['\"])|\$CI_COMMIT_TAG|\bbuildingTag\(", 4, flags=0)
    out["release_triggered_by_tag"] = fact(bool(trig), "CONFIRMED" if trig else ("UNKNOWN" if unres else "NOT_FOUND"), trig,
                                           "the pipeline reacts to a pushed tag; who creates the tag is not visible")
    vtag = grep_files(r, ctx.ci_files + ctx.build_files, r"git\s+describe|GITHUB_REF(?:_NAME)?\b[^\n]*(?:tags|:10|#refs)|\bBUILD_TAG\b|\bshipkit\b|axion-release|nebula\.release|\bgitversion\b|CI_COMMIT_TAG", 4)
    out["version_from_git_tag"] = fact(bool(vtag), "CONFIRMED" if vtag else "NOT_FOUND", vtag,
                                       "the artefact version is taken from the git tag or `git describe`")
    # an image or artefact named after the commit: every build is traceable, but no release tag is created
    sha = grep_files(r, ctx.ci_files, r"git\s+rev-parse(?:\s+--short)?\s+HEAD|\$\{?(?:GIT_COMMIT|CI_COMMIT_SHORT_SHA|CI_COMMIT_SHA|GITHUB_SHA|BITBUCKET_COMMIT|CIRCLE_SHA1)\b", 3)
    out["artifact_tag_from_commit"] = fact(bool(sha), "CONFIRMED" if sha else "NOT_FOUND", sha,
                                           "the image or artefact is tagged with the commit; no release tag is created")
    # a release plugin in the build creates the tag when its task runs; who runs it (a person, an external job) is not visible
    rel = grep_files(r, ctx.build_files, r"net\.researchgate\.release|['\"]pl\.allegro\.tech\.build\.axion-release['\"]|maven-release-plugin|tagTemplate", 2)
    out["release_plugin_tags"] = fact(bool(rel), "CONFIRMED" if rel else "NOT_FOUND", rel,
                                      "a release plugin creates the version tag when its release task runs; nothing here shows the pipeline running it")
    tag = grep_files(r, ctx.ci_files, r"git\s+tag|semantic-release|release-please|versioning|\bgitversion\b|standard-version", 3)
    out["version_tagging"] = fact(bool(tag), "CONFIRMED" if tag else ("UNKNOWN" if unres else "NOT_FOUND"), tag)
    return out
