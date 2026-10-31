#!/usr/bin/env python3
"""app-discovery CLI: scan a repo and write an evidence-backed discovery.json. No model, no network.

Exit codes: 0 ok | 1 produced, but a detector failed or evidence did not re-verify | 2 could not run.
"""
from __future__ import annotations

import argparse
import datetime
import importlib
import json
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)

import evidence  # noqa: E402
import maturity  # noqa: E402
import validate  # noqa: E402
from detectors import Ctx  # noqa: E402

TOOL_VERSION = "0.3.0"
LIMITATIONS = [
    "Static scan only: no build, test, CI or runtime was executed or queried.",
    "NO_EVIDENCE means no pattern matched in the scanned files; it is not proof of absence.",
    "Remote CI includes (project/remote/template) are not fetched; facts that may live there are UNKNOWN.",
    "Declared versions are not resolved versions (no BOM resolution; version catalogs, `${property}` and Gradle variables are read only for the Java, Kotlin and Spring Boot versions, and only when one literal defines them).",
    "When several Java versions are declared, the lowest is reported as the compatibility baseline and the status is INFERRED; the alternatives are listed in the note.",
    "A coverage report found on disk may predate the current code; staleness is flagged by file time versus the HEAD commit.",
    "Test detection is by annotation and naming convention; test quality is not assessed.",
    "A coverage gate is reported as run by the pipeline only when the pipeline names it or the build wires it to a task the pipeline runs; no gate execution or pass/fail result was observed.",
    "A coverage report is only quoted when the test run behind it covers at least half of the test classes found; the percentage is never a verified result.",
    "Only the build system at the repository root counts as the build; build files under docs, samples, examples, benchmarks, test source sets and test-only modules are set aside (their number is in the build_tool note).",
    "Ant, Bazel and Make builds are not analysed; an Ant repository is reported as `ant` and its test, coverage and CI facts reflect Maven/Gradle layouts only.",
    "CI is read from GitLab CI, GitHub Actions, CircleCI, Jenkinsfiles and Azure/Bitbucket files. Repository scripts that CI calls are searched one level deep and anything found there is INFERRED (which command CI reaches was not traced). TeamCity and server-side Jenkins job definitions are not read.",
    "allow_failure / continue-on-error on scan jobs is not considered: a non-blocking scan still counts as run.",
    "Coverage services (Codecov, Coveralls, Sonar quality gates) are not read; thresholds declared only as pom properties are reported as intent, not enforcement.",
    "Test classes are recognised by @Test-style annotations, Kotest specs, JUnit 3 TestCase and Spock Specification; suites run through other harnesses (AntUnit, shell scripts, docker-compose) are not counted.",
    "Suites that the pipeline triggers from another project are INFERRED from the CI job; their content and results are not visible.",
    "Facts are repository-wide. File citations carry the module they came from; per-module assessment is not performed.",
    "Dependencies and hosting are read from files (deployment descriptors and pipeline commands name the platform; nothing is queried): hosts are not resolved, a service reached only at run time, through a client built in code or through a URL held in a property is not named, and a declared dependency with no connection setting is reported as declared only.",
    "Evidence snippets are redacted for secret-looking literals; review before sharing outside the organisation.",
]
ORDER = ["identity", "stack", "build_ci", "tests", "api", "resilience", "security"]


def build(repo: str) -> dict:
    ctx = Ctx(repo)
    doc = {"contract": "discovery.v1"}
    failures = []
    for name in ORDER:
        try:
            doc[name] = importlib.import_module("detectors." + name).detect(ctx)
        except Exception as e:  # a broken detector must not erase the others
            doc[name] = {}
            failures.append("%s: %s: %s" % (name, type(e).__name__, e))
    if len(ctx.module_dirs()) > 1:  # keep attribution: every file citation says which module it came from
        for _, f in evidence.iter_facts(doc):
            for e in f["evidence"]:
                if e.get("kind") == "file":
                    e["module"] = ctx.module_of(e["path"])
    doc["stack"]["artifact_kind"] = maturity.artifact_kind(doc)
    doc["maturity"] = maturity.score(doc)
    doc["gaps_and_risks"] = maturity.gaps(doc["maturity"])
    doc["llm_fill"] = {"ambiguities": maturity.ambiguities(doc), "narrative": None, "resolutions": []}
    checked, invalid = 0, []
    for fid, f in evidence.iter_facts(doc):
        for e in f["evidence"]:
            checked += 1
            bad = evidence.verify(repo, e)
            if bad:
                invalid.append("%s: %s" % (fid, bad))
    versions = [{"id": n, "version": getattr(importlib.import_module("detectors." + n), "VERSION", "0")} for n in ORDER]
    stamp = os.environ.get("DISCOVERY_FIXED_TIME") or \
        datetime.datetime.now(datetime.timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    doc["run_meta"] = {"tool_version": TOOL_VERSION, "generated_at": stamp,
                       "fingerprint": validate.fingerprint(doc),
                       "inventory_fingerprint": evidence.inventory_fingerprint(repo, ctx.files),
                       "detectors": versions,
                       "completeness": {"static_scan": "completed", "build_execution": "not_run", "tests_executed": "not_run",
                                        "ci_integration": "not_run", "runtime_integration": "not_run"},
                       "limitations": LIMITATIONS,
                       "failures": failures, "evidence_checked": checked, "evidence_invalid": sorted(invalid)}
    return doc


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--repo", required=True)
    ap.add_argument("--out", help="output directory (default: <repo>/.modernise/discovery)")
    a = ap.parse_args(argv)
    repo = os.path.abspath(a.repo)
    if not os.path.isdir(repo):
        print("repo not found: %s" % repo, file=sys.stderr)
        return 2
    doc = build(repo)
    errs = validate.validate(doc)
    if errs:
        print("discovery.json failed schema validation:\n  " + "\n  ".join(errs[:10]), file=sys.stderr)
        return 2
    out_dir = a.out or os.path.join(repo, ".modernise", "discovery")
    os.makedirs(out_dir, exist_ok=True)
    path = os.path.join(out_dir, "discovery.json")
    tmp = path + ".tmp"  # write-then-rename so a crash never leaves a half-written discovery.json
    with open(tmp, "w", encoding="utf-8") as fh:
        json.dump(doc, fh, indent=2, sort_keys=True)
        fh.write("\n")
    os.replace(tmp, path)
    m = doc["maturity"]
    print("━━ APP-DISCOVERY-SUMMARY ━━")
    print("app_id:        %s" % doc["identity"]["app_id"]["value"])
    print("output:        %s" % path)
    print("maturity:      %s (%s%%) - %d criteria with no evidence, %d unknown" % (m["band"], m["score"], m["no_evidence"], m["unknown"]))
    print("coverage:      %s" % doc["tests"]["coverage_state"]["value"])
    print("tests in CI:   %s" % doc["tests"]["ci_test_execution"]["value"])
    print("gaps:          %d (%d blocking)" % (len(doc["gaps_and_risks"]),
          sum(1 for g in doc["gaps_and_risks"] if g["severity"] == "BLOCKING")))
    print("evidence:      %d citations checked, %d invalid" % (doc["run_meta"]["evidence_checked"],
                                                             len(doc["run_meta"]["evidence_invalid"])))
    for f in doc["run_meta"]["failures"]:
        print("DETECTOR FAILED: " + f)
    return 1 if (doc["run_meta"]["failures"] or doc["run_meta"]["evidence_invalid"]) else 0


if __name__ == "__main__":
    sys.exit(main())
