from __future__ import annotations

import re

from evidence import fact, grep_files, file_ev, read_lines


VERSION = "0.2.1"


def dockerfiles(ctx):
    """The application's Dockerfiles: not a sample's, a test module's or a dev workspace image."""
    return [f for f in ctx.files if (re.match(r"(?i)(?:docker|container)file(\.[\w.-]+)?$", f.split("/")[-1]) or f.lower().endswith(".dockerfile"))
            and not ctx._aux(f) and not ctx._test_module(f)
            and not grep_files(ctx.repo, [f], r"^\s*FROM\s+(?:gitpod/|mcr\.microsoft\.com/devcontainers|[\w./-]*devcontainer)", 1)]


def detect(ctx) -> dict:
    r = ctx.repo
    out = {}
    dep = ctx.deploy_files
    out["deploy_descriptors"] = fact(dep, "CONFIRMED" if dep else "NOT_FOUND",
                                     [file_ev(f, 1, (read_lines(r, f) or [""])[0]) for f in dep[:5]],
                                     "nomad/hcl, k8s/helm yaml, docker-compose")
    docker = dockerfiles(ctx)
    out["container_image"] = fact(docker, "CONFIRMED" if docker else "NOT_FOUND",
                                  [file_ev(f, 1, (read_lines(r, f) or [""])[0]) for f in docker[:3]])
    rep = grep_files(r, dep, r"^\s*(?:replicas|replicaCount|minReplicas|minReplicaCount):\s*([2-9]|\d{2,})|^\s*count\s*=\s*([2-9]|\d{2,})", 3)
    out["multiple_instances"] = fact(bool(rep), "CONFIRMED" if rep else "NOT_FOUND", rep,
                                     "replicas / minReplicas / count >= 2 in a deploy descriptor")
    probes = grep_files(r, dep, r"readinessProbe|livenessProbe|startupProbe|^\s*check\s*\{|health_check|healthcheck", 3)
    out["health_probes"] = fact(bool(probes), "CONFIRMED" if probes else "NOT_FOUND", probes)
    strat = grep_files(r, dep, r"RollingUpdate|maxUnavailable|maxSurge|^\s*update\s*\{|max_parallel|canary|blue.?green", 3)
    out["rolling_or_zero_downtime_strategy"] = fact(bool(strat), "CONFIRMED" if strat else "NOT_FOUND", strat)
    rb = grep_files(r, dep + ctx.ci_files, r"auto_revert\s*=\s*true|rollout\s+undo|helm\s+rollback|nomad\s+job\s+revert|automatic.?rollback", 3)
    out["rollback"] = fact(bool(rb), "CONFIRMED" if rb else "NOT_FOUND", rb)
    act = grep_files(r, ctx.build_files, r"spring-boot-starter-actuator|quarkus-smallrye-health|micronaut-management|smallrye-health", 1) + \
        grep_files(r, ctx.props, r"management\.(endpoint|endpoints)\.", 2)
    if not act:  # Dropwizard and MicroProfile register health checks in code, not in build files
        act = grep_files(r, ctx.src_main_java, r"healthChecks\(\)\.register\(|extends\s+(?:com\.codahale\.metrics\.health\.)?HealthCheck\b|@(?:Readiness|Liveness)\b", 2)
    out["health_endpoint"] = fact(bool(act), "CONFIRMED" if act else "NOT_FOUND", act)
    return out
