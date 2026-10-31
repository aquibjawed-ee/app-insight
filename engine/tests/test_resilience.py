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

    def test_deterministic(self):
        import json
        root = tempfile.mkdtemp()
        a = resilience.assess(F.make_repo(root, "x", F.HA_K8S))
        b = resilience.assess(F.make_repo(tempfile.mkdtemp(), "x", F.HA_K8S))
        self.assertEqual(json.dumps(a, sort_keys=True), json.dumps(b, sort_keys=True))


if __name__ == "__main__":
    unittest.main()
