"""Platform-aware resilience / high-availability configuration check (resilience.v1).

Reads deployment descriptors that are in the repository and says, per workload and per check, whether the HA setting is `present`, `absent`
(a descriptor of that workload was read and the setting is not in it), `unknown` (templated, defined elsewhere, or not readable) or
`not_applicable`. Nothing is run or queried; a cluster, GitOps repository or platform team may add what is absent here, so `absent` means
"not in these files", never "not in production".

Platforms: Kubernetes (plain manifests and Helm charts, EKS hints), HashiCorp Nomad, Docker Compose. Checks are grouped:
redundancy (replicas, anti-affinity, zone spread, PodDisruptionBudget, autoscaling), health (probes), rollout (strategy, graceful stop),
capacity (requests/limits), recovery (restart/reschedule/rollback), supply (pinned image).
"""
from __future__ import annotations

import os
import re
from typing import Dict, List, Optional

import evidence
from detectors import Ctx
from detectors import integrations as I
from graph.adapters.common import ev

CONTRACT = "resilience.v1"
VERSION = "0.1.0"

CHECKS = [  # id, group, title, why it matters
    ("replicas", "Redundancy", "More than one instance", "A single instance is a single point of failure and goes down on every rollout or node loss."),
    ("anti_affinity", "Redundancy", "Pods spread across nodes (anti-affinity)", "Without it the scheduler may place every replica on one node."),
    ("zone_spread", "Redundancy", "Spread across availability zones", "Survives the loss of a whole zone (on EKS: multi-AZ node groups plus a zone topology key)."),
    ("pdb", "Redundancy", "PodDisruptionBudget", "Stops node drains and upgrades from evicting every replica at once."),
    ("autoscaling", "Redundancy", "Autoscaling with a floor of two or more", "Keeps capacity under load without dropping below two instances."),
    ("readiness", "Health", "Readiness probe", "Traffic is only sent to instances that can serve it."),
    ("liveness", "Health", "Liveness probe", "Hung instances are restarted automatically."),
    ("startup", "Health", "Startup probe", "Slow-starting applications are not killed by the liveness probe while booting."),
    ("rollout", "Rollout", "Rolling update with a stated surge/unavailable limit", "Deployments replace instances gradually instead of all at once."),
    ("graceful_stop", "Rollout", "Graceful shutdown (grace period or preStop)", "In-flight requests finish before the instance is stopped."),
    ("resources", "Capacity", "Resource requests and limits", "Predictable scheduling and protection from noisy neighbours and OOM evictions."),
    ("restart_recovery", "Recovery", "Restart / reschedule / auto-revert policy", "Failed instances come back and bad releases roll back without a person."),
    ("image_pinned", "Supply", "Image pinned to a version", "A moving tag such as :latest makes rollbacks and reproducibility unreliable."),
]
GROUPS = ["Redundancy", "Health", "Rollout", "Capacity", "Recovery", "Supply"]
APPLIES = {  # which platforms each check is meaningful for
    "kubernetes": {c[0] for c in CHECKS}, "nomad": {"replicas", "anti_affinity", "zone_spread", "readiness", "rollout", "graceful_stop", "resources", "restart_recovery", "image_pinned"},
    "compose": {"replicas", "readiness", "restart_recovery", "image_pinned", "resources"}}
# EKS-specific signals only. An ECR image or an AWS SDK says nothing about EKS (ECR also serves ECS and Lambda).
EKS_HINT = re.compile(r"eks\.amazonaws\.com|eksctl\.io|aws_eks_|alb\.ingress\.kubernetes\.io|karpenter\.sh|ebs\.csi\.aws\.com|aws-load-balancer-controller")
ZONE_KEY = re.compile(r"topology\.kubernetes\.io/zone|failure-domain\.beta\.kubernetes\.io/zone|topology\.ebs\.csi\.aws\.com/zone")


def _res(state, value=None, note=None, e=None):
    return {"state": state, "value": value, "note": note, "evidence": [e] if e else []}


def _first(lines, rx, flags=0):
    r = re.compile(rx, flags)
    for i, ln in enumerate(lines, 1):
        s = ln.strip()
        if s.startswith("#") or s.startswith("//"):
            continue
        if r.search(ln):
            return i
    return None


def _docs(lines):
    starts = [0] + [i + 1 for i, l in enumerate(lines) if l.strip() == "---"]
    for n, s in enumerate(starts):
        e = (starts[n + 1] - 1) if n + 1 < len(starts) else len(lines)
        yield s, lines[s:e]


def _kind(doc):
    for l in doc:
        m = re.match(r"^kind:\s*(\w+)", l)
        if m:
            return m.group(1)
    return None


def _name(doc):
    meta = next((i for i, l in enumerate(doc) if re.match(r"^metadata:\s*$", l)), None)
    if meta is None:
        return None
    for j in range(meta + 1, len(doc)):
        if re.match(r"^\S", doc[j]):
            break
        m = re.match(r"^\s{2}name:\s*[\"']?([^\s\"'#]+)", doc[j])
        if m:
            return m.group(1)
    return None


def _helm_values(repo, ctx, chart_dir):
    out = {}
    for f in ctx.files:
        if os.path.dirname(f) == chart_dir and re.match(r"values[^/]*\.ya?ml$", os.path.basename(f)) and os.path.basename(f) in ("values.yaml", "values.yml"):
            lines = evidence.read_lines(repo, f) or []
            for k, v, i in I.flatten(lines, "yaml"):
                out[k] = (v, i, f, lines)
    return out


def k8s_checks(app, repo, f, s, doc, lines_all, ctx, siblings, helm_vals, eks):
    """Checks for one Deployment/StatefulSet document. `siblings` is the repository-wide set of kinds found (PDB, HPA)."""
    text = "\n".join(doc)
    templated = "{{" in text
    base = s  # offset of doc inside file

    def at(rx, flags=0):
        i = _first(doc, rx, flags)
        return ev(f, base + i, lines_all, app) if i else None
    c = {}
    # replicas
    m = re.search(r"^\s*replicas:\s*(\S+)", text, re.M)
    hv = helm_vals.get("replicaCount") or helm_vals.get("replicas")
    n = None
    if m and "{{" not in m.group(1):
        n = int(m.group(1)) if m.group(1).isdigit() else None
        e = at(r"^\s*replicas:")
    elif hv and hv[0].isdigit():
        n, e = int(hv[0]), ev(hv[2], hv[1], hv[3], app)
    else:
        e = at(r"^\s*replicas:")
    hpa = siblings.get("HorizontalPodAutoscaler") or siblings.get("ScaledObject")
    if n is not None:
        c["replicas"] = _res("present" if n >= 2 else "absent", n, None if n >= 2 else "a single replica", e)
    elif hpa:
        c["replicas"] = _res("unknown", None, "replica count not stated here; an autoscaler exists", e)
    else:
        c["replicas"] = _res("unknown" if templated or m else "absent", None, "replicas not set: Kubernetes defaults to 1" if not (templated or m) else "value comes from a template or Helm value not read", e)
    # anti-affinity and zone spread
    pa = at(r"podAntiAffinity:")
    ts = at(r"topologySpreadConstraints:")
    aff_helm = helm_vals.get("affinity")
    if pa:
        c["anti_affinity"] = _res("present", None, None, pa)
    elif ts:
        c["anti_affinity"] = _res("present", "topologySpreadConstraints", "spread via topology constraints", ts)
    elif templated and ("affinity" in text or aff_helm):
        c["anti_affinity"] = _res("unknown", None, "affinity comes from a Helm value", None)
    else:
        c["anti_affinity"] = _res("absent", None, "no podAntiAffinity or topologySpreadConstraints", None)
    zone = None
    for i, l in enumerate(doc):
        if ZONE_KEY.search(l) and not l.strip().startswith("#"):
            zone = ev(f, base + i + 1, lines_all, app)
            break
    if zone:
        c["zone_spread"] = _res("present", None, None, zone)
    elif templated and (ts or pa or "affinity" in text):
        c["zone_spread"] = _res("unknown", None, "topology key may come from a Helm value", ts or pa)
    else:
        c["zone_spread"] = _res("absent", None, "no zone topology key" + (" (EKS detected: nodes usually span several zones)" if eks else ""), None)
    # PDB / autoscaling (repository-wide kinds)
    pdb = siblings.get("PodDisruptionBudget")
    helm_pdb = helm_vals.get("podDisruptionBudget.enabled") or helm_vals.get("podDisruptionBudget.minAvailable") or helm_vals.get("pdb.enabled")
    if pdb:
        c["pdb"] = _res("present", None, "a PodDisruptionBudget exists in the repository; its selector was not matched to this workload", pdb)
    elif helm_pdb:
        c["pdb"] = _res("present" if str(helm_pdb[0]).lower() not in ("false", "0") else "absent", helm_pdb[0], "Helm value", ev(helm_pdb[2], helm_pdb[1], helm_pdb[3], app))
    else:
        c["pdb"] = _res("absent", None, "no PodDisruptionBudget in the repository (it may be managed elsewhere)", None)
    hv_as = helm_vals.get("autoscaling.enabled")
    hv_min = helm_vals.get("autoscaling.minReplicas")
    if hpa:
        mn = re.search(r"minReplicas:\s*(\d+)", hpa["snippet"])
        c["autoscaling"] = _res("present", None, "autoscaler found", hpa)
    elif hv_as and str(hv_as[0]).lower() == "true":
        c["autoscaling"] = _res("present" if not hv_min or int(hv_min[0] or 0) >= 2 else "absent", hv_min[0] if hv_min else None, "Helm value", ev(hv_as[2], hv_as[1], hv_as[3], app))
    else:
        c["autoscaling"] = _res("absent", None, "no HorizontalPodAutoscaler or KEDA ScaledObject in the repository", None)
    # probes
    for pid, key in (("readiness", "readinessProbe"), ("liveness", "livenessProbe"), ("startup", "startupProbe")):
        e = at(key + r":")
        c[pid] = _res("present", None, None, e) if e else _res("absent" if pid != "startup" else "absent", None, "not defined in the workload", None)
    # rollout
    st = at(r"strategy:")
    typ = re.search(r"strategy:\s*\n(?:\s+.*\n)*?\s+type:\s*(\w+)", text + "\n")
    mu = at(r"maxUnavailable:")
    if typ and typ.group(1) == "Recreate":
        c["rollout"] = _res("absent", "Recreate", "Recreate stops every instance before starting new ones", st)
    elif mu:
        c["rollout"] = _res("present", None, None, mu)
    else:
        c["rollout"] = _res("absent", None, "no strategy stated: Kubernetes defaults to RollingUpdate 25%/25%", st)
        c["rollout"]["state"] = "default"
    tg = at(r"terminationGracePeriodSeconds:")
    ps = at(r"preStop:")
    c["graceful_stop"] = _res("present", None, None, ps or tg) if (tg or ps) else _res("absent", None, "grace period left at the default (30s) and no preStop hook", None)
    # resources
    req, lim = at(r"^\s*requests:"), at(r"^\s*limits:")
    hv_res = helm_vals.get("resources.limits.memory") or helm_vals.get("resources.requests.cpu")
    if req and lim:
        c["resources"] = _res("present", None, None, lim)
    elif req or lim:
        c["resources"] = _res("absent", None, "only %s set" % ("requests" if req else "limits"), req or lim)
    elif hv_res:
        c["resources"] = _res("present", None, "Helm value", ev(hv_res[2], hv_res[1], hv_res[3], app))
    else:
        c["resources"] = _res("unknown" if templated else "absent", None, "no requests/limits" if not templated else "set through a Helm value that is empty or not read", None)
    # recovery: k8s restarts by default (restartPolicy Always); rollback is a CI concern
    rp = at(r"restartPolicy:")
    c["restart_recovery"] = _res("present", None, "Deployments restart failed containers by default (restartPolicy: Always)", rp)
    # image
    im = re.search(r"^\s*-?\s*image:\s*[\"']?([^\s\"']+)", text, re.M)
    if im and "{{" not in im.group(1):
        tag = im.group(1).rsplit(":", 1)[1] if ":" in im.group(1).split("/")[-1] else None
        e = at(r"image:")
        c["image_pinned"] = _res("present" if tag and tag != "latest" else "absent", tag, None if tag and tag != "latest" else "no tag or :latest", e)
    else:
        c["image_pinned"] = _res("unknown", None, "image is a template or Helm value", at(r"image:"))
    return c


def nomad_checks(app, repo, f, lines):
    text = "\n".join(lines)

    def at(rx):
        i = _first(lines, rx)
        return ev(f, i, lines, app) if i else None
    c = {}
    m = re.search(r"^\s*count\s*=\s*(\d+)", text, re.M)
    c["replicas"] = _res("present" if m and int(m.group(1)) >= 2 else "absent", int(m.group(1)) if m else None, None if m and int(m.group(1)) >= 2 else "count is 1 or not set (default 1)", at(r"^\s*count\s*="))
    sp = at(r"^\s*(?:spread|affinity)\s*\{") or at(r"distinct_hosts|distinct_property")
    c["anti_affinity"] = _res("present", None, None, sp) if sp else _res("absent", None, "no spread, affinity or distinct_hosts constraint", None)
    zone = at(r"\$\{(?:attr\.platform\.aws\.placement\.availability-zone|node\.datacenter)\}")
    c["zone_spread"] = _res("present", None, None, zone) if zone else _res("absent", None, "no spread over datacenter / availability zone", None)
    chk = at(r"^\s*check\s*\{")
    c["readiness"] = _res("present", None, "service check", chk) if chk else _res("absent", None, "no service check", None)
    upd = at(r"^\s*update\s*\{")
    hc = at(r"health_check\s*=") or at(r"min_healthy_time") or at(r"max_parallel")
    c["rollout"] = _res("present", None, None, upd or hc) if (upd or hc) else _res("absent", None, "no update block (all allocations are replaced together per default)", None)
    kt = at(r"kill_timeout\s*=") or at(r"shutdown_delay\s*=")
    c["graceful_stop"] = _res("present", None, None, kt) if kt else _res("absent", None, "no kill_timeout / shutdown_delay", None)
    rs = at(r"^\s*resources\s*\{")
    c["resources"] = _res("present", None, None, rs) if rs else _res("absent", None, "no resources block", None)
    rec = at(r"auto_revert\s*=\s*true") or at(r"^\s*reschedule\s*\{") or at(r"^\s*restart\s*\{")
    c["restart_recovery"] = _res("present", None, None, rec) if rec else _res("absent", None, "no restart, reschedule or auto_revert", None)
    im = re.search(r"image\s*=\s*[\"']([^\"']+)", text)
    if im:
        tag = im.group(1).rsplit(":", 1)[1] if ":" in im.group(1).split("/")[-1] else None
        c["image_pinned"] = _res("present" if tag and tag != "latest" else "absent", tag, None if tag and tag != "latest" else "no tag or :latest", at(r"image\s*="))
    else:
        c["image_pinned"] = _res("unknown", None, "image not literal", None)
    return c


def compose_checks(app, repo, f, lines, svc_start, svc_lines):
    def at(rx):
        i = _first(svc_lines, rx)
        return ev(f, svc_start + i, lines, app) if i else None
    text = "\n".join(svc_lines)
    c = {}
    m = re.search(r"replicas:\s*(\d+)", text)
    c["replicas"] = _res("present" if m and int(m.group(1)) >= 2 else "absent", int(m.group(1)) if m else None, None if m else "one container per service", at(r"replicas:"))
    hc = at(r"healthcheck:")
    c["readiness"] = _res("present", None, None, hc) if hc else _res("absent", None, "no healthcheck", None)
    rp = at(r"restart:") or at(r"restart_policy:")
    c["restart_recovery"] = _res("present", None, None, rp) if rp else _res("absent", None, "no restart policy", None)
    rs = at(r"(?:mem_limit|cpus|limits):")
    c["resources"] = _res("present", None, None, rs) if rs else _res("absent", None, "no limits", None)
    im = re.search(r"image:\s*[\"']?([^\s\"']+)", text)
    if im:
        tag = im.group(1).rsplit(":", 1)[1] if ":" in im.group(1).split("/")[-1] else None
        c["image_pinned"] = _res("present" if tag and tag != "latest" else "absent", tag, None, at(r"image:"))
    return c


def assess(repo: str, disc: Optional[dict] = None) -> dict:
    ctx = Ctx(repo)
    app = (disc or {}).get("identity", {}).get("app_id", {}).get("value") or os.path.basename(os.path.abspath(repo))
    files = [f for f in ctx.files if not ctx._aux(f) and not ctx._test_module(f)]
    deploy = [f for f in ctx.deploy_files]
    nomad = [f for f in files if re.search(r"\.(nomad|hcl)$", f)]
    nomad = [f for f in nomad if any(re.search(r'^\s*job\s+"', l) for l in (evidence.read_lines(repo, f) or [])[:80])]
    k8s_files = sorted(f for f in deploy if f.endswith((".yml", ".yaml")) and not re.match(r"(?i)(?:docker-)?compose|values|Chart\.", os.path.basename(f)))
    compose = sorted(f for f in deploy if re.match(r"(?i)(?:docker-)?compose[^/]*\.ya?ml$", os.path.basename(f)))
    # EKS / cloud hints anywhere in infra-ish files
    eks_ev = []
    for f in sorted(set(k8s_files + deploy + [x for x in files if x.endswith((".tf", ".yaml", ".yml", ".json")) and re.search(r"(?i)eks|terraform|infra|cluster|deploy|helm|chart", x)])):
        lines = evidence.read_lines(repo, f) or []
        i = _first(lines, EKS_HINT.pattern)
        if i and len(eks_ev) < 3:
            eks_ev.append(ev(f, i, lines, app))
    for f in ctx.ci_files:
        lines = evidence.read_lines(repo, f) or []
        i = _first(lines, r"aws\s+eks\s+update-kubeconfig|\beksctl\b")
        if i and len(eks_ev) < 3:
            eks_ev.append(ev(f, i, lines, app))
    eks = bool(eks_ev)
    # repository-wide kinds
    siblings: Dict[str, dict] = {}
    docs = []  # (file, offset, doc, lines)
    chart_dirs = {os.path.dirname(f) for f in ctx.files if os.path.basename(f) == "Chart.yaml"}
    for f in k8s_files:
        lines = evidence.read_lines(repo, f) or []
        for s, d in _docs(lines):
            k = _kind(d) or ("Template" if any("{{" in l for l in d) else None)
            if k in ("PodDisruptionBudget", "HorizontalPodAutoscaler", "ScaledObject"):
                i = _first(d, r"^kind:")
                siblings.setdefault(k, ev(f, s + (i or 1), lines, app))
            docs.append((f, s, d, lines))
    # helm templates that are a single templated doc with `kind:` after {{ if }} lines are handled by _kind scanning all lines
    workloads, platforms = [], []
    for f, s, d, lines in docs:
        k = _kind(d)
        if k not in ("Deployment", "StatefulSet"):
            continue
        chart = next((c for c in sorted(chart_dirs, key=len, reverse=True) if c == "." or f.startswith(c + "/")), None)
        hv = _helm_values(repo, ctx, chart) if chart is not None else {}
        workloads.append({"platform": "kubernetes", "kind": k, "name": _name(d) or "(templated)", "file": f, "helm": chart is not None,
                          "checks": k8s_checks(app, repo, f, s, d, lines, ctx, siblings, hv, eks)})
    for f in nomad:
        lines = evidence.read_lines(repo, f) or []
        jm = next((re.match(r'^\s*job\s+"([^"]+)"', l) for l in lines if re.match(r'^\s*job\s+"([^"]+)"', l)), None)
        workloads.append({"platform": "nomad", "kind": "job", "name": jm.group(1) if jm else f, "file": f, "helm": False, "checks": nomad_checks(app, repo, f, lines)})
    for f in compose:
        lines = evidence.read_lines(repo, f) or []
        svc = [(i, re.match(r"^  ([\w.-]+):\s*$", l).group(1)) for i, l in enumerate(lines) if re.match(r"^  ([\w.-]+):\s*$", l)]
        in_services = False
        for i, name in svc:
            above = [l for l in lines[:i] if re.match(r"^\S", l)]
            if not above or not above[-1].startswith("services:"):
                continue
            nxt = next((j for j, n in svc if j > i), len(lines))
            body = lines[i + 1:nxt]
            if any(re.search(r"^\s+(?:image|build):", l) for l in body):
                workloads.append({"platform": "compose", "kind": "service", "name": name, "file": f, "helm": False, "checks": compose_checks(app, repo, f, lines, i + 1, body)})
    for p in ("kubernetes", "nomad", "compose"):
        if any(w["platform"] == p for w in workloads):
            platforms.append(p)
    # summary
    summary = []
    for cid, grp, title, why in CHECKS:
        rel = [w for w in workloads if cid in w["checks"] and cid in APPLIES[w["platform"]]]
        if not rel:
            summary.append({"id": cid, "group": grp, "title": title, "why": why, "state": "not_applicable" if workloads else "not_assessed", "workloads": 0, "evidence": []})
            continue
        states = [w["checks"][cid]["state"] for w in rel]
        agg = "present" if all(s == "present" for s in states) else "absent" if all(s in ("absent",) for s in states) else "default" if all(s in ("default", "present") for s in states) and "default" in states else "partial" if "present" in states else "unknown" if "unknown" in states and "absent" not in states else "absent"
        ev_list = [e for w in rel for e in w["checks"][cid]["evidence"]][:2]
        summary.append({"id": cid, "group": grp, "title": title, "why": why, "state": agg, "workloads": len(rel), "evidence": ev_list,
                        "notes": sorted({w["checks"][cid]["note"] for w in rel if w["checks"][cid]["note"]})[:2]})
    if "kubernetes" not in platforms:
        eks, eks_ev = False, []
    state = "not_assessed" if not workloads else "assessed"
    limitations = ["Only deployment descriptors in this repository were read. Platform or GitOps repositories, cluster policy, admission controllers and cloud settings can add what is absent here.",
                   "`absent` means 'not in these files', never 'not in production'.",
                   "Helm charts are not rendered: a value that comes from a template or an unread values file is `unknown`.",
                   "A PodDisruptionBudget or autoscaler is matched to the repository, not to a specific workload selector.",
                   "Nothing was applied or queried; no cluster was contacted."]
    return {"contract": CONTRACT, "version": VERSION, "application": app, "state": state, "platforms": platforms,
            "eks": {"detected": eks, "evidence": eks_ev, "note": "EKS signals: eks.amazonaws.com annotations, eksctl, aws_eks Terraform, ALB / Karpenter / EBS CSI annotations" if eks else "no EKS-specific signal found; generic Kubernetes checks apply"},
            "workloads": workloads, "summary": summary, "groups": GROUPS,
            "reason": None if workloads else "no Kubernetes, Nomad or Compose workload definition in this repository: HA configuration may live in a platform or GitOps repository",
            "limitations": limitations}
