"""What this scan read, and what the repository points to that it cannot read.

files_read: the files each area of the scan searched (build, CI, configuration, deployment, source, tests, docs), so a
"not found" can say where it looked.

blind_spots: places the repository itself names where a missing setting may live instead: a parent POM or Gradle plugin
from outside the repository, a CI template from another project, a Jenkins shared library, a config server, a CI system or
build tool this scan does not parse, deployment defined in a tool it does not read. Each cites the line that names it. A
check that finds nothing in an area with a blind spot cannot say "missing"; the product reports it as not decidable."""
from __future__ import annotations

import os
import re

from evidence import fact, file_ev, grep_files, read_lines


VERSION = "0.2.0"

# parents whose contents are public and known not to configure scanners, coverage gates or deploy steps
PUBLIC_PARENT = re.compile(r"^(?:org\.springframework|io\.spring|org\.apache|org\.sonatype|io\.quarkus|io\.micronaut|io\.dropwizard|org\.jboss|"
                           r"com\.google|io\.helidon|org\.eclipse|io\.vertx|org\.jetbrains|org\.codehaus|org\.basepom|com\.fasterxml|io\.netty)\b")
# CI systems whose files this scan does not parse: their presence means the pipeline exists but was not read
UNREAD_CI = [(r"^\.travis\.ya?ml$", "Travis CI"), (r"^buildspec[^/]*\.ya?ml$", "AWS CodeBuild"), (r"^cloudbuild[^/]*\.ya?ml$", "Google Cloud Build"),
             (r"^\.drone\.ya?ml$", "Drone"), (r"^\.buildkite/", "Buildkite"), (r"^bamboo-specs/", "Bamboo"), (r"^\.tekton/", "Tekton"),
             (r"^appveyor\.ya?ml$", "AppVeyor"), (r"^\.semaphore/", "Semaphore"), (r"^codefresh\.ya?ml$", "Codefresh"),
             (r"^\.woodpecker(?:\.ya?ml|/)", "Woodpecker"), (r"^\.teamcity/", "TeamCity")]
UNREAD_BUILD = [(r"^build\.sbt$", "sbt"), (r"^(?:WORKSPACE|WORKSPACE\.bazel|MODULE\.bazel)$", "Bazel"), (r"^build\.sc$", "Mill"), (r"^project\.clj$", "Leiningen")]
# deployment defined in tools whose files the availability checks do not read
UNREAD_DEPLOY = [(r"\.tf$", "Terraform", r"\bresource\s+\"(?:aws_ecs_service|aws_ecs_task_definition|aws_instance|aws_autoscaling_group|aws_lambda_function|aws_elastic_beanstalk\w*|azurerm_\w*app\w*|google_cloud_run\w*|google_compute_instance\w*|kubernetes_\w+|helm_release)\""),
                 (r"(?:^|/)[^/]*task-?def[^/]*\.json$", "an ECS task definition", r"\"containerDefinitions\""),
                 (r"\.(?:ya?ml|json|template)$", "CloudFormation / SAM", r"^\s*(?:AWSTemplateFormatVersion|Transform:\s*['\"]?AWS::Serverless)"),
                 (r"(?:^|/)manifest[^/]*\.ya?ml$", "Cloud Foundry", r"^\s*applications:\s*$"),
                 (r"(?:^|/)serverless\.ya?ml$", "the Serverless Framework", r"^\s*provider:\s*$"),
                 (r"(?:^|/)app\.ya?ml$", "Google App Engine", r"^\s*runtime:\s*java"),
                 (r"(?:^|/)\.ebextensions/", "Elastic Beanstalk", r"."),
                 (r"\.ya?ml$", "OpenShift", r"^\s*kind:\s*DeploymentConfig\b"),
                 (r"(?:^|/)Pulumi\.ya?ml$", "Pulumi", r"^\s*runtime:"),
                 (r"(?:^|/)cdk\.json$", "the AWS CDK", r"\"app\"\s*:")]
# configuration read at run time from somewhere this scan cannot see
EXTERNAL_CONFIG = [
    (r"configserver:|^\s*spring\.cloud\.config\.(?:uri|discovery\.enabled)\s*[=:]", "a Spring Cloud Config server"),
    (r"^\s*spring\.cloud\.(?:consul|zookeeper|nacos|kubernetes)\.config\.|import\s*[=:].*\b(?:consul|zookeeper|nacos):", "a config service (Consul, ZooKeeper, Nacos, Kubernetes)"),
    (r"aws-parameterstore:|aws-appconfig:|^\s*spring\.cloud\.aws\.paramstore\.", "AWS Parameter Store / AppConfig"),
    (r"configtree:", "a mounted config tree (Kubernetes ConfigMap or Secret)"),
    (r"(?i)spring[._]config[._](?:additional[._-])?location(?![=:\s\"']*(?:optional:)?classpath:)", "configuration files outside the repository (spring.config.location)"),
]


def _areas(ctx):
    conf = ctx.props + [f for f in ctx.files if re.search(r"(^|/)(?:bootstrap[^/]*\.(?:properties|ya?ml)|(?:logback|log4j2)[^/]*\.xml)$", f)
                        and "src/test" not in f and not ctx._aux(f)]
    docs = [f for f in ctx.files if re.match(r"(?i)(?:readme|runbook|deploy(?:ment)?|release|contributing)[^/]*\.(?:md|adoc|rst|txt)$", os.path.basename(f))
            and not ctx._aux(f)]
    return {"build": ctx.build_files + [f for f in ctx.gradle_settings if f not in ctx.build_files], "ci": ctx.ci_files + ctx.ci_scripts(),
            "config": sorted(set(conf)), "deploy": ctx.deploy_files, "main_source": ctx.src_main_java, "test_source": ctx.test_sources, "docs": docs}


def files_read(ctx):
    areas = _areas(ctx)
    ev = []
    for k in ("build", "ci", "config", "deploy", "docs"):
        if areas[k]:
            ln = (read_lines(ctx.repo, areas[k][0]) or [""])[:1] or [""]
            ev.append(file_ev(areas[k][0], 1, ln[0]))
    value = {k: {"count": len(v), "files": v[:8]} for k, v in areas.items()}
    return fact(value, "CONFIRMED" if ev else "NOT_FOUND", ev)


def _maven_parent(ctx):
    if "pom.xml" not in ctx.poms:
        return []
    lines = read_lines(ctx.repo, "pom.xml") or []
    txt = "\n".join(lines[:200])
    par = re.search(r"<parent>(.*?)</parent>", txt, re.S)
    if not par:
        return []
    gid = re.search(r"<groupId>\s*([^<\s]+)\s*<", par.group(1))
    aid = re.search(r"<artifactId>\s*([^<\s]+)\s*<", par.group(1))
    if not gid or PUBLIC_PARENT.match(gid.group(1)):
        return []
    rel = re.search(r"<relativePath>\s*([^<]*?)\s*<", par.group(1))
    rp = os.path.normpath(rel.group(1) if rel and rel.group(1) else "../pom.xml")
    if not rp.startswith("..") and (rp if rp.endswith(".xml") else os.path.join(rp, "pom.xml")) in ctx.fileset:
        return []  # the parent is in this repository, and was read with the other poms
    at = next((i for i, ln in enumerate(lines, 1) if gid.group(1) in ln and "<groupId>" in ln), None)
    if not at:
        return []
    return [{"id": "build.parent_pom", "area": "build", "what": "a parent POM from outside this repository (%s:%s), which may configure plugins, coverage and scanners"
             % (gid.group(1), aid.group(1) if aid else "?"), "ev": [file_ev("pom.xml", at, lines[at - 1])]}]


def _gradle_external(ctx):
    out = []
    remote = grep_files(ctx.repo, ctx.build_files, r"apply\s*\(?\s*from\s*[:=]\s*['\"]https?://", 2)
    if remote:
        out.append({"id": "build.remote_script", "area": "build", "what": "a Gradle script loaded from a URL, which this scan does not fetch", "ev": remote})
    grp = grep_files(ctx.repo, [f for f in ctx.build_files if os.path.dirname(f) == ""] + [f for f in ctx.files if f == "gradle.properties"],
                     r"^\s*(?:allprojects\s*\{\s*)?group\s*=\s*['\"]?[a-z][\w.]*", 1)
    m = re.search(r"group\s*=\s*['\"]?([a-z][\w]*\.[\w]+)", grp[0]["snippet"]) if grp else None
    if m:
        own = re.escape(m.group(1))
        hits = grep_files(ctx.repo, ctx.build_files, r"\bid\s*\(?\s*['\"]%s\.[\w.-]+['\"]|classpath\s*\(?\s*['\"]%s[\w.-]*:" % (own, own), 3)
        # a plugin that the repository builds itself (buildSrc, build-logic, an included build) is read with the other build files
        local = {os.path.basename(f).replace(".gradle.kts", "").replace(".gradle", "") for f in ctx.files if re.search(r"(^|/)(?:buildSrc|build-logic|gradle/plugins)/", f)}
        hits = [h for h in hits if not any(n and n in h["snippet"] for n in local)]
        if hits:
            out.append({"id": "build.org_plugin", "area": "build", "what": "a Gradle plugin published by the same organisation (%s...), which may configure coverage, scanners or publishing" % m.group(1),
                        "ev": hits[:2]})
    return out


def _ci(ctx):
    out = []
    inc = ctx.unresolved_ci_includes()
    if inc:
        out.append({"id": "ci.remote_include", "area": "ci", "what": "GitLab CI templates from another project, which this scan does not fetch", "ev": inc[:2]})
    jen = [f for f in ctx.ci_files if "Jenkinsfile" in f or f.startswith("jenkins/")]
    lib = grep_files(ctx.repo, jen, r"^\s*@Library\s*\(|^\s*library\s*\(?\s*['\"]", 2)
    if lib:
        out.append({"id": "ci.shared_library", "area": "ci", "what": "a Jenkins shared library, whose steps this scan cannot see", "ev": lib})
    gh = [f for f in ctx.ci_files if f.startswith(".github/workflows/")]
    reuse = grep_files(ctx.repo, gh, r"^\s*(?:-\s*)?uses:\s*['\"]?[\w.-]+/[\w.-]+/\.github/workflows/", 2)
    if reuse:
        out.append({"id": "ci.reusable_workflow", "area": "ci", "what": "a reusable GitHub workflow from another repository, which this scan does not fetch", "ev": reuse})
    az = grep_files(ctx.repo, [f for f in ctx.ci_files if "azure-pipelines" in f], r"^\s*-?\s*template:\s*\S+@\S+", 2)
    if az:
        out.append({"id": "ci.azure_template", "area": "ci", "what": "Azure Pipelines templates from another repository, which this scan does not fetch", "ev": az})
    for rx, name in UNREAD_CI:
        fs = [f for f in ctx.files if re.search(rx, f)]
        if fs:
            ln = (read_lines(ctx.repo, fs[0]) or [""])[:1] or [""]
            out.append({"id": "ci.unread_system", "area": "ci", "what": "a %s pipeline, which this scan does not parse" % name, "ev": [file_ev(fs[0], 1, ln[0])]})
    return out


def _build_tool(ctx):
    out = []
    for rx, name in UNREAD_BUILD:
        fs = [f for f in ctx.files if re.search(rx, f)]
        if fs:
            ln = (read_lines(ctx.repo, fs[0]) or [""])[:1] or [""]
            out.append({"id": "build.unread_tool", "area": "build", "what": "a %s build, which this scan does not parse" % name, "ev": [file_ev(fs[0], 1, ln[0])]})
    if "build.xml" in ctx.fileset and not ctx.poms and not ctx.gradle:
        ln = (read_lines(ctx.repo, "build.xml") or [""])[:1] or [""]
        out.append({"id": "build.unread_tool", "area": "build", "what": "an Ant build, which this scan does not parse", "ev": [file_ev("build.xml", 1, ln[0])]})
    return out


def _config(ctx, areas):
    out = []
    where = areas["config"] + areas["deploy"] + areas["ci"] + [f for f in ctx.files if os.path.basename(f).startswith("Dockerfile")]
    for rx, name in EXTERNAL_CONFIG:
        hits = [e for e in grep_files(ctx.repo, where, rx, 4) if not e["snippet"].lstrip().startswith("#")]
        if hits:
            out.append({"id": "config.external", "area": "config", "what": "settings read at run time from %s, which this scan cannot see" % name, "ev": hits[:2]})
    return out


def _deploy(ctx):
    out, seen = [], set()
    main = [f for f in ctx.files if not ctx._aux(f) and "src/test" not in f]
    for path_rx, name, body_rx in UNREAD_DEPLOY:
        fs = [f for f in main if re.search(path_rx, f)][:200]
        hits = grep_files(ctx.repo, fs, body_rx, 1) if fs else []
        if hits and name not in seen:
            seen.add(name)
            out.append({"id": "deploy.unread_tool", "area": "deploy", "what": "deployment defined with %s, which the availability checks do not read" % name, "ev": hits})
    return out


# positive markers that deployment is handed to GitOps: the manifests or the deploy itself live in another repository or a
# controller. An image published with no deploy step is not one: that is also the shape of a manual deploy.
GITOPS_FILE = [(r"^\s*apiVersion:\s*argoproj\.io/\S+", r"^\s*kind:\s*(?:Application|ApplicationSet|AppProject)\s*$", "Argo CD"),
               (r"^\s*apiVersion:\s*(?:kustomize|helm|source|image)\.toolkit\.fluxcd\.io/\S+", r".", "Flux"),
               (r"argocd-image-updater\.argoproj\.io/", r".", "Argo CD Image Updater")]
MANIFEST_REPO = r"git\s+clone\b[^\n]*(?:gitops|manifest|deploy|k8s|kube|helm|charts?|environments?|infra)[\w.-]*"
SET_IMAGE = r"kustomize\s+edit\s+set\s+image|\byq\b[^\n]*\bimage\b|\bsed\b[^\n]*\bimage:|helm-?docs?\b[^\n]*\bset\b[^\n]*image"


def _gitops(ctx):
    out = []
    ymls = [f for f in ctx.files if f.endswith((".yml", ".yaml")) and not ctx._aux(f) and "src/test" not in f][:2000]
    for api, kind, name in GITOPS_FILE:
        for f in ymls:
            hit = grep_files(ctx.repo, [f], api, 1)
            if hit and grep_files(ctx.repo, [f], kind, 1, flags=0):
                out.append({"id": "deploy.gitops", "area": "deploy", "what": "deployment handed to %s, whose target manifests this scan cannot see" % name, "ev": hit})
                break
    ci = ctx.ci_files + ctx.ci_scripts()
    for f in ci:  # a pipeline that updates a manifest repository: the deploy happens when that repository is synced
        push = grep_files(ctx.repo, [f], r"\bgit\s+push\b", 1)
        moved = grep_files(ctx.repo, [f], MANIFEST_REPO, 1) or grep_files(ctx.repo, [f], SET_IMAGE, 1)
        if push and moved:
            out.append({"id": "deploy.gitops", "area": "deploy", "what": "a pipeline step that pushes to a manifest repository (GitOps), whose deploy this scan cannot see",
                        "ev": moved[:1] + push[:1]})
            break
    return out


def blind_spots(ctx, areas):
    spots = _maven_parent(ctx) + _gradle_external(ctx) + _build_tool(ctx) + _ci(ctx) + _config(ctx, areas) + _deploy(ctx) + _gitops(ctx)
    ev = [e for s in spots for e in s["ev"]][:20]
    value = [{"id": s["id"], "area": s["area"], "what": s["what"], "at": ["%s:%s" % (e["path"], e["line_start"]) for e in s["ev"]]} for s in spots]
    return fact(value, "CONFIRMED" if spots else "NOT_FOUND", ev,
                None if spots else "nothing in the repository points to build, pipeline, configuration or deployment held elsewhere")


def detect(ctx) -> dict:
    areas = _areas(ctx)
    return {"files_read": files_read(ctx), "blind_spots": blind_spots(ctx, areas)}
