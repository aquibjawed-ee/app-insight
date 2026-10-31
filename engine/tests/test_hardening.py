"""P0 hardening from the design review: each test pins a defect that was demonstrated before it was fixed."""
import json
import os
import sys
import tempfile
import unittest

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(HERE, "..", "scripts"))
sys.path.insert(1, HERE)
os.environ["DISCOVERY_FIXED_TIME"] = "2026-10-30T00:00:00Z"

import discover  # noqa: E402
import graph_fixtures as F  # noqa: E402
import relate  # noqa: E402
from graph import extract, model, resolve, safetynet  # noqa: E402

SECRET = "S3cr3t-Value-That-Must-Not-Appear"


def extract_one(files, name="hard", **kw):
    repo = F.make_repo(tempfile.mkdtemp(), name, files)
    return repo, extract.extract(repo, discover.build(repo), **kw)


class SymlinkTest(unittest.TestCase):
    def test_config_dir_never_follows_symlinks(self):  # F3 / evidence-rules 7
        outside = tempfile.mkdtemp()
        open(os.path.join(outside, "secret.yml"), "w").write("audit:\n  url: https://%s.acme-corp.io\n" % SECRET.lower())
        cfg = tempfile.mkdtemp()
        os.symlink(os.path.join(outside, "secret.yml"), os.path.join(cfg, "gap-profiles.yml"))   # a link to a file outside
        os.makedirs(os.path.join(outside, "d"))
        open(os.path.join(outside, "d", "application.yml"), "w").write("audit:\n  url: https://other.acme-corp.io\n")
        os.symlink(os.path.join(outside, "d"), os.path.join(cfg, "linkdir"))
        repo, doc = extract_one(F_PROFILES(), "gap-profiles", config_dirs=[cfg])
        text = json.dumps(doc)
        self.assertNotIn(SECRET.lower(), text)
        self.assertNotIn("other.acme-corp.io", text)
        events = [e for e in doc["edges"] if e["type"] == "CALLS_API" and e["attrs"].get("path") == "/events"]
        self.assertEqual(events[0]["resolution"]["state"], "unresolved")     # the value stayed unknown instead of being read through the link

    def test_a_symlinked_config_directory_itself_is_refused(self):
        real = tempfile.mkdtemp()
        open(os.path.join(real, "gap-profiles.yml"), "w").write("audit:\n  url: https://audit.acme-corp.io\n")
        link = os.path.join(tempfile.mkdtemp(), "cfg")
        os.symlink(real, link)
        _, doc = extract_one(F_PROFILES(), "gap-profiles", config_dirs=[link])
        self.assertNotIn("audit.acme-corp.io", json.dumps(doc))

    def test_oversized_and_non_config_files_in_the_config_dir_are_ignored(self):
        cfg = tempfile.mkdtemp()
        open(os.path.join(cfg, "gap-profiles.yml"), "w").write("audit:\n  url: https://audit.acme-corp.io\n" + "x: " + "y" * 2_000_000 + "\n")
        _, doc = extract_one(F_PROFILES(), "gap-profiles", config_dirs=[cfg])
        self.assertNotIn("audit.acme-corp.io", json.dumps(doc))


def F_PROFILES():
    import gap_fixtures as G
    return G.PROFILES


class CommentTest(unittest.TestCase):
    def test_commented_sql_and_yaml_are_not_evidence(self):  # F5 / evidence-rules 10
        files = {"pom.xml": F.pom("c", "3.2.4", "17", [F.dep("spring-boot-starter-web"), F.dep("spring-boot-starter-jdbc"), F.dep("postgresql", "org.postgresql")]),
                 "src/main/resources/application.yml": """spring:
  datasource:
    url: jdbc:postgresql://db.acme-corp.io:5432/x
  cloud:
    gateway:
      routes:
        - id: live
          uri: lb://live-service
          predicates:
            - Path=/live/**
        # - id: old
        #   uri: lb://ghost-service
        #   predicates:
        #     - Path=/ghost/**
""",
                 "src/main/resources/db/migration/V1__init.sql": "-- create table ghost_one (id int);\n/* create table ghost_two (id int); */\ncreate table real_table (id int);\n",
                 "src/main/java/c/A.java": "package c;\n@SpringBootApplication class A {}\n"}
        _, doc = extract_one(files, "c")
        text = json.dumps(doc)
        self.assertIn("real_table", text)
        for ghost in ("ghost_one", "ghost_two", "ghost-service", "/ghost/"):
            self.assertNotIn(ghost, text, ghost)
        self.assertIn("live-service", text)


class ExternalEvidenceTest(unittest.TestCase):
    def test_external_evidence_is_verified_and_a_changed_file_is_detected(self):  # F4 / evidence-rules 5, 8
        import gap_fixtures as G
        root = tempfile.mkdtemp()
        repo = F.make_repo(root, "gap-profiles", G.PROFILES)
        cfg = tempfile.mkdtemp()
        path = os.path.join(cfg, "gap-profiles.yml")
        open(path, "w").write("audit:\n  url: https://audit.acme-corp.io\n")
        out = tempfile.mkdtemp()
        self.assertEqual(relate.main(["analyse", repo, "--out", out, "--config-dir", cfg]), 0)
        self.assertEqual(relate.main(["validate", "--out", out]), 0)
        open(path, "w").write("audit:\n  url: https://changed.acme-corp.io\n")          # the external source changes after the analysis
        self.assertEqual(relate.main(["validate", "--out", out]), 1)

    def test_tampered_external_snippet_is_rejected(self):
        ev = {"kind": "file", "path": "[config-dir] a.yml", "line_start": 2, "line_end": 2, "snippet": "url: https://evil", "external": True, "app": "x"}
        cfg = tempfile.mkdtemp()
        open(os.path.join(cfg, "a.yml"), "w").write("audit:\n  url: https://audit.acme-corp.io\n")
        doc = {"contract": "relationships.v1", "scope": "application", "nodes": [{"id": "app:x", "type": "Application", "name": "x", "app": "x", "attrs": {}, "evidence": []},
                                                                                     {"id": "svc:y", "type": "Service", "name": "y", "app": None, "attrs": {}, "evidence": []}],
               "edges": [{"id": "e-1", "type": "CALLS_API", "source": "app:x", "target": "svc:y", "mechanism": "configuration", "basis": "static_configured", "confidence": "high", "status": "CONFIRMED",
                          "resolution": {"state": "resolved"}, "evidence": [ev], "attrs": {}}], "not_relationships": [], "meta": {}}
        self.assertTrue([e for e in model.validate_integrity(doc, {}, {"[config-dir] a.yml": os.path.join(cfg, "a.yml")}) if "snippet mismatch" in e])
        self.assertFalse(model.validate_integrity(doc, {}, {}) == [], "an external citation with nothing to verify it against must not pass silently")


class SecretEnvTest(unittest.TestCase):
    def test_secret_named_environment_values_are_never_cited(self):  # F8
        files = {"pom.xml": F.pom("s", "3.2.4", "17", [F.dep("spring-boot-starter-web"), F.dep("spring-cloud-starter-openfeign", "org.springframework.cloud")]),
                 "src/main/java/s/C.java": '@FeignClient(name = "x", url = "${PAY_API_TOKEN}")\ninterface X { @GetMapping("/a") String a(); }\n@FeignClient(name = "y", url = "${LEDGER_URL}")\ninterface Y { @GetMapping("/b") String b(); }\n',
                 "deploy/k8s/app.yaml": "apiVersion: apps/v1\nkind: Deployment\nmetadata:\n  name: s\nspec:\n  template:\n    spec:\n      containers:\n        - name: app\n          image: r.example.org/s:1\n          env:\n            - name: PAY_API_TOKEN\n              value: https://%s.acme-corp.io\n            - name: LEDGER_URL\n              value: https://ledger.acme-corp.io\n" % SECRET.lower()}
        _, doc = extract_one(files, "s")
        text = json.dumps(doc)
        self.assertNotIn(SECRET.lower(), text)
        self.assertIn("ledger.acme-corp.io", text)       # non-secret names still resolve


class MappingTierTest(unittest.TestCase):
    def test_class_level_mapping_is_a_separate_tier_and_not_counted_as_route_level(self):  # F6
        files = {"pom.xml": F.pom("u", "3.2.4", "17", [F.dep("spring-boot-starter-web")]),
                 "src/main/java/u/PingController.java": "package u;\n@RestController\n@RequestMapping(\"/ping\")\nclass PingController {\n  @GetMapping(\"/a\")\n  String a() { return \"a\"; }\n  @GetMapping(\"/b\")\n  String b() { return \"b\"; }\n}\n",
                 "src/test/java/u/PingControllerTest.java": "package u;\nclass PingControllerTest {\n  @Test void a() { assertEquals(\"a\", new PingController().a()); }\n  @Test void b() { mockMvc.perform(get(\"/ping/b\")).andExpect(status().isOk()); }\n}\n"}
        repo = F.make_repo(tempfile.mkdtemp(), "u", files)
        d = discover.build(repo)
        sn = safetynet.map_application(repo, extract.extract(repo, d), d)
        by = {c["label"]: c for c in sn["components"]}
        self.assertEqual(by["GET /ping/b"]["strength"], "route")
        self.assertEqual(by["GET /ping/a"]["strength"], "class")
        self.assertEqual(sn["summary"]["api_endpoint"]["direct"], 1)
        self.assertEqual(sn["summary"]["api_endpoint"]["class_level"], 1)


if __name__ == "__main__":
    unittest.main()
