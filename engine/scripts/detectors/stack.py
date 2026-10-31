from __future__ import annotations

import os
import re

from evidence import fact, file_ev, grep_files, read_lines

NOTABLE = [
    ("spring-boot", r"spring-boot-starter(?!-test)|org\.springframework\.boot"),
    ("spring-web", r"spring-boot-starter-web|spring-webmvc"),
    ("spring-data-jpa", r"spring-boot-starter-data-jpa"),
    ("hibernate", r"hibernate-core"),
    ("kafka", r"spring-kafka|kafka-clients"),
    ("jms/activemq", r"activemq|spring-jms|artemis"),
    ("rabbitmq", r"spring-rabbit|amqp-client|starter-amqp"),
    ("jaxrs (jersey/resteasy)", r"resteasy|jersey|javax\.ws\.rs|jakarta\.ws\.rs"),
    ("ignite", r"ignite-"),
    ("postgresql", r"postgresql"),
    ("mysql", r"mysql-connector"),
    ("oracle", r"ojdbc|oracle"),
    ("mongodb", r"mongodb|mongo-java"),
    ("redis", r"spring-boot-starter-data-redis|jedis|lettuce"),
    ("actuator", r"spring-boot-starter-actuator"),
]


VERSION = "0.3.0"


# catalog entries that identify the Kotlin / Spring Boot version (not org.jetbrains.kotlinx.*, not other boot libraries)
KOTLIN_ENTRY = r"id\s*=\s*\"org\.jetbrains\.kotlin\.(?:jvm|multiplatform|android)\"|group\s*=\s*\"org\.jetbrains\.kotlin\"[^}]*name\s*=\s*\"kotlin-(?:stdlib[\w-]*|gradle-plugin)\"|module\s*=\s*\"org\.jetbrains\.kotlin:kotlin-(?:stdlib[\w-]*|gradle-plugin)\""
BOOT_ENTRY = r"id\s*=\s*\"org\.springframework\.boot\"|name\s*=\s*\"spring-boot-(?:gradle-plugin|dependencies|starter-parent)\"|module\s*=\s*\"org\.springframework\.boot:spring-boot-(?:gradle-plugin|dependencies|starter-parent)\""


def _gradle_var(ctx, name):
    """Value of a Gradle variable (`ext.name = '1.2'`, `name = "1.2"`, gradle.properties) when exactly one literal defines
    it. Returns (value, [evidence]) or None."""
    r = ctx.repo
    defs = grep_files(r, ctx.gradle + [f for f in ctx.files if os.path.basename(f) == "gradle.properties"],
                      r"\b(?:ext\.)?%s\s*=\s*['\"]?[\d][\w.-]*['\"]?\s*$" % re.escape(name), 3)
    vals = {re.search(r"=\s*['\"]?([\d][\w.-]*)", e["snippet"]).group(1) for e in defs}
    return (vals.pop(), defs[:1]) if len(vals) == 1 else None


def _catalog_version(ctx, entry_rx):
    """Version of a plugin/library from a Gradle version catalog (*.versions.toml): entries whose id/group starts with
    group_prefix, resolved through `version.ref` to the [versions] table. Used only when every such entry resolves to the
    same literal; otherwise (none, or disagreeing) returns None. `entry_rx` must match the whole entry line. Returns (version, [evidence...])."""
    r = ctx.repo
    found = []  # (version, entry_evidence, version_evidence)
    for f in sorted(x for x in ctx.files if x.endswith(".versions.toml") and not ctx._aux(x)):
        section, versions, entries = None, {}, []
        for i, ln in enumerate(read_lines(r, f) or [], 1):
            t = ln.strip()
            if t.startswith("#") or not t:
                continue
            if t.startswith("["):
                section = t.strip("[]").strip()
                continue
            if section == "versions":
                m = re.match(r"([\w.-]+)\s*=\s*\"([^\"]+)\"", t)
                if m:
                    versions[m.group(1)] = (m.group(2), i, ln)
            elif section in ("plugins", "libraries") and re.search(entry_rx, t):
                entries.append((i, ln, t))
        for i, ln, t in entries:
            ref = re.search(r"version\.ref\s*=\s*\"([\w.-]+)\"", t)
            lit = re.search(r"version\s*=\s*\"([^\"]+)\"", t)
            if ref and ref.group(1) in versions:
                v, vi, vl = versions[ref.group(1)]
                found.append((v, file_ev(f, i, ln), file_ev(f, vi, vl)))
            elif lit:
                found.append((lit.group(1), file_ev(f, i, ln), None))
    plug = [x for x in found if re.search(r"\bid\s*=", x[1]["snippet"])]
    found = plug or found  # the plugin's version is the compiler's; a library (stdlib) may lag behind it on purpose
    vals = {x[0] for x in found}
    if len(vals) != 1:
        return None
    first = found[0]
    return first[0], [e for e in (first[1], first[2]) if e]


DEP_LINE = re.compile(r"<artifactId>|<groupId>|['\"][\w.-]+:[\w.-]+|\b(?:implementation|api|compile|compileOnly|runtimeOnly|runtime|"
                      r"testImplementation|kapt|ksp|annotationProcessor|classpath)\b|\bid\s*\(?\s*['\"]|\balias\(")
NOT_DEP = re.compile(r"https?://|<link>|<exclude|excludePackageNames|<module>|Import-Package|<value>")


def _is_dependency(rx, line):
    """The match is part of a dependency coordinate: inside <artifactId>/<groupId>, or inside a quoted group:artifact
    string, or a Gradle plugin id. Not a javadoc link, an exclude list, a module name or a property."""
    for m in re.finditer(r"<(artifactId|groupId)>([^<]*)</\1>", line):
        if re.search(rx, m.group(2), re.I):
            return True
    for m in re.finditer(r"[\"']([^\"']+)[\"']", line):
        t = m.group(1)
        if re.search(rx, t, re.I) and not re.search(r"https?://|\s", t) and (":" in t or "." in t) \
                and re.search(r"\b(?:implementation|api|compile\w*|runtime\w*|test\w*|kapt|ksp|annotationProcessor|classpath|id|alias)\b", line):
            return True
    return False


def detect(ctx) -> dict:
    r = ctx.repo
    out = {}
    ant = "build.xml" in ctx.fileset and any("<project" in ln for ln in (read_lines(r, "build.xml") or [])[:60])
    ANT_NOTE = ("Ant builds are not analysed in this version: test, coverage and CI facts reflect conventional Maven/Gradle "
                "layouts only and may be incomplete")
    root_gradle = [f for f in ("settings.gradle.kts", "settings.gradle", "build.gradle.kts", "build.gradle") if f in ctx.fileset]
    roots = [n for n, here in (("maven", "pom.xml" in ctx.fileset), ("gradle", bool(root_gradle)), ("ant", ant)) if here]
    nested = [n for n, any_ in (("maven", bool(ctx.poms or ctx.nested_poms)), ("gradle", bool(ctx.gradle))) if any_ and n not in roots]
    if len(roots) == 1 and (nested or roots[0] == "ant"):
        # one build system at the repository root is the build; others found deeper are secondary tooling
        tool, st = roots[0], "CONFIRMED"
        first = {"maven": "pom.xml", "gradle": root_gradle[0] if root_gradle else None, "ant": "build.xml"}[tool]
        ln = next((i for i, x in enumerate(read_lines(r, first) or [""], 1) if x.strip()), 1)
        ev = [file_ev(first, ln, (read_lines(r, first) or [""])[ln - 1])]
        parts = []
        if tool == "ant":
            parts.append(ANT_NOTE)
        if nested:
            parts.append("%s files exist deeper in the tree (secondary tooling, a test module or publishing metadata) and were not treated as the build" % "/".join(nested))
        note = "; ".join(parts) or None
    elif ctx.poms and ctx.gradle:
        tool, ev, st, note = "maven+gradle", [], "CONFIRMED", "both build systems present - see llm_fill.ambiguities"
        ev = [file_ev(ctx.poms[0], 1, (read_lines(r, ctx.poms[0]) or [""])[0])] + grep_files(r, ctx.gradle[:1], r".", 1)
    elif ctx.poms:
        tool, st, note = "maven", "CONFIRMED", None
        ev = grep_files(r, ctx.poms[:1], r"<project", 1)
    elif ctx.gradle:
        tool, st, note = "gradle", "CONFIRMED", None
        ev = [file_ev(ctx.gradle[0], 1, (read_lines(r, ctx.gradle[0]) or [""])[0])]
    else:
        tool, st, note, ev = None, "NOT_FOUND", "no pom.xml or build.gradle(.kts) found", []
    if ctx.aux_build_files:
        note = ((note + "; ") if note else "") + "%d build file(s) under docs/samples/examples paths were not used" % len(ctx.aux_build_files)
    out["build_tool"] = fact(tool, st, ev, note)
    srcs = {}
    for lang, ext in (("java", ".java"), ("kotlin", ".kt")):
        fs = [f for f in ctx.src_main_java if f.endswith(ext)]
        srcs[lang] = fs
        out[lang + "_sources"] = fact(len(fs), "CONFIRMED" if fs else "NOT_FOUND",
                                      [file_ev(fs[0], 1, (read_lines(r, fs[0]) or [""])[0])] if fs else [],
                                      "files under src/main" if fs else None)
    langs = [l for l in ("java", "kotlin") if srcs[l]]
    out["language"] = fact("+".join(langs) if langs else None, "CONFIRMED" if langs else "NOT_FOUND", [],
                           derivation={"rule": "language-from-source-files",
                                       "inputs": ["stack.%s_sources" % l for l in langs]} if langs else None)
    kt = grep_files(r, ctx.gradle, r"kotlin\(\"jvm\"\)\s*version|kotlin-gradle-plugin|id\s*\(?\s*['\"]org\.jetbrains\.kotlin\.jvm['\"]", 1)
    kv = re.search(r"version\s*\(?\s*['\"]([\d.]+)['\"]", kt[0]["snippet"]) if kt else None
    kev = kt
    if kt and not kv:
        # version held in a variable: kotlin-gradle-plugin:$kotlin_version / ${kotlinVersion}
        var = re.search(r"kotlin-(?:gradle-plugin|allopen|stdlib[\w-]*):\$\{?(\w+)\}?", kt[0]["snippet"])
        res = _gradle_var(ctx, var.group(1)) if var else None
        if res:
            kv, kev = re.match(r"(.*)", res[0]), kt + res[1]
    if not kv and ctx.poms:
        mk = grep_files(r, ctx.poms, r"<kotlin\.version>\s*[\d][\w.-]*\s*<", 3)
        vals = {re.search(r">\s*([\d][\w.-]*)\s*<", e["snippet"]).group(1) for e in mk}
        if len(vals) == 1:
            kv, kev = re.match(r"(.*)", vals.pop()), mk[:1]
    if not kv:
        cat = _catalog_version(ctx, KOTLIN_ENTRY)
        if cat:
            kv, kev = re.match(r"(.*)", cat[0]), kev + cat[1]
    out["kotlin_version"] = fact(kv.group(1), "CONFIRMED", kev) if kv else fact(None, "NOT_FOUND", kev)
    wr = [f for f in ctx.files if os.path.basename(f) in ("mvnw", "gradlew")]
    out["build_wrapper"] = fact(wr, "CONFIRMED" if wr else "NOT_FOUND",
                                [file_ev(f, 1, (read_lines(r, f) or [""])[0]) for f in wr[:2]])
    # Java version: every declaration in a production build file (not a test module, fixture or sample)
    prod_poms = [f for f in ctx.poms if not ctx._test_module(f)]
    # a Gradle file whose own name says test (mockito.test-launcher-conventions) configures tests, not the code's target
    prod_gradle = [f for f in ctx.gradle if not ctx._test_module(f) and not re.search(r"(?i)(^|[./_-])tests?([./_-]|$)", os.path.basename(f))]
    if "secondary" in (note or "") or (tool in ("maven", "gradle") and "deeper in the tree" in (note or "")):
        # one build system is the build; the other, found only deeper in the tree, is side tooling whose Java level says nothing
        prod_poms, prod_gradle = (prod_poms, []) if tool == "maven" else ([], prod_gradle)
    cands = []  # (version, evidence)

    def norm(v):
        return v.replace("_", ".")
    POMVER = r"<(?:java\.version|maven\.compiler\.(?:source|target|release)|release|source|target)>\s*(1\.\d+|\d+)\s*<"
    for e in grep_files(r, prod_poms, POMVER, 40):
        for m in re.finditer(POMVER, (read_lines(r, e["path"]) or [""])[e["line_start"] - 1]):  # every match on a (compact) line
            cands.append((m.group(1), [e]))
    for e in grep_files(r, prod_poms, r"<(?:source|target|release)>\s*\$\{([\w.-]+)\}\s*<", 10):
        var = re.search(r"\$\{([\w.-]+)\}", e["snippet"]).group(1)
        d = grep_files(r, [e["path"]], r"<%s>\s*(?:1\.\d+|\d+)\s*<" % re.escape(var), 1)
        if d:
            m = re.search(r"<%s>\s*(1\.\d+|\d+)\s*<" % re.escape(var), (read_lines(r, d[0]["path"]) or [""])[d[0]["line_start"] - 1])
            cands.append((m.group(1), [d[0], e]))
    GRADLE_RX = (r"(?:source|target)Compatibility\s*=?\s*(?:JavaVersion\.VERSION_)?['\"]?(1[._]\d+|\d+)",
                 r"JavaLanguageVersion\.of\(\s*(\d+)", r"jvmToolchain\(\s*(\d+)", r"jvmTarget[\w.]*\s*[=(]?\s*(?:JvmTarget\.JVM_)?['\"]?(1[._]\d+|\d+)",
                 r"options\.release(?:\.set)?\s*[=(]\s*(\d+)")
    for e in grep_files(r, prod_gradle, "|".join(GRADLE_RX), 40):
        for rx in GRADLE_RX:
            m = re.search(rx, e["snippet"])
            if m:
                cands.append((norm(m.group(1)), [e]))
                break
    # a named constant in a convention plugin (val javaReleaseVersion = 11, DEFAULT_JDK = 8): found by name, so INFERRED
    heuristic = False
    NAMED = r"(?i)\b[\w]*(?:java|jdk|jvm)[\w]*(?:release|version|target|major)?[\w]*\s*=\s*['\"]?(1\.\d+|\d{1,2})['\"]?\s*$"
    for e in grep_files(r, [f for f in prod_gradle if re.search(r"(?i)(build-?logic|buildSrc|conventions?|\.gradle(\.kts)?$)", f)], NAMED, 20):
        m = re.search(NAMED, e["snippet"])
        if m and 5 <= float(m.group(1)[2:] if m.group(1).startswith("1.") else m.group(1)) <= 30 and not re.search(r"(?i)toolchain.*=|\bversion\s*=\s*['\"]\d+\.\d+\.\d+", e["snippet"]):
            cands.append((norm(m.group(1)), [e]))
            heuristic = True
    for e in grep_files(r, [f for f in ctx.files if f in (".java-version", ".sdkmanrc", ".tool-versions")], r"java|^\d", 2):
        m = re.search(r"(1\.\d+|\d+)", e["snippet"])
        if m:
            cands.append((m.group(1), [e]))
    from detectors.tests import _in_optin_profile
    prof = [c for c in cands if _in_optin_profile(r, c[1][-1]["path"], c[1][-1]["line_start"])]
    cands = [c for c in cands if c not in prof] or prof  # profile-scoped values only apply under that profile
    # unconditional declarations only; among conflicting values the lowest is the compatibility baseline (a toolchain,
    # a test release or a module-info compile can only be higher); ties keep the shallowest build file
    num = lambda v: float(v[2:] if v.startswith("1.") else v)
    cands.sort(key=lambda c: (num(c[0]), c[1][-1]["path"].count("/")))
    prof_note = ("; other values apply only inside profiles: " + ", ".join(sorted({c[0] for c in prof}))) if prof and cands and cands[0] not in prof else ""
    same = lambda v: v[2:] if v.startswith("1.") else v  # 1.8 and 8 are the same Java version
    distinct = list(dict.fromkeys(same(c[0]) for c in cands))
    if not cands:
        # last resort: the JDK the pipeline builds with (setup-java / a JDK image). It is a build JDK, not necessarily the target.
        ci = [e for e in grep_files(r, ctx.ci_files, r"java-version\s*:\s*['\"]?(\d+)|\bjdk\s*:\s*['\"]?(\d+)|openjdk[-:]?(\d+)", 6)]
        vals = sorted({int(g) for e in ci for g in re.search(r"(\d+)", e["snippet"].split(":", 1)[-1]).groups() if g} - {0}) if ci else []
        if vals:
            out["java_version"] = fact(str(vals[0]), "INFERRED", ci[:2],
                                       "no java version in build files; this is the JDK the pipeline builds with (lowest of %s), "
                                       "the compile target may be lower" % ", ".join(map(str, vals)))
        else:
            out["java_version"] = fact(None, "NOT_FOUND", [], "no explicit java version in build files")
    elif len(distinct) == 1 and not heuristic:
        out["java_version"] = fact(cands[0][0], "CONFIRMED", cands[0][1] + [e for c in cands[1:3] for e in c[1]][:2], prof_note.lstrip("; ") or None)
    else:
        seen_alt, alt_l = set(), []
        for c in cands:
            if (same(c[0]), c[1][-1]["path"]) not in seen_alt:
                seen_alt.add((same(c[0]), c[1][-1]["path"]))
                alt_l.append("%s (%s)" % (c[0], c[1][-1]["path"]))
        alt = "; ".join(alt_l[:6])
        out["java_version"] = fact(cands[0][0], "INFERRED", cands[0][1],
                                   ("found through a variable name, not a build setting; " if heuristic and len(distinct) == 1 else "") +
                                   "%d different values are declared (%s); the value shown is the lowest, the compatibility baseline%s" % (len(distinct), alt, prof_note))
    # Spring Boot version
    sb = grep_files(r, ctx.poms, r"spring-boot-starter-parent|spring-boot-dependencies", 1)
    sbv = None
    if sb:
        rel = sb[0]["path"]
        near = grep_files(r, [rel], r"<version>[^<]+</version>", 50)
        idx = sb[0]["line_start"]
        # same line first (compact poms put the whole <parent> on one line), then the next three lines
        same = re.search(r"spring-boot-(?:starter-parent|dependencies)</artifactId>\s*<version>([^<]+)<", (read_lines(r, rel) or [""])[idx - 1])
        cand = [e for e in near if idx < e["line_start"] <= idx + 3]
        if same:
            sbv = same.group(1)
        elif cand:
            m = re.search(r"<version>([^<]+)<", cand[0]["snippet"])
            sbv, sb = m.group(1), sb + cand[:1]
    else:
        sb = grep_files(r, ctx.gradle, r"org\.springframework\.boot['\"]?\)?\s*(version)?\s*['\"][\d.A-Za-z-]+['\"]", 1)
        if sb:
            m = re.search(r"['\"]([\d][^'\"]*)['\"]\s*\)?\s*$", sb[0]["snippet"])
            sbv = m.group(1) if m else None
        else:
            sb = grep_files(r, ctx.gradle, r"spring-boot-gradle-plugin:\$\{?(\w+)\}?", 1)
            var = re.search(r"spring-boot-gradle-plugin:\$\{?(\w+)\}?", sb[0]["snippet"]) if sb else None
            res = _gradle_var(ctx, var.group(1)) if var else None
            if res:
                sbv, sb = res[0], sb + res[1]
    if not sbv:
        cat = _catalog_version(ctx, BOOT_ENTRY)
        if cat:
            sbv, sb = cat[0], sb + cat[1]
    if sbv and "${" in sbv:  # never report a placeholder as the version: resolve it from <properties> or say nothing
        name = re.search(r"\$\{([^}]+)\}", sbv).group(1)
        d = grep_files(r, ctx.poms, r"<%s>\s*[\d][\w.-]*\s*<" % re.escape(name), 3)
        vals = {re.search(r">\s*([\d][\w.-]*)\s*<", e["snippet"]).group(1) for e in d}
        sbv, sb = (vals.pop(), sb + d[:1]) if len(vals) == 1 else (None, sb)
    out["spring_boot_version"] = fact(sbv, "CONFIRMED", sb) if sbv else \
        fact(None, "NOT_FOUND", sb, "no Spring Boot parent/plugin version found")
    pk = grep_files(r, ctx.poms, r"<packaging>\s*\w+\s*<", 1)
    pv = re.search(r">\s*(\w+)\s*<", pk[0]["snippet"]).group(1) if pk else None
    out["packaging"] = fact(pv, "CONFIRMED", pk) if pv else fact("jar", "INFERRED", [], "no <packaging>; Maven default")
    # Notable dependencies
    found, ev = [], []
    for name, rx in NOTABLE:
        # only a dependency declaration counts: not a javadoc link, an exclude list, a module name or a property
        hits = [e for e in grep_files(r, [f for f in ctx.build_files if not ctx._test_module(f)], rx, 30)
                if _is_dependency(rx, (read_lines(r, e["path"]) or [""])[e["line_start"] - 1])][:1]
        if hits:
            found.append(name)
            ev.extend(hits)
    out["notable_dependencies"] = fact(sorted(found), "CONFIRMED" if found else "NOT_FOUND", ev,
                                       "declared in production build files in any scope (a test-only database driver also appears here)" if found else None)
    from detectors import integrations
    out.update(integrations.detect(ctx))
    return out
