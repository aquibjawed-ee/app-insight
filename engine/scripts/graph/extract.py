"""Relationship extraction for one repository: discovery facts + framework adapters -> relationships.v1 (application scope).

Read-only: the repository is only read. Reuses `discover.build` (existing detectors) as the normalised-facts layer and the
existing integration detector for dependencies, hosting and modules; adapters add what those facts do not carry (endpoints,
destinations, persistence). No model, no network, no execution of repository code.
"""
from __future__ import annotations

import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(HERE, ".."))

import evidence  # noqa: E402
from detectors import Ctx  # noqa: E402
from graph import model  # noqa: E402
from graph.adapters import common, data, gateway, http, messaging, platform  # noqa: E402

EXTRACTOR_VERSION = "0.2.0"


def extract(repo: str, disc: dict = None, profile: str = None, config_dirs=()) -> dict:
    if disc is None:
        import discover
        disc = discover.build(repo)
    ctx = Ctx(repo)
    app = disc["identity"]["app_id"]["value"]
    cfg = common.Config(ctx, app, profile=profile, config_dirs=tuple(config_dirs))
    consts = common.constants(ctx)
    g = model.Graph("application")
    app_node = "app:%s" % app
    keys = platform.identity_keys(ctx, app, cfg, disc)
    ctx_path = next((v for k in ("server.servlet.context-path", "server.servlet-path", "quarkus.http.root-path", "micronaut.server.context-path")
                     for v in [cfg.get(k)[0]] if v and "${" not in v), None)
    hosts = platform.declared_hosts(ctx, app)
    g.node(app_node, "Application", app, {"identity_keys": keys, "declared_hosts": hosts, "context_path": ctx_path, "artifact_kind": disc.get("stack", {}).get("artifact_kind", {}).get("value"),
                                        "language": disc.get("stack", {}).get("language", {}).get("value")}, app=app)
    for k in keys:  # the application's own identity evidence (repository name has none)
        if k["evidence"]:
            g.nodes[app_node]["evidence"].append(k["evidence"])
    g.nodes[app_node]["evidence"] = g.nodes[app_node]["evidence"][:6]
    platform.modules(ctx, g, app, app_node, disc)
    data.dependencies(ctx, g, app, app_node, cfg)          # databases, brokers, external systems (existing integration detector)
    http.exposed(ctx, g, app, app_node, cfg, consts)
    http.router_functions(ctx, g, app, app_node)
    http.feign_clients(ctx, g, app, app_node, cfg, consts)
    exchange_hosts = http.http_exchange_clients(ctx, g, app, app_node, cfg, consts)
    gateway.routes(ctx, g, app, app_node, cfg)
    http.http_calls(ctx, g, app, app_node, cfg, consts, skip_hosts={h.lower() for h in exchange_hosts})
    messaging.source_messaging(ctx, g, app, app_node, cfg, consts)
    messaging.stream_bindings(ctx, g, app, app_node, cfg)
    data.persistence(ctx, g, app, app_node)
    data.ownership(ctx, g, app, app_node)
    platform.deployment(ctx, g, app, app_node, disc)
    doc = g.to_doc({"extractor_version": EXTRACTOR_VERSION, "application": app, "repository_fingerprint": disc["run_meta"]["inventory_fingerprint"],
                    "discovery_fingerprint": disc["run_meta"]["fingerprint"], "static_analysis_only": True, "profile": profile, "config_dirs": [str(d) for d in config_dirs], "external_sources": cfg.external,
                    "limitations": LIMITATIONS})
    errs = model.validate_integrity(doc, {app: repo}, cfg.external)
    doc["meta"]["integrity_errors"] = errs
    return doc


LIMITATIONS = [
    "Static analysis of source and configuration only; nothing was executed, so no relationship is an observed runtime fact.",
    "A dependency declaration is a DEPENDS_ON relationship with basis `declared`; it is never turned into a publisher, consumer or caller.",
    "Destinations (URLs, topics, queues, paths) are named only when they are literals, resolvable `${property}` placeholders or unique string constants; computed values stay unresolved.",
    "HTTP calls through a client built from variables, reflection, generated clients, or other languages are not found.",
    "Repository read/write edges are inferred from the repository base type; individual calls were not traced.",
    "Ktor `route(...)` prefixes and nested WebFlux `path(...)`/`nest(...)` prefixes are not combined into paths.",
    "Kubernetes workloads are read from literal manifests only; Helm templates are not rendered.",
]
