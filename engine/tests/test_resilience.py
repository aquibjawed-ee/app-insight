"""Platform-aware HA configuration: Kubernetes/EKS, Helm, Nomad. `absent` = not in the files read; templated = unknown."""
import os
import sys
import tempfile
import unittest

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(HERE, "..", "scripts"))
sys.path.insert(1, HERE)
os.environ["DISCOVERY_FIXED_TIME"] = "2026-01-01T00:00:00Z"

import graph_fixtures as F  # noqa: E402
from graph import resilience  # noqa: E402


class ResilienceTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        root = tempfile.mkdtemp()
        cls.R = {n: resilience.assess(F.make_repo(root, n, f)) for n, f in (("ha", F.HA_K8S), ("weak", F.WEAK_K8S), ("helm", F.HELM_APP), ("nomad", F.NOMAD_APP), ("orders", F.ORDERS))}
        cls.empty = resilience.assess(F.make_repo(root, "nothing", {"pom.xml": F.pom("n", "3.2.4", "17", [])}))

    def st(self, app, cid):
        return next(s for s in self.R[app]["summary"] if s["id"] == cid)["state"]

    def test_fully_configured_kubernetes_workload_is_present_everywhere_and_eks_is_detected(self):
        for cid in ("replicas", "anti_affinity", "zone_spread", "pdb", "autoscaling", "readiness", "liveness", "startup", "rollout", "graceful_stop", "resources", "image_pinned"):
            self.assertEqual(self.st("ha", cid), "present", cid)
        self.assertTrue(self.R["ha"]["eks"]["detected"])
        self.assertEqual(self.R["ha"]["platforms"], ["kubernetes"])

    def test_weak_workload_is_flagged_with_reasons(self):
        for cid in ("replicas", "anti_affinity", "zone_spread", "pdb", "autoscaling", "readiness", "liveness", "rollout", "resources", "image_pinned"):
            self.assertEqual(self.st("weak", cid), "absent", cid)
        notes = {n for s in self.R["weak"]["summary"] for n in s.get("notes", [])}
        self.assertIn("Recreate stops every instance before starting new ones", notes)
        self.assertFalse(self.R["weak"]["eks"]["detected"])

    def test_an_ecr_image_alone_is_not_an_eks_signal(self):
        root = tempfile.mkdtemp()
        files = dict(F.WEAK_K8S)
        files["deploy/k8s/app.yaml"] = files["deploy/k8s/app.yaml"].replace("registry.example.org/weak-service:latest", "123456789012.dkr.ecr.eu-west-1.amazonaws.com/weak:1.0")
        self.assertFalse(resilience.assess(F.make_repo(root, "ecr", files))["eks"]["detected"])

    def test_missing_replicas_default_to_one_and_unset_strategy_is_the_kubernetes_default(self):
        self.assertEqual(self.st("orders", "replicas"), "absent")
        self.assertEqual(self.st("orders", "rollout"), "default")

    def test_findings_that_cite_a_file_carry_a_file_citation(self):
        e = next(s for s in self.R["ha"]["summary"] if s["id"] == "pdb")["evidence"][0]
        self.assertEqual((e["kind"], e["path"]), ("file", "deploy/k8s/app.yaml"))

    def test_helm_templated_values_are_read_from_values_yaml_or_reported_unknown(self):
        self.assertEqual(self.st("helm", "replicas"), "present")      # replicaCount: 2 in values.yaml
        self.assertEqual(self.st("helm", "pdb"), "present")           # podDisruptionBudget.enabled: true
        self.assertEqual(self.st("helm", "autoscaling"), "absent")    # autoscaling.enabled: false
        self.assertEqual(self.st("helm", "readiness"), "present")
        self.assertEqual(self.st("helm", "image_pinned"), "unknown")  # "{{ repo }}:{{ tag }}" is not a literal

    def test_nomad_job(self):
        for cid in ("replicas", "anti_affinity", "zone_spread", "readiness", "rollout", "graceful_stop", "resources", "restart_recovery", "image_pinned"):
            self.assertEqual(self.st("nomad", cid), "present", cid)
        self.assertEqual(self.R["nomad"]["platforms"], ["nomad"])
        self.assertEqual(self.st("nomad", "pdb"), "not_applicable")   # a Kubernetes concept

    def test_no_descriptor_means_not_assessed_not_failing(self):
        self.assertEqual(self.empty["state"], "not_assessed")
        self.assertTrue(all(s["state"] == "not_assessed" for s in self.empty["summary"]))
        self.assertIn("GitOps", self.empty["reason"])

    def test_test_harness_and_third_party_compose_files_are_not_the_deployment(self):
        pom = {"pom.xml": F.pom("orders-service", "3.2.4", "17", [])}
        harness = dict(pom, **{"contracts/docker-compose.yml": "version: '2'\nservices:\n  orders:\n    build:\n      context: ../\n  mock-server:\n    image: node:boron\n"})
        r = resilience.assess(F.make_repo(tempfile.mkdtemp(), "orders-service", harness))
        self.assertEqual((r["state"], r["workloads"]), ("not_assessed", []))
        self.assertEqual(r["ignored"][0]["file"], "contracts/docker-compose.yml")
        stack = dict(pom, **{"docker-compose.yaml": "services:\n  prometheus:\n    image: prom/prometheus:v2.45.0\n    restart: unless-stopped\n"
                                                    "  orders:\n    image: acme/orders-service:${TAG}\n    restart: always\n"})
        r = resilience.assess(F.make_repo(tempfile.mkdtemp(), "orders-service", stack))
        self.assertEqual([w["name"] for w in r["workloads"]], ["orders"])  # prometheus is what it runs next to
        self.assertEqual([x.get("service") for x in r["ignored"]], ["prometheus"])
        self.assertEqual(r["workloads"][0]["checks"]["image_pinned"]["state"], "unknown")  # tag set at deploy time
        rr = r["workloads"][0]["checks"]["restart_recovery"]
        self.assertNotIn("roll back without", rr["note"])  # a restart policy is not a rollback

    def test_codename_and_moving_tags_are_not_pinned(self):
        self.assertEqual(resilience._pinned("node:boron")[0], "absent")
        self.assertEqual(resilience._pinned("nginx:stable")[0], "absent")
        self.assertEqual(resilience._pinned("nginx")[0], "absent")
        self.assertEqual(resilience._pinned("nginx:1.25.3-alpine")[0], "present")
        self.assertEqual(resilience._pinned("nginx@sha256:" + "a" * 64)[0], "present")

    def test_a_deployment_this_check_cannot_read_is_named_not_failed(self):
        files = {"pom.xml": F.pom("orders-service", "3.2.4", "17", []),
                 "Jenkinsfile": "pipeline {\n  stages {\n    stage('Deploy') {\n      steps { sh 'ansible-playbook -i inventory/prod site.yml' }\n    }\n  }\n}\n"}
        r = resilience.assess(F.make_repo(tempfile.mkdtemp(), "orders-service", files))
        self.assertEqual(r["state"], "not_assessed")
        self.assertEqual((r["unread"]["mechanism"], r["unread"]["evidence"][0]["path"]), ("Ansible", "Jenkinsfile"))
        self.assertIn("Ansible", r["reason"])

    def test_deterministic(self):
        import json
        root = tempfile.mkdtemp()
        a = resilience.assess(F.make_repo(root, "x", F.HA_K8S))
        b = resilience.assess(F.make_repo(tempfile.mkdtemp(), "x", F.HA_K8S))
        self.assertEqual(json.dumps(a, sort_keys=True), json.dumps(b, sort_keys=True))


if __name__ == "__main__":
    unittest.main()
