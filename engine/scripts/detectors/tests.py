from __future__ import annotations

import os
import re

import coverage_tools
from evidence import fact, grep_files, read_lines, walk, file_ev, find_lines, run

CI_TEST_CMD = r"(?:^|[\s:&;|_\"'=-])(?:\./)?(?:mvnw?|gradlew?)\s+[^\n]*\b(test|verify|install|package|build|check)\b"
SKIP_FLAG = r"-DskipTests|-Dmaven\.test\.skip(=true)?|-Dskip\.?[Uu]nit|-x\s+test\b|-x\s+check\b|--exclude-task\s+test"
BUILD_SKIP = (r"<skipTests>\s*true|<maven\.test\.skip>\s*true|<skip>\s*true\s*</skip>.*surefire"
              r"|\btest\s*\{[^}]*enabled\s*=\s*false|(?<![\w])test\.enabled\s*=\s*false|tasks\.test\.enabled\s*=\s*false")


# markers found inside an integration-style test class -> the name shown to the reader
IT_TOOLS = (("spring-boot-test", r"@SpringBootTest"), ("spring-mvc-test", r"@WebMvcTest|@AutoConfigureMockMvc"),
            ("data-jpa-test", r"@DataJpaTest"), ("testcontainers", r"@Testcontainers|\bGenericContainer\b|org\.testcontainers"),
            ("embedded-kafka", r"@EmbeddedKafka"), ("wiremock", r"WireMock"), ("rest-assured", r"io\.restassured|RestAssured"),
            ("localstack", r"(?i)localstack"))


# a test class: a JUnit/TestNG-style annotation, or a Kotest spec (class extends one of its spec styles)
TEST_MARK = re.compile(r"@(?:[\w]+\.)*(?:Test|ParameterizedTest|RepeatedTest|TestFactory|QuarkusTest|QuarkusIntegrationTest|"
                       r"SpringBootTest|MicronautTest|DataJpaTest|WebMvcTest|WebFluxTest)\b"
                       r"|:\s*(?:StringSpec|FunSpec|WordSpec|BehaviorSpec|DescribeSpec|ShouldSpec|FreeSpec|FeatureSpec|ExpectSpec|AnnotationSpec)\b"
                       r"|\bextends\s+(?:[\w.]+\.)?(?:TestCase|Specification)\b")  # JUnit 3 and Spock
# e2e/acceptance/journey directories hold acceptance-style tests anywhere; `functional` only as a module directory
# (before src/): a package named functional inside src/test is usually in-process tests (e.g. gson's)
ACCEPT_DIR = re.compile(r"(^|/)(e2e|acceptance|journeys?)(/|$)", re.I)
SOURCE_SET = re.compile(r"(?:^|/)src/(integrationTest|integration-test|intTest|it|functionalTest|acceptanceTest|e2eTest|contractTest)/")
FUNCTIONAL_MODULE = re.compile(r"^(?:.*/)?functional/(?:src/)", re.I)
CONTRACT_DIR = re.compile(r"(^|/)contracts?(/|$)", re.I)
# the class name states the intent: FooAcceptanceTest, CheckoutE2ETest, SignupJourneyTest
ACCEPT_NAME = re.compile(r"(?:Acceptance|E2E|EndToEnd|Journey)(?:Test|Tests|IT|Spec)\.\w+$")
# boots the whole application: the test talks to the running app, not to one class
FULL_APP = re.compile(r"\bDropwizardAppRule\b|\bDropwizardAppExtension\b|@SpringBootTest\s*\([^)]*webEnvironment\s*=\s*[\w.]*(?:RANDOM_PORT|DEFINED_PORT)|@QuarkusTest\b|@MicronautTest\b")
# a class whose only test checks that the application context starts: it proves wiring, not behaviour
CONTEXT_ONLY = re.compile(r"(?:@Test\s*(?:fun|void|public\s+void)\s+`?contextLoads`?\s*\(\s*\)\s*(?::\s*Unit\s*)?\{\s*\}\s*)")


def _classify(repo, test_sources, module_of=lambda p: "."):
    unit = integ = 0
    unit_mods = {}
    it_tools, it_separate = set(), False
    unit_ev, integ_ev = [], []
    acc_ev, con_ev = [], []
    for f in test_sources:
        ls = read_lines(repo, f) or []
        text = "\n".join(ls)
        if not TEST_MARK.search(text):
            continue
        idx0 = next((i for i, ln in enumerate(ls, 1) if TEST_MARK.search(ln)), 1)
        sset = SOURCE_SET.search(f)
        if sset and sset.group(1) in ("acceptanceTest", "e2eTest"):
            acc_ev.append(file_ev(f, idx0, ls[idx0 - 1]))
            continue
        if sset and sset.group(1) == "contractTest":
            con_ev.append(file_ev(f, idx0, ls[idx0 - 1]))
            continue
        if ACCEPT_DIR.search(f) or FUNCTIONAL_MODULE.search(f):  # a module or package named functional/e2e/acceptance holds acceptance-style tests
            acc_ev.append(file_ev(f, idx0, ls[idx0 - 1]))
            continue
        if CONTRACT_DIR.search(f):
            con_ev.append(file_ev(f, idx0, ls[idx0 - 1]))
            continue
        if ACCEPT_NAME.search(f):
            acc_ev.append(file_ev(f, idx0, ls[idx0 - 1]))
            continue
        if len(re.findall(r"@Test\b", text)) == 1 and CONTEXT_ONLY.search(text):
            continue  # neither a unit nor an integration test: it only starts the context
        is_it = re.search(r"(IT|IntegrationTest|ITCase)\.\w+$", f) or "/integration" in f \
            or re.search(r"(^|/)(?:its?|[\w.-]*integration[-_]?tests?|[\w.-]*-it)(/|$)", f.split("/src/")[0] + "/") or (sset and sset.group(1) in ("integrationTest", "integration-test", "intTest", "it", "functionalTest")) \
            or re.search(r"@(SpringBootTest|Testcontainers|DataJpaTest|WebMvcTest)", text) or FULL_APP.search(text)
        idx = next((i for i, ln in enumerate(ls, 1) if TEST_MARK.search(ln)), 1)
        if is_it:
            integ += 1
            it_tools.update(n for n, rx in IT_TOOLS if re.search(rx, text))
            it_separate = it_separate or bool(sset and sset.group(1) in ("integrationTest", "integration-test", "intTest", "it", "functionalTest"))
            integ_ev.append(file_ev(f, idx, ls[idx - 1]))
        else:
            unit += 1
            unit_mods[module_of(f)] = unit_mods.get(module_of(f), 0) + 1
            unit_ev.append(file_ev(f, idx, ls[idx - 1]))
    return unit, unit_ev, integ, integ_ev, sorted(it_tools), it_separate, acc_ev, con_ev, unit_mods


def _in_optin_profile(repo, path, line):
    """True when a pom line sits inside a <profile> that is not active by default: such a setting only applies when
    someone selects the profile (e.g. -P benchmark), so it says nothing about the normal build."""
    if not path.endswith("pom.xml"):
        return False
    ls = read_lines(repo, path) or []
    start = None
    for i in range(min(line, len(ls)) - 1, -1, -1):
        if "</profile>" in ls[i]:
            return False
        if "<profile>" in ls[i]:
            start = i
            break
    if start is None:
        return False
    end = next((j for j in range(line, len(ls)) if "</profile>" in ls[j]), len(ls))
    return not re.search(r"<activeByDefault>\s*true", "\n".join(ls[start:end]))


def _libs(hits, rx):
    """Library names (not raw build-file lines) for the lines that matched."""
    return sorted({m.group(0).lower().replace("restassured", "rest-assured") for e in hits for m in [re.search(rx, e["snippet"], re.I)] if m})


def _kind(value: dict, ev: list, external: list, libs_ev: list = ()):
    """libs_ev: evidence that a test library is declared. It supports a finding only next to real artefacts (feature
    files, test classes, plans); a library with nothing to run is reported as not found."""
    if libs_ev and not ev and not external:
        return fact(dict(value, external=[]), "NOT_FOUND", [], "a test library is declared but no test artefact of this kind was found")
    ev = list(ev) + (list(libs_ev) if ev else [])
    return _kind_inner(value, ev, external)


def _kind_inner(value: dict, ev: list, external: list):
    """In-repo evidence wins (CONFIRMED). Otherwise a CI job that triggers/runs the suite from elsewhere is INFERRED:
    the job is proof the pipeline invokes it, not proof of what the suite contains or whether it passes."""
    if ev:
        return fact(dict(value, external=[{k: x[k] for k in ("job", "target_project")} for x in external]), "CONFIRMED", ev)
    if external:
        return fact(dict(value, external=[{k: x[k] for k in ("job", "target_project")} for x in external]), "INFERRED",
                    [x["ev"] for x in external][:3], "the pipeline runs this suite from another project; its content is not visible here")
    return fact(dict(value, external=[]), "NOT_FOUND", [])


from detectors import Ctx as _Ctx
Ctx_AUX = _Ctx.AUX_DIR

VERSION = "0.7.0"


def _it_note(ctx):
    run = [e for e in grep_files(ctx.repo, ctx.ci_files, r"\b(?:integrationTest|intTest|integration-test)\b", 5)
           if not re.search(r"-x\s+(?:integrationTest|intTest)\b", e["snippet"])][:1]  # `build -x integrationTest` skips them
    if run:
        return "the classes live in their own source set, which the pipeline runs (%s:%s)" % (run[0]["path"], run[0]["line_start"])
    return "the classes live in their own source set, so the ordinary test task may not run them"


def detect(ctx) -> dict:
    r = ctx.repo
    out = {}
    unit, unit_ev, integ, integ_ev, it_tools, it_separate, acc_cls, con_cls, unit_mods = _classify(r, ctx.test_sources, ctx.module_of)
    out["unit_tests"] = fact({"test_classes": unit, "test_files": len(ctx.test_sources), "by_module": dict(sorted(unit_mods.items()))},
                             "CONFIRMED" if unit else "NOT_FOUND", unit_ev[:5])
    out["integration_tests"] = fact({"test_classes": integ, "tools": it_tools, "separate_source_set": it_separate},
                                    "CONFIRMED" if integ else "NOT_FOUND", integ_ev[:5],
                                    _it_note(ctx) if it_separate else None)
    fw = []
    fev = []
    for name, rx in (("junit5", r"junit-jupiter|org\.junit\.jupiter|useJUnitPlatform"), ("junit4", r"<artifactId>junit</artifactId>|junit:junit"),
                     ("testng", r"testng"), ("mockito", r"mockito"), ("mockk", r"mockk"), ("embedded-kafka", r"spring-kafka-test|EmbeddedKafka"), ("assertj", r"assertj"),
                     ("testcontainers", r"testcontainers"), ("quarkus-test", r"quarkus-junit5?"), ("rest-assured", r"rest-assured"), ("awaitility", r"awaitility")):
        h = [e for e in grep_files(r, ctx.build_files, rx, 10) if not re.search(r"\bexclude\b", e["snippet"])][:1]
        if h:
            fw.append(name)
            fev.extend(h)
    out["frameworks"] = fact(sorted(fw), "CONFIRMED" if fw else "NOT_FOUND", fev)
    skip_mods = {ctx.module_of(e["path"]) for e in grep_files(r, [f for f in ctx.build_files if not ctx._test_module(f)], BUILD_SKIP, 20)
                 if not _in_optin_profile(r, e["path"], e["line_start"])}

    def disabled(evs):
        """True when every module that holds these test classes switches its tests off: they exist but never run."""
        mods = {ctx.module_of(e["path"]) for e in evs}
        return bool(mods) and mods <= skip_mods and "." not in mods
    # Suites triggered from CI but kept in another project (or run by a job named for the suite)
    ext = {"acceptance": [], "performance": [], "contract": []}
    kinds = (("acceptance", r"acceptance|e2e|end-to-end|functional|smoke"), ("performance", r"performance|perf|load|stress|gatling|jmeter|k6"),
             ("contract", r"pact|contract"))
    for j in ctx.ci_jobs():
        if not (j["trigger_project"] or j["has_script"]):
            continue
        # only the job's own name and target project decide; a stage name alone says nothing (a deploy job can sit in `e2e`)
        text = j["name"] + " " + (j["trigger_project"] or "")
        kind = next((k for k, rx in kinds if re.search(rx, text, re.I)), None)
        if kind:
            ext[kind].append({"job": j["name"], "target_project": j["trigger_project"], "ev": file_ev(j["file"], j["line"], j["text"])})
    # An external coverage service (Codecov, Coveralls) with a declared target: a status check this scan cannot see run
    svc_files = [f for f in ctx.files if re.search(r"(^|/)\.?codecov\.ya?ml$|(^|/)\.coveralls\.yml$", f)]
    tgt = grep_files(r, svc_files, r"target:\s*['\"]?(\d+(?:\.\d+)?)\s*%?", 3)
    svc_ci = grep_files(r, ctx.ci_files, r"codecov|coveralls", 2)
    out["coverage_service"] = fact({"service": "codecov" if any("codecov" in f for f in svc_files) or svc_ci else "coveralls",
                                    "target_pct": float(re.search(r"(\d+(?:\.\d+)?)", tgt[0]["snippet"].split(":", 1)[1]).group(1)) if tgt else None,
                                    "uploaded_by_ci": bool(svc_ci)},
                                   "INFERRED" if (svc_files or svc_ci) else "NOT_FOUND",
                                   (tgt or [file_ev(f, 1, (read_lines(r, f) or [""])[0]) for f in svc_files[:1]]) + svc_ci,
                                   "an external service applies this target as a status check; whether it blocks a merge is not visible here" if (svc_files or svc_ci) else None)
    # Other test kinds
    feat = [f for f in ctx.files if f.endswith(".feature")]
    cuc = grep_files(r, ctx.build_files, r"cucumber|karate|serenity|rest-assured|restassured|selenium|playwright", 2)
    post = [f for f in ctx.files if f.endswith(".postman_collection.json") and not Ctx_AUX.search(os.path.dirname("/" + f) + "/")]
    # Browser suites: a Cypress/Playwright config or spec, or test code that imports Selenium/Playwright. A dependency alone is a library.
    bro_files = [f for f in ctx.files if re.search(r"(^|/)(?:cypress|playwright)\.config\.(?:js|ts|mjs|cjs)$|\.cy\.(?:js|ts|jsx|tsx)$|(^|/)cypress/(?:e2e|integration)/", f)
                 and not Ctx_AUX.search(os.path.dirname("/" + f) + "/")]
    bro_code = grep_files(r, ctx.test_sources, r"import\s+(?:org\.openqa\.selenium|com\.microsoft\.playwright)|from\s+['\"](?:selenium|playwright)", 3)
    bro_ev = [file_ev(f, 1, (read_lines(r, f) or [""])[0]) for f in bro_files[:3]] + bro_code
    bro_tools = sorted({("cypress" if "cypress" in f.lower() or ".cy." in f else "playwright" if "playwright" in f.lower() else "selenium") for f in bro_files}
                       | {("playwright" if "playwright" in e["snippet"] else "selenium") for e in bro_code})
    pkgs = grep_files(r, [f for f in ctx.files if os.path.basename(f) == "package.json" and not Ctx_AUX.search(os.path.dirname("/" + f) + "/")],
                      r"[\"'](?:cypress|@playwright/test|playwright|selenium-webdriver|webdriverio)[\"']\s*:", 2)
    cuc = cuc + pkgs
    ev = [file_ev(f, 1, (read_lines(r, f) or [""])[0]) for f in feat[:3]] + acc_cls[:3] \
        + [file_ev(f, 1, (read_lines(r, f) or [""])[0]) for f in post[:2]] + bro_ev
    styles = [k for k, on in (("gherkin", feat), ("test_classes", acc_cls), ("postman", post), ("browser", bro_files or bro_code),
                              ("external", ext["acceptance"])) if on]
    acc_val = {"feature_files": len(feat), "test_classes": len(acc_cls), "postman_collections": len(post),
               "styles": styles, "browser_tools": bro_tools,
               "libraries": _libs(cuc, r"cucumber|karate|serenity|rest-?assured|selenium|playwright|cypress|webdriverio")}
    if acc_cls and not feat and disabled(acc_cls):
        acc_val["not_run_reason"] = "the module holding these tests switches its tests off"
    out["acceptance_tests"] = _kind(acc_val, ev, ext["acceptance"], cuc)
    # contract files, not the tooling next to them (package.json, a compose file that starts a mock)
    cdirs = [f for f in ctx.files if re.search(r"(^|/)(pacts?|contracts?)/.+\.(json|ya?ml|groovy|kts?|apib|md)$", f)
             and not re.search(r"(^|/)(package(-lock)?\.json|(docker-)?compose[^/]*\.ya?ml|README\.md|[^/]*\.config\.\w+)$|/node_modules/", f)]
    cl = grep_files(r, ctx.build_files, r"pact|spring-cloud-contract|spring-cloud-starter-contract|\bdredd\b", 2)
    # the pipeline step that runs them proves more than the first line of a contract file
    # the command that runs them first; a stage named after them only if no command is found
    con_run = grep_files(r, ctx.ci_files, r"runContract\w*|pact(?:Verify|Publish)|\bcontractTest\b|\bdredd\b", 2) or \
        grep_files(r, ctx.ci_files, r"(?i)contract[-_ ]?tests?", 1)
    ev = con_run + [file_ev(f, 1, (read_lines(r, f) or [""])[0]) for f in cdirs[:3]] + con_cls[:3]
    con_val = {"contract_files": len(cdirs), "test_classes": len(con_cls), "libraries": _libs(cl, r"spring-cloud-(?:starter-)?contract|pact"),
               "tools": sorted(({"pact"} if re.search(r"pact", " ".join(e["snippet"] for e in cl), re.I) or any("pact" in f for f in cdirs) else set())
                               | ({"dredd"} if re.search(r"\bdredd\b", " ".join(e["snippet"] for e in cl + con_run), re.I) else set())
                               | ({"spring-cloud-contract"} if re.search(r"spring-cloud-(?:starter-)?contract", " ".join(e["snippet"] for e in cl)) else set()))}
    if con_cls and not cdirs and disabled(con_cls):
        con_val["not_run_reason"] = "the module holding these tests switches its tests off"
    out["contract_tests"] = _kind(con_val, ev, ext["contract"], cl)
    jm = [f for f in ctx.files if f.endswith(".jmx")]
    gat = [f for f in ctx.files if re.search(r"(^|/)(gatling|simulations?)/.*\.(scala|java|kt)$", f)]
    pl = grep_files(r, ctx.build_files, r"gatling|jmeter|k6|locust", 2)
    k6 = [f for f in ctx.files if f.endswith(".js") and re.search(r"(perf|load)", f)
          and find_lines(r, f, r"from\s+['\"]k6", 1)]
    # JMH / Caliper microbenchmarks: only files that sit in a benchmark directory or are named *Benchmark(s), and import the harness
    bench = []
    for f in ctx.files:
        if len(bench) >= 400 or not f.endswith((".java", ".kt")):
            continue
        if re.search(r"(^|/)(jmh|benchmarks?)/", f) or re.search(r"Benchmarks?\.(java|kt)$", f):
            h = find_lines(r, f, r"import\s+(?:org\.openjdk\.jmh|com\.google\.caliper)", 1)
            if h:
                bench.append(h[0])
    ev = [file_ev(f, 1, (read_lines(r, f) or [""])[0]) for f in (jm + gat + k6)[:3]] + bench[:3]
    perf_val = {"artefacts": len(jm) + len(gat) + len(k6) + len(bench),
                "tools": sorted(({"jmeter"} if jm else set()) | ({"gatling"} if gat else set()) | ({"k6"} if k6 else set())
                                | {("caliper" if "caliper" in e["snippet"] else "jmh") for e in bench})}
    if perf_val["artefacts"]:
        runs = grep_files(r, ctx.ci_files + ctx.ci_scripts(), r"gatling|jmeter|\bk6\b|locust|\bjmh\b|performance[-_ ]?test", 3)
        if runs:
            ev = ev + runs[:2]
        else:
            perf_val["not_run_reason"] = "no CI file or script that CI calls mentions running them"
    out["performance_tests"] = _kind(perf_val, ev, ext["performance"], pl)

    # Is test execution enabled where it matters?
    cmds = grep_files(r, ctx.ci_files, CI_TEST_CMD, 20, continuation=True)
    dg = ctx.default_goal_ci()  # goal-less `mvn` runs the pom's <defaultGoal>; cite both lines
    if dg:
        cmds = cmds + dg[0][:3] + [dg[1]]
    active = [e for e in cmds if not re.search(SKIP_FLAG, e["snippet"])]
    skipped = [e for e in cmds if re.search(SKIP_FLAG, e["snippet"])]
    skip_ci_more = grep_files(r, ctx.ci_files + ctx.mvn_config, SKIP_FLAG, 5)
    build_skip = [e for e in grep_files(r, [f for f in ctx.build_files if not ctx._test_module(f)], BUILD_SKIP, 20)
                  if not _in_optin_profile(r, e["path"], e["line_start"])][:5]
    out["build_level_test_skip"] = fact(bool(build_skip), "CONFIRMED" if build_skip else "NOT_FOUND", build_skip,
                                        "tests switched off inside pom/gradle")
    unres = ctx.unresolved_ci_includes()
    # A skip counts against the tests only where unit tests live: a switch in a runner/support module with no unit
    # tests (e.g. `test.enabled = false` in a journey-test module) says nothing about the application's own tests.
    skip_mods = {ctx.module_of(e["path"]) for e in build_skip}
    root_skip = "." in skip_mods
    build_skip_all = bool(build_skip) and (root_skip or (bool(unit_mods) and set(unit_mods) <= skip_mods))
    # tests switched off in some modules: "partially disabled" only when at least half of the modules holding unit tests are
    # skipped; one skipped module among many is listed in modules_with_tests_disabled, not allowed to define the pipeline
    skipped_unit = sorted(set(skip_mods) & set(unit_mods))
    build_skip_some = bool(build_skip) and not build_skip_all and bool(skipped_unit) and len(skipped_unit) * 2 >= len(unit_mods)
    out["modules_with_tests_disabled"] = fact(skipped_unit, "CONFIRMED" if skipped_unit else "NOT_FOUND", build_skip[:3] if skipped_unit else [],
                                              "modules that hold unit tests and switch them off in their build file")
    if not ctx.ci_files:
        state, st, ev = "no_ci", "NOT_FOUND", []
    elif build_skip_all and not active:
        state, st, ev = "disabled_in_build", "CONFIRMED", build_skip
    elif active:
        # one command that runs the tests is enough: skips elsewhere (an install step before the test step, a reproducible-
        # build job) are listed in ci_skip_flags, not allowed to turn the pipeline into "partially disabled"
        state, st, ev = (("disabled_in_build", "CONFIRMED", build_skip) if build_skip_all else
                         ("partially_disabled", "CONFIRMED", active + build_skip) if build_skip_some else
                         ("enabled", "CONFIRMED", active))
    elif skipped:
        state, st, ev = "disabled_in_pipeline", "CONFIRMED", skipped
    else:
        via = [e for e in grep_files(r, ctx.ci_scripts(), CI_TEST_CMD, 6, continuation=True) if not re.search(SKIP_FLAG, e["snippet"])]
        if via:  # a script CI calls runs the tests; whether this CI job reaches that command was not traced
            state, st, ev = "enabled", "INFERRED", via
        elif unres:
            state, st, ev = "unknown_remote_includes", "UNKNOWN", unres
        else:
            state, st, ev = "no_test_command_found", "NOT_FOUND", []
    out["ci_test_execution"] = fact(state, st, ev[:8],
                                    "found only inside a script that CI calls; which of its commands CI runs was not traced" if st == "INFERRED" else None)
    out["ci_skip_flags"] = fact([e["snippet"] for e in skip_ci_more], "CONFIRMED" if skip_ci_more else "NOT_FOUND", skip_ci_more,
                                "listed for transparency: a command that skips tests (an install or packaging step) does not mean the pipeline skips them; see ci_test_execution" if skip_ci_more else None)

    # Coverage: tools, enforcement and any report already on disk (JaCoCo, Kover, Cobertura, Clover)
    cov = coverage_tools.detect(ctx)
    jac = [e for t in cov for e in t["config_ev"]][:3]  # evidence that a coverage tool is configured
    enf = [e for t in cov for e in t["enforce_ev"]][:3]
    thr_t = next((t for t in cov if t["threshold"] is not None), None)
    # where the coverage tool is configured: a parent/root build applies to every module, a single module's build does not
    def _global(e):
        if e["path"].endswith("pom.xml"):
            # a parent pom's build configuration is inherited by its child modules
            return ctx.module_of(e["path"]) == "." or bool(ctx.pom_children.get(e["path"]))
        return ctx.module_of(e["path"]) == "." or bool(grep_files(r, [e["path"]], r"allprojects|subprojects", 1))
    prod_mods = [m for m in ctx.module_dirs() if m != "." and not ctx._test_module(m + "/x") and not ctx._aux(m + "/x")]
    cfg_ev = [e for t in cov for e in t["config_ev"]]
    cfg_mods = sorted({ctx.module_of(e["path"]) for e in cfg_ev})
    is_global = any(_global(e) for e in cfg_ev)
    partial_scope = bool(cov) and not is_global and len(prod_mods) > 3 and len(cfg_mods) * 2 < len(prod_mods)
    out["coverage_scope"] = fact({"configured_modules": len(cfg_mods), "total_modules": len(prod_mods), "partial": partial_scope},
                                 "CONFIRMED" if cov else "NOT_FOUND", cfg_ev[:3],
                                 "the coverage tool is configured in few modules and not in a parent or root build" if partial_scope else None)
    out["coverage_tool_configured"] = fact("+".join(t["id"] for t in cov) if cov else None, "CONFIRMED" if cov else "NOT_FOUND", jac)
    out["coverage_enforced"] = fact(bool(enf), "CONFIRMED" if enf else "NOT_FOUND", enf)
    out["coverage_threshold_pct"] = fact(thr_t["threshold"] if thr_t else None, "CONFIRMED" if thr_t else "NOT_FOUND",
                                         thr_t["threshold_ev"] if thr_t else [])
    # ratios declared as properties (commons.jacoco.lineRatio=0.96): they feed a rule that normally lives in a parent pom
    # this scan cannot read, so they show intent, not enforcement
    decl = grep_files(r, ctx.poms, r"<[\w.]*jacoco[\w.]*(?:Ratio|haltOnFailure|minimum)[\w.]*>\s*[\d.]+|<[\w.]*jacoco\.haltOnFailure>\s*true", 6) if cov else []
    out["coverage_thresholds_declared"] = fact(bool(decl) and not enf, "INFERRED" if decl and not enf else "NOT_FOUND",
                                               decl[:4] if not enf else [],
                                               "threshold properties are declared, but the rule that uses them is not in this repository's "
                                               "build files (likely a parent pom); enforcement is not shown" if decl and not enf else None)
    rep = coverage_tools.measure(r, [t["id"] for t in cov])
    ran = coverage_tools.executed_tests(r)
    discovered = unit + integ + len(acc_cls) + len(con_cls)
    representative = None if not ran or not discovered else ran["classes"] >= coverage_tools.REPRESENTATIVE_MIN * discovered
    out["coverage_run"] = fact({"executed_test_classes": ran["classes"], "executed_test_cases": ran["cases"],
                                "discovered_test_classes": discovered, "representative": representative}, "CONFIRMED",
                               [file_ev(ran["path"], 1, (read_lines(r, ran["path"]) or [""])[0])],
                               "JUnit results already on disk, compared with the test classes found in the sources") if ran \
        else fact(None, "NOT_FOUND", [], "no JUnit test results on disk, so a coverage report cannot be checked against the run that made it")
    if rep:
        stale = False
        rc, ct = run(["git", "log", "-1", "--format=%ct"], r)
        if rc == 0 and ct.isdigit():
            stale = os.path.getmtime(os.path.join(r, rep["path"])) < int(ct)
        ls = read_lines(r, rep["path"]) or [""]
        out["coverage_measured"] = fact(
            rep["counts"], "INFERRED" if (stale or representative is False) else "CONFIRMED", [file_ev(rep["path"], rep["line"], ls[min(rep["line"], len(ls)) - 1])],
            ("STALE: the report on disk is older than the HEAD commit, so it may not describe this code. " if stale else "")
            + ("PARTIAL RUN: the build behind this report executed %d of %d test classes, so these numbers do not describe the application. "
               % (ran["classes"], discovered) if representative is False else "")
            + "parsed from an existing %s %s report on disk; not produced by this scan" % (rep["tool"], rep["format"]))
    else:
        out["coverage_measured"] = fact(None, "UNKNOWN", [], "no coverage report (JaCoCo/Kover/Cobertura/Clover) on disk; run the build to measure")
    # Is the coverage gate actually reached by the pipeline? Configuration alone proves nothing about execution.
    ci_gate = grep_files(r, ctx.ci_files, r"jacocoTestCoverageVerification|koverVerify|koverBinaryVerify|jacoco:check", 2)
    gate_wire = grep_files(r, ctx.build_files, r"finalizedBy\s*\([^)]*(?:Verification|koverVerify|koverBinaryVerify)"
                                              r"|dependsOn\s*\([^)]*(?:Verification|koverVerify|koverBinaryVerify)", 2)
    mvn_check = [e for e in grep_files(r, ctx.poms, r"<goal>check</goal>", 20)
                 if coverage_tools.in_plugin(r, e["path"], e["line_start"], "jacoco")][:1] \
        if any(t["id"] == "jacoco" for t in cov) else []
    mvn_ci = grep_files(r, ctx.ci_files + ctx.ci_scripts(), r"(?:^|[\s:&;|\"'=-])(?:\./)?mvnw?\s+[^\n]*\b(?:verify|install|deploy)\b", 2, continuation=True)
    gradle_ci = [e for e in active if re.search(r"gradlew?\s", e["snippet"]) and re.search(r"\b(test|check|build)\b", e["snippet"])]
    if not enf:
        gate, gst, gev, gnote = "no_gate", "NOT_FOUND", [], None
    elif ci_gate:
        gate, gst, gev, gnote = "invoked_in_ci", "CONFIRMED", ci_gate, "the pipeline names the verification task"
    elif gate_wire and gradle_ci:
        gate, gst, gev, gnote = "wired_into_build", "INFERRED", gate_wire[:1] + gradle_ci[:1], \
            "the build wires the verification task to a task the pipeline runs; not observed running"
    elif mvn_check and mvn_ci:
        gate, gst, gev, gnote = "maven_lifecycle", "INFERRED", mvn_check + mvn_ci[:1], \
            "the JaCoCo check goal runs in the verify phase, which the pipeline's mvn command reaches; not observed running"
    elif unres:
        gate, gst, gev, gnote = "unknown_remote_includes", "UNKNOWN", unres[:1], "part of the pipeline is defined in templates that cannot be read offline"
    else:
        gate, gst, gev, gnote = "not_shown", "NOT_FOUND", [], "a gate is configured but nothing shows the pipeline running it"
    out["coverage_gate_in_ci"] = fact(gate, gst, gev, gnote)
    total_tests = unit + integ
    if total_tests == 0:
        cstate = "no_tests"
    elif state in ("disabled_in_pipeline", "disabled_in_build"):
        cstate = "tests_disabled_in_pipeline"
    elif not jac:
        cstate = "tests_present_coverage_not_configured"
    elif not enf:
        cstate = "coverage_configured_not_enforced"
    else:
        cstate = "coverage_enforced"
    out["coverage_state"] = fact(cstate, "CONFIRMED", (unit_ev[:1] + integ_ev[:1] + jac[:1] + enf[:1] + ev[:1]),
                                 "derived from tests.unit_tests, integration_tests, ci_test_execution, coverage_*",
                                 derivation={"rule": "coverage-state-from-tests-ci-and-coverage-config",
                                             "inputs": ["tests.unit_tests", "tests.integration_tests", "tests.ci_test_execution",
                                                        "tests.coverage_tool_configured", "tests.coverage_enforced"]})
    return out
