#!/usr/bin/env python3
"""Guard check: every protection in the dependency / hosting / module detector must be backed by a fixture that FAILS without it.

  guard_check.py [--only NAME]...

For each mutation below, this copies the whole skill to a temporary directory (the real files are never touched), removes one
guard from `scripts/detectors/integrations.py` in the copy, runs the named benchmark cases there, and requires them to fail. A
baseline run of the same cases on the unmodified copy must pass first. A mutation whose text no longer occurs exactly once is
reported as stale, so a refactor cannot silently turn a guard check into a no-op. Stdlib only. Exit 0 all guards proven, 1 a guard
is unproven or stale, 2 could not run. Takes a few minutes; it is not part of the default test run (see tests/test_integrations.py).
"""
from __future__ import annotations

import argparse
import os
import shutil
import subprocess
import sys
import tempfile

HERE = os.path.dirname(os.path.abspath(__file__))
SKILL = os.path.dirname(HERE)
TARGET = os.path.join("scripts", "detectors", "integrations.py")

# (name, exact text in integrations.py, replacement, benchmark cases that must fail without the guard)
MUTATIONS = [
    ("test scope counted as application", 'scope = "test" if (sc and sc.group(1) == "test") or test_mod else "runtime"', 'scope = "runtime"',
     ["deps_h2_test_only_is_not_the_database", "deps_test_module_dependencies_are_tests_only"]),
    ("plugin / managed / exclusion blocks not removed", '("pluginManagement", "dependencyManagement", "plugin", "exclusions")', "()",
     ["deps_comment_plugin_managed_exclusion_not_counted"]),
    ("XML comments not removed", "    text = _strip_comments(text)\n", "",
     ["deps_comment_plugin_managed_exclusion_not_counted"]),
    ("coordinates matched as substrings", "rx.fullmatch(coord)", "rx.search(coord)", ["deps_comment_plugin_managed_exclusion_not_counted"]),
    ("generic SQL not merged into the named database", "        if pool:\n            items.remove(it)", "        if False:\n            items.remove(it)",
     ["deps_spring_boot_postgres_redis_kafka"]),
    ("IDE bin/ output copy read as configuration", 're.match(r"(?:.*/)?bin/(?:main|test|default|production)/", f)', "False",
     ["deps_ide_output_copy_is_ignored"]),
    (".env.example read as configuration", 'return b.startswith(".env") and not re.search(r"(?i)example|sample|template|dist|tmpl", b)', 'return b.startswith(".env")',
     ["deps_env_example_is_documentation"]),
    ("spring.config.import read without its value", "(vrx is None or vrx.search(val))", "True", ["deps_spring_config_import_of_a_file_is_no_service"]),
    ("endpoint to localhost / placeholder host accepted", 'or ENDPOINT_HOST_NOT.match(m.group(1))', "", ["deps_endpoints_named_in_configuration"]),
    ("documentation / callback endpoint keys accepted", "or ENDPOINT_NOT.search(key)", "", ["deps_endpoints_named_in_configuration"]),
    ("JWT helper library read as an identity provider", 'r"io\\.micronaut\\.security:micronaut-security-(?:jwt|oauth2)",',
     'r"io\\.micronaut\\.security:micronaut-security-(?:jwt|oauth2)", r"com\\.auth0:jwks-rsa",', ["deps_jwt_library_alone_is_not_an_identity_provider"]),
    ("developmentOnly Gradle configuration counted as the application", 'conf == "developmentOnly" or ', "",
     ["deps_dev_only_gradle_configuration_is_not_the_application"]),
    ("a Gradle script-plugin directory listed as a module", "if not pom and d not in gm and gfiles and not any(", "if False and not pom and d not in gm and gfiles and not any(",
     ["modules_gradle_script_plugin_directory_is_not_a_module"]),
    ("the word 'application' in a dependency makes an application", "|\\bbootJar\\b|", "|\\bbootJar\\b|\\bapplication\\b|",
     ["modules_word_application_in_a_dependency_is_not_an_application"]),
    ("test-only sources not recognised as a tests module", '(role != "aggregator" and d in own_test and not own_src)', "False",
     ["modules_test_sources_only_is_a_tests_module"]),
    ("a Spring Boot dependency read as the Boot plugin", 'r"id\\s*\\(?\\s*[\\"\']org\\.springframework\\.boot[\\"\']|apply', 'r"org\\.springframework\\.boot|apply',
     ["modules_spring_boot_dependency_is_not_the_boot_plugin"]),
    ("an environment's endpoint cited before the production one", "(0 if re.search(r\"(?:^|/)(?:prod|production|live)(?:/|[-_.])\", host_ev[1][\"path\"]) else 1, host_ev[0])", "(1, host_ev[0])",
     ["deps_endpoint_prefers_the_production_value"]),
    ("a developer-machine file read as the deployed configuration", 'cbasis = "local configuration" if is_local_file(f) else "connection setting"', 'cbasis = "connection setting"',
     ["deps_local_config_file_is_not_the_deployed_setting"]),
    ("a dev environment's deployment directory treated as a laptop", "return bool(LOCAL_FILE.search(path)) and not DEPLOY_DIR.search(path)", "return bool(LOCAL_FILE.search(path))",
     ["deps_dev_environment_directory_is_deployment_config"]),
    ("evidence from another scope cited for the claim shown", 'pool = deciding or it["ev"]', 'pool = it["ev"]',
     ["deps_only_evidence_from_the_deciding_scope_is_cited"]),
    ("evidence of another kind cited for the claim shown", 'narrowed = [t for t in pool if want and t[2] in want] or pool', "narrowed = pool",
     ["deps_local_config_file_is_not_the_deployed_setting"]),
    ("an APM key read as a service", '(r"(?:^|\\.)(?:elastic\\.)?apm(?:\\.|$)", MON, "APM agent"), ', "", ["deps_apm_key_is_observability_not_a_service_and_vendor_tool_urls_are_ignored"]),
    ("an environment variable named by its YAML parents", 'label = last if re.fullmatch(r"[A-Z][A-Z0-9_]{3,}", last) else key', "label = key",
     ["deps_env_style_endpoint_is_named_by_its_variable_and_environments_are_labelled"]),
    ("the environment of each host not recorded", '"env": env_of(ev["path"])', '"env": None',
     ["deps_env_style_endpoint_is_named_by_its_variable_and_environments_are_labelled"]),
    ("commented-out Jib read as an image build", 'tools\\.jib", 3)', 'tools\\.jib", 3, skip_comments=False)', ["container_jib_commented_out_is_not_a_build"]),
    ("a Jib image held in a variable reported as a value", 'if (not v or re.search(r"[$<{]", v)) else', "if False else", ["container_jib_images_set_by_variables_are_not_reported"]),
    ("a Maven ${property} Jib image reported as a value", 'put(key, (None if re.search(r"[$<{]", v) else v, ln, lines[ln - 1])', "put(key, (v, ln, lines[ln - 1])",
     ["container_jib_maven_property_image_is_not_reported"]),
    ("Jib reported as run by the pipeline when no pipeline file runs it", 'via = "the pipeline" if run else', 'via = "the pipeline" if True else', ["container_jib_not_run_by_pipeline"]),
    ("the Jib base image left out of the base images", 'bases.insert(0, jib["base_image"])', "pass", ["container_jib_maven_configured"]),
    ("the registry named in the build file not reported", "                                                              or f in ctx.build_files)]", "                                                              )]", ["hosting_registry_named_in_a_build_file"]),
    ('a Spring Boot plugin with no image configuration counted as an image build', '            ln_of = lambda off: bisect.bisect_left(nl, i0 + off) + 1\n            g = re.search(r"<goal>\\s*build-image\\s*</goal>", blk)', '            ln_of = lambda off: bisect.bisect_left(nl, i0 + off) + 1\n            out["configured"] = True\n            g = re.search(r"<goal>\\s*build-image\\s*</goal>", blk)',
     ['container_spring_boot_maven_plugin_alone_is_not_an_image_build']),
    ('a Maven ${property} Spring Boot image name reported as a value', 'take(key, (None if re.search(r"[$<{]", v) else v, ln, lines[ln - 1]), pom)', 'take(key, (v, ln, lines[ln - 1]), pom)',
     ['container_spring_boot_maven_image_name_from_property_is_not_reported']),
    ('a commented-out bootBuildImage block read as an image build', 'hdr = re.compile(r"^(?!\\s*(?://|\\*|/\\*)).*\\b(?:bootBuildImage', 'hdr = re.compile(r"^.*\\b(?:bootBuildImage',
     ['container_spring_boot_build_image_commented_out_is_not_a_build']),
    ('bootBuildImage inside an echo read as a pipeline run', 'find_lines(r, f, r"spring-boot:build-image|bootBuildImage", 10, continuation=True, flags=0):\n            if at_command_position(', 'find_lines(r, f, r"spring-boot:build-image|bootBuildImage", 10, continuation=True, flags=0):\n            if True or at_command_position(',
     ['container_spring_boot_build_image_text_in_echo_is_not_a_run']),
    ('the Spring Boot image name and registry not reported as an image registry', 'refs += [(t, sb["ev"][0]) for t in (sb["image_name"], sb["registry"]) if t and sb["ev"]]', 'refs += []',
     ['container_spring_boot_gradle_kotlin_dsl_configured']),
    ('the Quarkus extension alone counted as an image build', '(qk and qk["enabled"]))', 'qk)',
     ['container_quarkus_extension_alone_does_not_build_an_image', 'container_quarkus_build_switched_off', 'container_quarkus_dev_profile_does_not_build_the_production_image']),
    ('a %dev Quarkus profile counted for the production image', 'if k not in want or prof not in (None, "prod"):', 'if k not in want:',
     ['container_quarkus_dev_profile_does_not_build_the_production_image']),
    ('a %prod property line not read', '(%?[\\w.\\-\\[\\]\\"\']+)\\s*[=:]', '([\\w.\\-\\[\\]\\"\']+)\\s*[=:]',
     ['container_quarkus_prod_profile_enables_the_build']),
    ('a Quarkus ${expression} value reported as a string', 'if not val or re.search(r"[$<{]", val):\n            out["set_by_variable"].append(slot)', 'if not val or False:\n            out["set_by_variable"].append(slot)',
     ['container_quarkus_expression_values_are_not_reported']),
    ('only the first Quarkus flag on a pipeline line read', 'for m in re.finditer(r"quarkus\\.container-image\\.(build|push)=(true|false)", e["snippet"]):', 'for m in [re.search(r"quarkus\\.container-image\\.(build|push)=(true|false)", e["snippet"])]:',
     ['container_quarkus_enabled_by_pipeline_flag']),
    ('the Quarkus registry not reported as an image registry', 'refs += [(t, qk["ev"][-1]) for t in (qk["image"], qk["registry"]) if t]', 'refs += []',
     ['container_quarkus_container_image_enabled_in_config']),
    ("tool configuration read for endpoints", 'if b.startswith(".") or re.search(', 'if False and re.search(', ["deps_endpoints_in_tool_config_are_not_the_applications"]),
    ("Dockerfile stage alias reported as a base image", "if img.lower() in stages or img.lower() ==", "if False or img.lower() ==", ["container_dockerfile_base_images"]),
    ("deploy command accepted anywhere on the line", "if at_command_position(e[\"snippet\"], rx) and n < 2:", "if n < 2:", ["hosting_command_text_inside_echo_is_ignored"]),
    ("serverless.yml accepted for any provider", 'r"^\\s*name:\\s*aws\\b", "AWS Lambda (Serverless Framework)"', 'None, "AWS Lambda (Serverless Framework)"',
     ["hosting_serverless_yml_for_another_cloud"]),
    ("image registry reported as a deployment target", 'grep_files(r, reg_files, rx, 1, flags=re.I):\n            add(target, "image registry", "image reference", e, "image reference")',
     'grep_files(r, reg_files, rx, 1, flags=re.I):\n            add(target, "deployment target", "image reference", e, "image reference")', ["hosting_registry_is_not_a_target"]),
    ("Helm / Kustomize / manifests shown as separate targets", 'plat = "Kubernetes" if target in K8S_FAMILY else target', "plat = target",
     ["hosting_kubernetes_helm_kustomize_kubectl_are_one_target", "hosting_helm_chart"]),
    ("hosting NOT_FOUND where the pipeline cannot be read", "    elif remote or server_side:", "    elif False:",
     ["hosting_unknown_when_pipeline_templates_are_remote", "hosting_unknown_when_only_a_jenkinsfile_exists"]),
    ("a cloud SDK dependency counted as a deployment target", "    for rx, target in REGISTRIES:\n        for e in grep_files(r, reg_files, rx, 1, flags=re.I):",
     '    for e in grep_files(r, ctx.build_files, r"software\\.amazon\\.awssdk", 1):\n        add("AWS", "deployment target", "dependency", e, "SDK")\n    for rx, target in REGISTRIES:\n        for e in grep_files(r, reg_files, rx, 1, flags=re.I):',
     ["hosting_cloud_sdk_is_not_a_deployment_target"]),
]


def run_cases(root, cases):
    cmd = [sys.executable, os.path.join(root, "benchmark", "run_benchmark.py"), "--out", os.path.join(root, "_out")]
    for c in cases:
        cmd += ["--case", c]
    p = subprocess.run(cmd, cwd=root, capture_output=True, text=True, timeout=600)
    return p.returncode


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--only", action="append", help="run only mutations whose name contains this text")
    a = ap.parse_args(argv)
    todo = [m for m in MUTATIONS if not a.only or any(o in m[0] for o in a.only)]
    if not todo:
        print("no mutation matches", file=sys.stderr)
        return 2
    bad = 0
    with tempfile.TemporaryDirectory(prefix="guardcheck-") as tmp:
        for name, old, new, cases in todo:
            root = os.path.join(tmp, "skill")
            shutil.rmtree(root, ignore_errors=True)
            shutil.copytree(SKILL, root, ignore=shutil.ignore_patterns("__pycache__", ".modernise", "*.pyc", "tests", "_out"))
            path = os.path.join(root, TARGET)
            src = open(path, encoding="utf-8").read()
            if src.count(old) != 1:
                print("STALE     %s (mutation text occurs %d times)" % (name, src.count(old)))
                bad += 1
                continue
            if run_cases(root, cases) != 0:
                print("BASELINE  %s: the cases already fail without the mutation" % name)
                bad += 1
                continue
            open(path, "w", encoding="utf-8").write(src.replace(old, new))
            if run_cases(root, cases) == 0:
                print("UNPROVEN  %s: no fixture fails when this guard is removed" % name)
                bad += 1
            else:
                print("proven    %s" % name)
    print("%d of %d guards proven" % (len(todo) - bad, len(todo)))
    return 1 if bad else 0


if __name__ == "__main__":
    sys.exit(main())
