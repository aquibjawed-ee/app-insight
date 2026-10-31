"""Messaging adapter: Kafka, RabbitMQ, JMS and SQS publishers/consumers from source annotations, template calls and Spring Cloud
Stream bindings. A topic is named only when its name is a literal, a resolvable property or a unique constant; otherwise the edge
stays unresolved. A broker dependency alone is never a publisher or consumer."""
from __future__ import annotations

import re
from typing import Dict, List

import evidence
from detectors import integrations as I
from graph.model import Graph, sid
from graph.adapters.common import Config, annotation_text, ev, mask_comments, resolve_arg, string_literals
from graph.adapters.http import _args, _kv

# (annotation regex, family, argument keys naming the destination)
LISTENERS = [(re.compile(r"@KafkaListener\b"), "kafka", ("topics", "topicPattern")),
             (re.compile(r"@RabbitListener\b"), "rabbitmq", ("queues",)),
             (re.compile(r"@JmsListener\b"), "jms", ("destination",)),
             (re.compile(r"@SqsListener\b"), "sqs", ("queueNames", "value"))]
# (call regex, family); the destination is the first argument (RabbitMQ: exchange first, routing key second)
TEMPLATE_TYPES = {"kafka": r"Kafka(?:Template|Operations)", "rabbitmq": r"(?:Rabbit|Amqp)Template|RabbitOperations", "jms": r"Jms(?:Template|MessagingTemplate)|JmsOperations",
                  "sqs": r"SqsTemplate|QueueMessagingTemplate"}
SEND_CALL = {"kafka": r"(?:send|sendDefault)", "rabbitmq": r"(?:convertAndSend|send)", "jms": r"(?:convertAndSend|send)", "sqs": r"send"}


def senders_in(text: str):
    """(compiled regex, family) for each messaging template variable DECLARED in this file (Java `KafkaTemplate<K,V> t`, Kotlin `t: KafkaTemplate<K,V>`).
    A call is a publication only on a variable declared with a messaging template type: `x.send(...)` on anything else is not."""
    out = []
    for fam, ty in TEMPLATE_TYPES.items():
        names = set(re.findall(r"(?:%s)\s*(?:<[^;(){}=]*?>)?\s+(\w+)\s*[;,)=]" % ty, text)) | set(re.findall(r"(\w+)\s*:\s*(?:%s)\b" % ty, text))
        for n in sorted(names):
            out.append((re.compile(r"\b%s\s*\.\s*%s\s*\(" % (re.escape(n), SEND_CALL[fam])), fam))
    if re.search(r"\bProducerRecord\b", text):
        out.append((re.compile(r"\bProducerRecord\s*(?:<[^>]*>)?\s*\("), "kafka"))
    return out
FAMILY_TECH = {"kafka": ("Kafka",), "rabbitmq": ("RabbitMQ",), "jms": ("ActiveMQ / Artemis", "IBM MQ", "JMS broker (not identified)"), "sqs": ("AWS SQS",)}
CLUSTER_KEYS = {"kafka": ("spring.kafka.bootstrap-servers", "kafka.bootstrap.servers", "spring.kafka.producer.bootstrap-servers",
                          "spring.kafka.consumer.bootstrap-servers"),
                "rabbitmq": ("spring.rabbitmq.host", "spring.rabbitmq.addresses"),
                "jms": ("spring.activemq.broker-url", "spring.artemis.broker-url"),
                "sqs": ("spring.cloud.aws.sqs.endpoint",)}


def cluster_hints(cfg: Config, family: str) -> List[str]:
    out = []
    for k in CLUSTER_KEYS.get(family, ()):
        v, _, _ = cfg.get(k)
        if v and "${" not in v:
            for h in re.split(r"[,\s]+", re.sub(r"^\w+://", "", v)):
                h = h.strip().lower()
                if h and h not in out:
                    out.append(h)
    return sorted(out)


def _topic(g: Graph, family: str, name: str, cfg: Config, **attrs):
    nid = "topic:%s:%s" % (family, name)
    g.node(nid, "Topic", name, dict({"broker_family": family, "cluster_hints": cluster_hints(cfg, family)}, **attrs), app=None)
    return nid


def _unresolved_topic(g, family, what, reason, e):
    nid = "unresolved:topic:%s:%s" % (family, sid(what, e["path"], str(e["line_start"])))
    g.node(nid, "Topic", "unresolved %s destination" % family, {"broker_family": family, "unresolved": True, "reason": reason, "expression": what}, [e])
    return nid


def _link_broker(g: Graph, app: str, topic_node: str, family: str, ev_list):
    """A topic lives on a broker: connect it to this application's broker node when the application declares one."""
    for nid, n in g.nodes.items():
        if n["type"] == "MessageBroker" and n["attrs"].get("family") == family and n["app"] == app:
            g.edge("DEPENDS_ON", topic_node, nid, "configuration", "inferred", "low", ev_list[:1],
                   attrs={"role": "topic hosted on broker", "reasoning": "this application declares one %s broker; the topic is used by this application" % family})
            return


def _edge(g, app, app_node, etype, tnode, family, e, mech, conf, attrs, unresolved_reason=None):
    if unresolved_reason or g.nodes[tnode]["attrs"].get("unresolved"):
        g.edge(etype, app_node, tnode, mech, "unresolved", "low", [e], {"state": "unresolved", "reason": unresolved_reason or g.nodes[tnode]["attrs"]["reason"]}, attrs)
    else:
        g.edge(etype, app_node, tnode, mech, "static_configured", conf, [e], {"state": "resolved"}, attrs)
        _link_broker(g, app, tnode, family, [e])


def source_messaging(ctx, g: Graph, app: str, app_node: str, cfg: Config, consts):
    r = ctx.repo
    for f in ctx.src_main_java:
        lines = evidence.read_lines(r, f) or []
        masked = mask_comments(lines)
        text = "\n".join(masked)
        if not re.search(r"Listener|Template|Operations|ProducerRecord|SendTo", text):
            continue
        module = ctx.module_of(f)
        SENDERS = senders_in(text)
        for i, ln in enumerate(masked):
            e = None
            for rx, family, keys in LISTENERS:
                if rx.search(ln):
                    e = ev(f, i + 1, lines, app)
                    a = _args(annotation_text(masked, i), rx.pattern.replace("\\b", ""))
                    raw = _kv(a, *keys, arrays=True) or (a.strip().split(",")[0] if a.strip().startswith(('"', "{", "[")) else None)
                    if not raw:
                        g.skip("listener at %s:%d" % (f, i + 1), "no destination named in the annotation", [e])
                        break
                    pattern = bool(re.search(r"topicPattern", a))
                    for it in (raw[1:-1].split(",") if raw[:1] in "{[" else [raw]):
                        it = it.strip()
                        if not it:
                            continue
                        v, ee, how, why = resolve_arg(it, cfg, consts, f)
                        if v is None or pattern:
                            tn = _unresolved_topic(g, family, it, why or "topic pattern: the set of topics it matches is not enumerable", e)
                            _edge(g, app, app_node, "CONSUMES_FROM", tn, family, e, "source_annotation", "low", {"module": module, "how": how})
                        else:
                            tn = _topic(g, family, v, cfg)
                            ev_list = [e] + ([ee] if ee else [])
                            _edge(g, app, app_node, "CONSUMES_FROM", tn, family, e, "source_annotation", "high" if how == "literal" else "medium",
                                  {"module": module, "how": how, "listener_class": _enclosing(masked, i)})
                            if ee:
                                g.edges[[k for k in g.edges if g.edges[k]["target"] == tn and g.edges[k]["source"] == app_node][-1]]["evidence"] = ev_list
                    break
            for rx, family in SENDERS:
                m = rx.search(ln)
                if not m:
                    continue
                e = ev(f, i + 1, lines, app)
                txt = ln[m.end():]
                # first argument, until a top-level comma
                depth, buf = 0, ""
                for ch in txt:
                    if ch in "([{":
                        depth += 1
                    elif ch in ")]}":
                        if depth == 0:
                            break
                        depth -= 1
                    if ch == "," and depth == 0:
                        break
                    buf += ch
                first = buf.strip()
                if rx.pattern.startswith(r"\bProducerRecord") and re.match(r"<", first):
                    first = first.lstrip("<>").strip()
                if not first:
                    g.skip("send at %s:%d" % (f, i + 1), "argument is on a following line; not read", [e])
                    break
                v, ee, how, why = resolve_arg(first, cfg, consts, f)
                if v is None:
                    tn = _unresolved_topic(g, family, first, why, e)
                    _edge(g, app, app_node, "PUBLISHES_TO", tn, family, e, "source_call", "low", {"module": module, "how": how})
                else:
                    tn = _topic(g, family, v, cfg)
                    conf = "high" if how == "literal" else "medium"
                    _edge(g, app, app_node, "PUBLISHES_TO", tn, family, e, "source_call", conf, {"module": module, "how": how})
                break
            m = re.search(r"@SendTo\s*\(\s*\"([^\"$]+)\"", ln)
            if m:
                e = ev(f, i + 1, lines, app)
                fam = _family_of_app(g, app) or "kafka"
                tn = _topic(g, fam, m.group(1), cfg)
                _edge(g, app, app_node, "PUBLISHES_TO", tn, fam, e, "source_annotation", "medium", {"module": module, "family_assumed_from_broker": True})


def _enclosing(masked, i):
    for j in range(i, -1, -1):
        m = re.search(r"\bclass\s+(\w+)", masked[j])
        if m:
            return m.group(1)
    return None


def _family_of_app(g, app):
    fams = {n["attrs"].get("family") for n in g.nodes.values() if n["type"] == "MessageBroker" and n["app"] == app}
    return fams.pop() if len(fams) == 1 else None


def stream_bindings(ctx, g: Graph, app: str, app_node: str, cfg: Config):
    """Spring Cloud Stream functional bindings: `<name>-in-<n>` consumes, `<name>-out-<n>` publishes; the destination is the topic."""
    binder = {n["attrs"].get("family") for n in g.nodes.values() if n["type"] == "MessageBroker" and n["app"] == app}
    for key, hits in sorted(cfg.values.items()):
        m = re.match(r"spring\.cloud\.stream\.bindings\.([\w-]+?)-(in|out)-(\d+)\.destination$", key)
        if not m:
            continue
        val, e, why = cfg.get(key)
        if not val or "${" in val:
            continue
        family = next(iter(binder)) if len(binder) == 1 else None
        if family is None:
            g.skip("binding %s" % key, "which broker the binder uses is not known from this application's declared brokers", [hits[0][1]])
            continue
        tn = _topic(g, family, val, cfg)
        etype = "CONSUMES_FROM" if m.group(2) == "in" else "PUBLISHES_TO"
        _edge(g, app, app_node, etype, tn, family, e, "configuration", "medium", {"binding": m.group(1) + "-" + m.group(2) + "-" + m.group(3), "framework": "spring-cloud-stream"})
