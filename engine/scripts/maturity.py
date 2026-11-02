"""Deterministic maturity scorecard + gap list. Pure functions of the fact sections - no free text input."""
from __future__ import annotations

from typing import Dict, List, Tuple

BLOCKING = {"automated_build", "version_tagging", "automated_deploy", "unit_tests_exist",
            "tests_run_in_ci", "coverage", "acceptance_tests"}


def _f(doc, fid):
    sec, key = fid.split(".", 1)
    return (doc.get(sec) or {}).get(key) or {"value": None, "status": "UNKNOWN", "evidence": []}


def _bool(doc, fid) -> Tuple[str, List[str]]:
    f = _f(doc, fid)
    if f["status"] == "UNKNOWN":
        return "UNKNOWN", [fid]
    if f["value"]:
        return "MET", [fid]
    return "NO_EVIDENCE", [fid]  # nothing matched; a pattern miss is not proof of absence


LIBRARY_NA = {"automated_deploy", "zero_downtime", "rollback", "openapi_exposed"}


def artifact_kind(doc: dict) -> dict:
    """library | service | unknown, from facts already gathered. Decides which criteria apply."""
    from evidence import fact
    publish = _f(doc, "build_ci.publish_step")
    http = _f(doc, "api.http_endpoints_present")
    image = _f(doc, "resilience.container_image")
    deploy = _f(doc, "resilience.deploy_descriptors")
    ev = publish["evidence"][:1] + http["evidence"][:1] + image["evidence"][:1] + deploy["evidence"][:1]
    if image["status"] == "CONFIRMED" or deploy["status"] == "CONFIRMED":
        return fact("service", "INFERRED", ev, "a container image or a deploy descriptor exists")
    if http["status"] in ("CONFIRMED", "INFERRED") and publish["status"] != "CONFIRMED":
        return fact("service", "INFERRED", ev, "HTTP controllers or an HTTP server framework exist, and nothing publishes an artefact")
    if publish["status"] == "CONFIRMED":
        return fact("library", "INFERRED", ev, "publishes an artefact and has no container image or deploy descriptor; "
                    "HTTP classes alone do not make a service (frameworks ship them). Deploy/HA/rollback/OpenAPI criteria are marked not applicable")
    return fact("unknown", "UNKNOWN", [], "neither a publish step nor service signals were found")


def _coverage(doc):
    state = _f(doc, "tests.coverage_state")["value"]
    enforced = _f(doc, "tests.coverage_enforced")["value"]
    thr = _f(doc, "tests.coverage_threshold_pct")["value"]
    meas = _f(doc, "tests.coverage_measured")["value"] or {}
    if (_f(doc, "tests.coverage_run")["value"] or {}).get("representative") is False:
        meas = {}  # the report came from a partial run: it says nothing about the application
    pct = meas.get("BRANCH", meas.get("LINE"))
    facts = ["tests.coverage_state", "tests.coverage_enforced", "tests.coverage_threshold_pct", "tests.coverage_measured",
             "tests.coverage_gate_in_ci"]
    gate = _f(doc, "tests.coverage_gate_in_ci")["value"]
    if state == "tests_disabled_in_pipeline":
        return "NOT_MET", facts  # positive evidence: tests are switched off
    if state in ("no_tests", "tests_present_coverage_not_configured"):
        return "NO_EVIDENCE", facts
    wired = gate in ("invoked_in_ci", "wired_into_build", "maven_lifecycle")
    scope = _f(doc, "tests.coverage_scope")["value"] or {}
    if enforced and ((thr or 0) >= 75 or (pct is not None and pct >= 75)):
        if wired and scope.get("partial"):
            return "PARTIAL", facts + ["tests.coverage_scope"]  # enforced in a few modules of many, not for the repository
        if wired:
            return "MET", facts
        # a gate that is configured but not shown to run is not an enforced gate; remote templates may hide it
        return ("UNKNOWN" if gate == "unknown_remote_includes" else "PARTIAL"), facts
    return "PARTIAL", facts


def _tests_in_ci(doc):
    v = _f(doc, "tests.ci_test_execution")["value"]
    if v == "enabled" and _f(doc, "tests.ci_test_execution")["status"] == "INFERRED":
        return "PARTIAL", ["tests.ci_test_execution"]  # found only inside a script CI calls
    res = {"enabled": "MET", "partially_disabled": "PARTIAL", "unknown_remote_includes": "UNKNOWN",
           "disabled_in_pipeline": "NOT_MET", "disabled_in_build": "NOT_MET"}.get(v, "NO_EVIDENCE")
    return res, ["tests.ci_test_execution"]


def _zdt(doc):
    ids = ["resilience.multiple_instances", "resilience.health_probes", "resilience.rolling_or_zero_downtime_strategy"]
    n = sum(1 for i in ids if _f(doc, i)["value"])
    return ("MET" if n == 3 else "PARTIAL" if n else "NO_EVIDENCE"), ids


def _api(doc):
    v = _f(doc, "api.openapi_exposure")["value"]
    if v == "exposed_via_library":
        return "MET", ["api.openapi_exposure"]  # a generator is configured and not disabled: a spec is produced
    if v == "static_spec_only":
        return "PARTIAL", ["api.openapi_exposure"]  # a spec file exists; whether it is served or current is not knowable offline
    return ("NOT_MET" if v in ("disabled", "library_present_but_disabled") else "NO_EVIDENCE"), ["api.openapi_exposure"]


def _present(fid):
    def fn(doc):
        f = _f(doc, fid)
        return ("MET" if f["status"] == "CONFIRMED" else "NO_EVIDENCE"), [fid]
    return fn


def _present_ext(fid):
    """In-repo evidence is MET; a suite only triggered from CI (kept in another project) is PARTIAL."""
    def fn(doc):
        f = _f(doc, fid)
        if f["status"] == "CONFIRMED":
            # the suite exists; MET also needs something that runs it (not a disabled module, not a plan nobody calls)
            return ("PARTIAL" if (f["value"] or {}).get("not_run_reason") else "MET"), [fid]
        return ("PARTIAL" if f["status"] == "INFERRED" and (f["value"] or {}).get("external") else "NO_EVIDENCE"), [fid]
    return fn


def _tagging(doc):
    """MET: the pipeline creates version tags. PARTIAL: releases are driven by tags (triggered by, or versioned from, a tag), or
    each build is tagged with its commit, but nothing shows the pipeline creating release tags."""
    base = _ci("build_ci.version_tagging")(doc)
    if base[0] in ("MET", "UNKNOWN"):
        return base
    ids = ["build_ci.release_triggered_by_tag", "build_ci.version_from_git_tag", "build_ci.artifact_tag_from_commit", "build_ci.release_plugin_tags"]
    hit = [i for i in ids if _f(doc, i)["value"]]
    if hit:
        return "PARTIAL", ["build_ci.version_tagging"] + hit
    return base


def _scan(cat):
    """Scanner criteria: MET only when a CI file invokes the tool; PARTIAL when it is configured but no pipeline runs it."""
    def fn(doc):
        base = _bool(doc, "security." + cat)
        if base[0] != "MET":
            return base
        run = _f(doc, "security." + cat + "_in_pipeline")
        if run["value"] and cat == "sast" and _f(doc, "security.sast_root_only")["value"]:
            return "PARTIAL", ["security.sast_root_only", "security.sast", "security.sast_in_pipeline"]  # modules left out
        if run["value"] and cat == "sast" and _f(doc, "security.sast_rules_filtered")["value"]:
            return "PARTIAL", ["security.sast_rules_filtered", "security.sast", "security.sast_in_pipeline"]  # wired, but its security rules filtered out
        if run["value"]:
            return "MET", ["security." + cat, "security." + cat + "_in_pipeline"]
        return "PARTIAL", ["security." + cat, "security." + cat + "_in_pipeline"]
    return fn


def _ci(fid):
    """CI-derived boolean: MET only when a CI file itself shows it (CONFIRMED); a hit found only inside a script that CI
    calls is INFERRED and scores PARTIAL."""
    def fn(doc):
        res = _bool(doc, fid)
        if res[0] == "MET" and _f(doc, fid)["status"] == "INFERRED":
            return "PARTIAL", res[1]
        return res
    return fn


def _b(fid):
    return lambda doc: _bool(doc, fid)


CRITERIA = [
    ("automated_build", "Automated build in CI", "build_ci.build_step is true", _ci("build_ci.build_step")),
    ("version_tagging", "Automated version tagging", "build_ci.version_tagging is true (partial: releases are tag-driven but tag creation is not shown)", _tagging),
    ("automated_deploy", "Automated deploy", "build_ci.deploy_step is true", _ci("build_ci.deploy_step")),
    ("unit_tests_exist", "Unit tests exist", "tests.unit_tests found (>=1 class with @Test)", _present("tests.unit_tests")),
    ("integration_tests", "Integration tests", "tests.integration_tests found (>=1 integration-style class)", _present("tests.integration_tests")),
    ("tests_run_in_ci", "Tests run in the pipeline", "ci_test_execution == enabled (partial if some commands skip tests)", _tests_in_ci),
    ("coverage", "Coverage minimum (>= 75%) configured and run in the pipeline",
     "MET: a coverage gate with minimum >= 75 that the pipeline runs or wires in (tests.coverage_gate_in_ci); PARTIAL: gate configured but not shown to run, or tool present without a qualifying gate; UNKNOWN: pipeline hidden in remote templates; NOT_MET: tests disabled; NO_EVIDENCE: no tests or no coverage tool", _coverage),
    ("acceptance_tests", "Acceptance tests", "feature files or acceptance libraries found", _present_ext("tests.acceptance_tests")),
    ("performance_tests", "Performance tests", "gatling/jmeter/k6/locust artefacts or deps found", _present_ext("tests.performance_tests")),
    ("contract_tests", "Contract tests", "pact/spring-cloud-contract deps or contract files found", _present_ext("tests.contract_tests")),
    ("openapi_exposed", "API specification (OpenAPI) provided", "api.openapi_exposure: exposed_via_library = MET (generator configured), static_spec_only = PARTIAL (file only; serving not verifiable offline); only scored if HTTP endpoints exist", _api),
    ("zero_downtime", "Zero-downtime / HA configuration", "replicas>=2, health probes and rolling strategy all present (partial if some)", _zdt),
    ("rollback", "Automatic rollback", "resilience.rollback true", _b("resilience.rollback")),
    ("secret_scanning", "Secret scanning", "security.secret_scanning true and a CI file invokes it (partial if only configured)", _scan("secret_scanning")),
    ("dependency_scanning", "Dependency scanning", "security.dependency_scanning true and a CI file invokes it (partial if only configured)", _scan("dependency_scanning")),
    ("sast", "Code scanning (SAST)", "security.sast true and a CI file invokes it (partial if only configured)", _scan("sast")),
    ("dependency_updates", "Automated dependency updates", "security.dependency_updates true", _b("security.dependency_updates")),
]


# criteria that only a pipeline can show: with the pipeline outside the repository, finding nothing is unknown, not absent
PIPELINE_ONLY = {"automated_build", "tests_run_in_ci", "version_tagging", "automated_deploy", "rollback", "secret_scanning", "dependency_scanning", "sast"}


def score(doc: dict) -> dict:
    has_http = _f(doc, "api.http_endpoints_present")["status"] in ("CONFIRMED", "INFERRED")
    out = []
    for cid, label, rule, fn in CRITERIA:
        if cid == "openapi_exposed" and not has_http:
            continue
        if cid in LIBRARY_NA and _f(doc, "stack.artifact_kind")["value"] == "library":
            continue
        result, facts = fn(doc)
        hand = cid in ("automated_deploy", "rollback") and _f(doc, "build_ci.manual_deploy_documented")["value"]  # a runbook shows it is manual
        if result == "NO_EVIDENCE" and hand:
            facts = ["build_ci.manual_deploy_documented"] + facts
        if result == "NO_EVIDENCE" and cid in PIPELINE_ONLY and not hand and (_f(doc, "build_ci.ci_system")["value"] or []) == ["external"]:
            result, facts = "UNKNOWN", ["build_ci.ci_system"] + facts
        out.append({"id": cid, "label": label, "result": result, "rule": rule, "facts": facts})
    scored = [c for c in out if c["result"] != "UNKNOWN"]
    pts = sum(1.0 if c["result"] == "MET" else 0.5 if c["result"] == "PARTIAL" else 0.0 for c in scored)
    # NO_EVIDENCE scores 0 (conservative) but is reported separately so a score is never read as proven absence
    pct = round(100.0 * pts / len(scored), 1) if scored else 0.0
    band = "Low" if pct < 40 else "Medium" if pct < 70 else "High"
    determined = len(scored)  # every applicable check whose answer the offline scan could establish (found or searched-and-absent)
    return {"criteria": out, "score": pct, "band": band,
            "completeness": {"applicable": len(out), "determined": determined, "unknown": len(out) - determined,
                             "no_evidence": sum(1 for c in out if c["result"] == "NO_EVIDENCE"),
                             "with_evidence": sum(1 for c in out if c["result"] in ("MET", "PARTIAL", "NOT_MET")),
                             "pct_determined": round(100.0 * determined / len(out), 1) if out else 0.0},
            "no_evidence": sum(1 for c in out if c["result"] == "NO_EVIDENCE"),
            "unknown": sum(1 for c in out if c["result"] == "UNKNOWN")}


def gaps(maturity: dict) -> List[dict]:
    out = []
    for c in maturity["criteria"]:
        if c["result"] == "MET":
            continue
        verb = {"NOT_MET": "Not met", "NO_EVIDENCE": "No evidence of", "PARTIAL": "Incomplete",
                "UNKNOWN": "Could not determine"}[c["result"]]
        out.append({"id": "gap-" + c["id"], "title": "%s: %s" % (verb, c["label"]),
                    "severity": "BLOCKING" if c["id"] in BLOCKING and c["result"] != "UNKNOWN" else "NON_BLOCKING",
                    "criterion": c["id"], "facts": c["facts"]})
    return out


def ambiguities(doc: dict) -> List[dict]:
    amb = []
    if _f(doc, "stack.build_tool")["value"] == "maven+gradle":
        amb.append({"id": "amb-build-tool", "facts": ["stack.build_tool"],
                    "question": "Both Maven and Gradle files exist. Which is the authoritative build for CI?"})
    if len(_f(doc, "build_ci.ci_system")["value"] or []) > 1:
        amb.append({"id": "amb-ci-system", "facts": ["build_ci.ci_system"],
                    "question": "More than one CI system is defined. Which one is live?"})
    if (_f(doc, "build_ci.unresolved_includes")["value"] or 0) > 0:
        amb.append({"id": "amb-remote-includes", "facts": ["build_ci.unresolved_includes"],
                    "question": "Remote CI templates are included but not visible offline. Provide their content to resolve UNKNOWN facts."})
    return amb
