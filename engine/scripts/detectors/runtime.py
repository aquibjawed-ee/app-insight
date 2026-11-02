"""Runtime resilience read from application configuration and main source code: HTTP client timeouts, retries and circuit
breakers, message-consumer error handling, database timeouts, graceful shutdown and structured logging.

Every fact's value is a verdict {state, summary, level}: state is PRESENT / PARTIAL / ABSENT / ISSUE / UNKNOWN /
NOT_APPLICABLE, decided here from the lines cited, so the product only maps it. Nothing is run; a setting supplied by the
platform or the environment at deploy time is not visible and the summary says so where it matters."""
from __future__ import annotations

import os
import re

from evidence import COMMENT_PREFIXES, fact, file_ev, grep_files, read_lines


VERSION = "0.1.0"

NOT_CODE = r"^(?!\s*(?:import|package)\b)"
# a timeout of 0 / -1 means "wait forever" for almost every client and pool
DISABLED = re.compile(r"^[\"']?(?:\$\{[\w.-]+:)?(?:0+|-1)(?:ms|s)?\}?[\"']?$", re.I)

HTTP_CLIENTS = [  # (name, pattern, finite default or None)
    ("RestTemplate", r"\bnew RestTemplate\s*\(|\bRestTemplateBuilder\b", None),
    ("RestClient", r"\bRestClient\.(?:builder|create)\s*\(", None),
    ("WebClient", r"\bWebClient\.(?:builder|create)\s*\(", None),
    ("JDK HttpClient", r"\bHttpClient\.new(?:Builder|HttpClient)\s*\(", None),
    ("Apache HttpClient", r"\bHttpClients\.(?:custom|createDefault|createSystem)\s*\(|\bHttpClientBuilder\.create\s*\(", None),
    ("JAX-RS client", r"\bClientBuilder\.new(?:Builder|Client)\s*\(", None),
    ("OkHttp", r"\bnew OkHttpClient\b|\bOkHttpClient\.Builder\s*\(", "10 s"),
    ("Retrofit", r"\bRetrofit\.Builder\s*\(", "10 s (OkHttp)"),
    ("Feign", r"@FeignClient\b", "10 s connect / 60 s read"),
    ("Feign builder", r"\b(?:Hystrix)?Feign\.builder\s*\(", "10 s connect / 60 s read"),
    ("HTTP client from a library", r"\bnew\s+(?!RestTemplate\b)\w*(?:Http|Rest)\w*Client\s*\(", None),
    ("MicroProfile REST client", r"@RegisterRestClient\b", "implementation default"),
    # AWS SDK clients call AWS over HTTP: v2 defaults to 2 s connect / 30 s socket with no overall call timeout; v1 to 10 s / 50 s
    ("AWS SDK v2", r"\b(?!(?:Rest|Web|Http|OkHttp|Feign|Jersey|Vertx|Ktor)Client\b)[A-Z][A-Za-z0-9]*(?:Async)?Client\.(?:builder|create)\s*\(", "2 s connect / 30 s socket, no overall call timeout"),
    ("AWS SDK v1", r"\bAmazon[A-Za-z0-9]*ClientBuilder\.(?:standard|defaultClient)\s*\(", "10 s connect / 50 s socket"),
]
AWS_SDK = r"software\.amazon\.awssdk|com\.amazonaws"
HTTP_TIMEOUT_CODE = (r"\.(?:connect|read|write|call|response|socket|connectionRequest|request|connection|apiCall|apiCallAttempt)Timeout\s*\(|"
                     r"\bwith(?:ClientExecution|Request|Socket|Connection)Timeout\s*\(|"
                     r"\.options\s*\(\s*new\s+(?:feign\.)?Request\.Options|\bnew\s+\w*(?:Http|Rest)\w*Client\s*\([^)]*(?i:timeout)|"
                     r"\bset(?:Connect|Read|Socket|ConnectionRequest|Response)Timeout\s*\(|\b(?:Read|Write)TimeoutHandler\b|"
                     r"\bCONNECT_TIMEOUT_MILLIS\b|\.timeout\s*\(\s*Duration")
NOT_HTTP = re.compile(r"datasource|jpa|hibernate|persistence|kafka|rabbit|jms|activemq|artemis|redis|mongo|r2dbc|jdbc|cassandra|"
                      r"ldap|mail|session|cloud\.stream|lifecycle|transaction|shutdown|hikari|server\.|management\.")

BREAKER_CODE = r"\bHystrixFeign\.builder\s*\(|@CircuitBreaker\b|@HystrixCommand\b|\bextends\s+Hystrix(?:Observable)?Command\b|@Bulkhead\b|\bCircuitBreaker\.of(?:Defaults)?\s*\(|\bCircuitBreakerFactory\b|\bCircuitBreakerRegistry\b"
RETRY_CODE = (r"@Retryable\b|@Retry\b|\bRetryTemplate\b|\bRetry\.of(?:Defaults)?\s*\(|\bRetryRegistry\b|\bFailsafe\.with\s*\(|"
              r"\.retryWhen\s*\(|\bRetry\.(?:backoff|fixedDelay|max)\s*\(")

KAFKA_IN = r"@KafkaListener\b|\bKafkaConsumer\s*<|@StreamListener\b|\bReactiveKafkaConsumerTemplate\b|\bKafkaMessageListenerContainer\b|@Incoming\b"
RABBIT_IN = r"@RabbitListener\b|\bSimpleMessageListenerContainer\b"
JMS_IN = r"@JmsListener\b|\bimplements\s+(?:\w+\s*,\s*)*MessageListener\b|\bDefaultMessageListenerContainer\b"
SQS_IN = r"(?-i:@SqsListener)\b|\bReceiveMessageRequest\b"  # the exact annotation: a class named SQSListener is not one
DEAD_CODE = (r"\bDeadLetterPublishingRecoverer\b|@RetryableTopic\b|@DltHandler\b|\bRepublishMessageRecoverer\b|"
             r"\bRejectAndDontRequeueRecoverer\b|x-dead-letter-exchange|\bdeadLetterExchange\b|\bdeadLetterTargetArn\b|\bredrivePolicy\b|"
             r"[\"'][\w.-]*(?:\.dlt|\.dlq|-dlt|-dlq|_dlq|_dlt|dead[-_.]?letter)[\w.-]*[\"']")
MSG_RETRY_CODE = (r"\bDefaultErrorHandler\b|\bSeekToCurrentErrorHandler\b|\bCommonErrorHandler\b|\bsetCommonErrorHandler\s*\(|"
                  r"\bsetErrorHandler\s*\(|\bErrorHandlingDeserializer\b|\bRedeliveryPolicy\b|\bRetryInterceptorBuilder\b")
MSG_KEY = re.compile(r"kafka|rabbit|cloud\.stream|jms|activemq|artemis|amqp|sqs|messaging")

DB_TIMEOUT_CODE = (r"@Transactional\s*\([^)]*\btimeout\s*=|\bsetQueryTimeout\s*\(|\bQueryHints\.(?:SPEC_)?TIMEOUT\b|"
                   r"(?:jakarta|javax)\.persistence\.query\.timeout|org\.hibernate\.timeout")
DS_CODE = r"\bDataSourceBuilder\b|\bnew HikariConfig\b|\bnew HikariDataSource\b"
MEMORY_DB = re.compile(r"jdbc:(?:h2:mem|hsqldb:mem|derby:memory)|r2dbc:h2:mem", re.I)
DB_KEY = re.compile(r"^(?:spring\.datasource|spring\.r2dbc|quarkus\.datasource|datasources?\.)")
DB_TIMEOUT_KEY = re.compile(r"(?:query|statement|socket)timeout|transaction\w*\.\w*timeout|defaulttimeout|persistence\.query\.timeout|hibernate\.timeout")
DB_TIMEOUT_URL = re.compile(r"socketTimeout=|queryTimeout=|statement_timeout|oracle\.jdbc\.ReadTimeout|readTimeout=", re.I)
POOL_KEY = re.compile(r"maximumpoolsize|\.maxsize$|maxactive|maxwait|connectiontimeout|acquisitiontimeout|maxlifetime|minimumidle|"
                      r"idletimeout|validationtimeout|\.pool\.")

JSON_LOG = (r"\bLogstashEncoder\b|\bLoggingEventCompositeJsonEncoder\b|\bJsonEncoder\b|\bJsonLayout\b|\bJsonTemplateLayout\b|"
            r"\bEcsLayout\b|\bEcsEncoder\b|logback\.contrib\.json|\bStructuredLogEncoder\b")
JSON_LOG_DEP = r"logstash-logback-encoder|quarkus-logging-json|log4j-layout-template-json|ecs-logging|logback-json"


def norm(key: str) -> str:
    """Spring's relaxed binding: read-timeout, readTimeout, read_timeout and READ_TIMEOUT are the same key."""
    return re.sub(r"[-_\"'\[\]]", "", key.lower())


def settings(ctx) -> list:
    """Every leaf setting in application*.properties / *.yml under src/main, with its full dotted key and the line it is on."""
    out = []
    for f in ctx.props:
        lines = read_lines(ctx.repo, f) or []
        if f.endswith(".properties"):
            for i, ln in enumerate(lines, 1):
                s = ln.strip()
                m = re.match(r"([^=:\s]+)\s*[=:]\s*(.*)$", s) if s and s[0] not in "#!" else None
                if m:
                    out.append({"key": m.group(1), "k": norm(m.group(1)), "value": m.group(2).strip(), "ev": file_ev(f, i, ln)})
            continue
        stack = []  # (indent, key) of the open parents
        for i, ln in enumerate(lines, 1):
            if ln.startswith("---"):
                stack = []
                continue
            if not ln.strip() or ln.strip().startswith("#"):
                continue
            m = re.match(r"^(\s*)(-\s+)?([\"']?[\w.\-\[\]/]+[\"']?)\s*:(?:\s+(.*?))?\s*(?:\s#.*)?$", ln)
            if not m:
                continue
            ind = len(m.group(1)) + len(m.group(2) or "")
            key = m.group(3).strip("\"'")
            while stack and stack[-1][0] >= ind:
                stack.pop()
            full = ".".join([k for _, k in stack] + [key])
            val = (m.group(4) or "").strip()
            if val and val not in ("|", ">", "|-", ">-"):
                out.append({"key": full, "k": norm(full), "value": val, "ev": file_ev(f, i, ln)})
            else:
                stack.append((ind, key))
    return out


def _sources(ctx):
    """Main source files read once per repository: (path, whole text, lines). Every code check scans this cache."""
    if not hasattr(ctx, "_runtime_sources"):
        ctx._runtime_sources = [(f, "\n".join(ls), ls) for f in ctx.src_main_java for ls in [read_lines(ctx.repo, f) or []]]
    return ctx._runtime_sources


def _code(ctx, pattern, limit=3):
    """Like grep_files over main code: live lines (not comments, imports or package lines) matching `pattern`, first `limit`."""
    rx, whole, out = re.compile(NOT_CODE + r".*(?:%s)" % pattern, re.I), re.compile(pattern, re.I), []
    for f, text, lines in _sources(ctx):
        if not whole.search(text):  # most files cannot match: skip the line scan
            continue
        for i, ln in enumerate(lines, 1):
            if not ln.strip().startswith(COMMENT_PREFIXES) and rx.search(ln):
                out.append(file_ev(f, i, ln))
                if len(out) >= limit:
                    return out
    return out


def _verdict(state, summary, evidence, level="configured"):
    status = {"ABSENT": "NOT_FOUND", "UNKNOWN": "UNKNOWN", "NOT_APPLICABLE": "NOT_FOUND"}.get(state, "CONFIRMED")
    return fact({"state": state, "summary": summary, "level": level if state in ("PRESENT", "PARTIAL", "ISSUE") else None},
                status, evidence[:5])


def _keys(ss):
    ks = sorted({s["key"] for s in ss})
    return ", ".join(ks[:4]) + (" and %d more" % (len(ks) - 4) if len(ks) > 4 else "")


# settings a framework applies to every client of its kind; a custom key (feignClientReadTimeout) is read by whichever code uses it
GLOBAL_KEY = re.compile(r"^(?:spring\.|feign\.|resilience4j\.|ribbon\.|hystrix\.|okhttp\.|quarkus\.|micronaut\.|mp-rest|server\.)")
HEALTH_CLASS = re.compile(r"(?i)health\w*\.(?:java|kt|groovy|scala)$")


def _outbound(evs):
    """A client inside a health check calls the application itself: it is not an outbound dependency."""
    return [e for e in evs if not HEALTH_CLASS.search(e["path"])]


def http_timeouts(ctx, cfg):
    aws = bool(grep_files(ctx.repo, ctx.build_files, AWS_SDK, 1))
    used = [(n, d, ev) for n, p, d in HTTP_CLIENTS for ev in [_outbound(_code(ctx, p, 3))[:1]] if ev and (aws or not n.startswith("AWS"))]
    keyed = [s for s in cfg if re.search(r"(?:connect|read|response|socket|request|call|write|connection)timeout$", s["k"])
             and not NOT_HTTP.search(s["k"])] + \
        [s for s in cfg if s["k"].startswith("resilience4j.timelimiter.") and s["k"].endswith("timeoutduration")]
    code = _outbound(_code(ctx, HTTP_TIMEOUT_CODE, 8))[:5]
    names = ", ".join(n for n, _, _ in used)
    off = [s for s in keyed if DISABLED.match(s["value"])]
    if off:
        return _verdict("ISSUE", "Timeout disabled (0 or -1 waits forever): %s" % _keys(off), [s["ev"] for s in off])
    if keyed or code:
        # a read / response / call bound, not only a connect or pool-wait (connection request) bound
        texts = [s["k"] for s in keyed] + [e["snippet"].lower() for e in code]
        reads = [t for t in texts if re.search(r"read|response|socket|call|write|request|timelimiter|\.timeout\s*\(", t.replace("connectionrequest", ""))]
        where = (_keys(keyed) + (" and " if keyed and code else "") + ("set in code" if code else "")).strip()
        evs = [s["ev"] for s in keyed] + code
        # timeouts set in code bound only the clients built in the same file; a client built elsewhere with none keeps its default
        coded = {e["path"] for e in code}
        custom = sorted({k["key"].split(".")[-1] for k in keyed if not GLOBAL_KEY.match(k["k"])})
        if custom:  # code that reads a custom timeout setting (@Value("${feignClientReadTimeout}")) applies it
            coded |= {e["path"] for e in _code(ctx, r"\b(?:%s)\b" % "|".join(map(re.escape, custom)), 20)}
        bare = sorted({e["path"] for n, p, d in HTTP_CLIENTS if n in ("Feign builder", "HTTP client from a library", "RestTemplate", "Apache HttpClient", "JDK HttpClient")
                       for e in _outbound(_code(ctx, p, 10)) if e["path"] not in coded}) if coded and not any(GLOBAL_KEY.match(k["k"]) for k in keyed) else []
        # a client wrapped by a breaker command that has an execution timeout is bounded by it (DiscoveryCommand: 5000 ms)
        hx = _code(ctx, r"withExecutionTimeoutInMilliseconds|execution\.isolation\.thread\.timeoutInMilliseconds", 2) + \
            [s["ev"] for s in cfg if re.search(r"hystrix\..*timeoutinmilliseconds$", s["k"])][:1]
        breakers = {e["path"] for e in _code(ctx, BREAKER_CODE, 10)}
        bounded = [b for b in bare if hx and any(re.sub(r"(?:Client)?(?:Configuration|Config|Factory)$", "", os.path.splitext(os.path.basename(b))[0]) in os.path.basename(k) for k in breakers)]
        bare = [b for b in bare if b not in bounded]
        if reads and bounded and not bare:
            return _verdict("PRESENT", "Timeouts set (%s); the client built in %s is bounded by its circuit-breaker command's timeout (%s:%s)" % (
                where, ", ".join(os.path.basename(b) for b in bounded), hx[0]["path"], hx[0]["line_start"]), evs + hx[:1])
        if reads and bare:
            return _verdict("PARTIAL", "Timeouts are set for the clients in %s, but clients built in %s use their library defaults" % (
                ", ".join(sorted({os.path.basename(p) for p in coded})[:3]), ", ".join(os.path.basename(b) for b in bare[:3])), evs)
        if reads:
            return _verdict("PRESENT", "Timeouts set (%s)%s" % (where, "; clients: " + names if names else ""), evs)
        if used and all(d for _, d, _ in used):
            return _verdict("PARTIAL", "Only a connect timeout is set (%s); the read timeout is left at the library default (%s)" %
                            (where, "; ".join("%s %s" % (n, d) for n, d, _ in used)), evs)
        return _verdict("PARTIAL", "Only a connect timeout is set (%s): a dependency that accepts the connection and then stalls "
                        "still holds the calling thread" % where, evs)
    if not used:
        return _verdict("UNKNOWN", "No HTTP client is built in this repository's code (it may come from a shared library) and no "
                        "timeout setting was found; timeouts cannot be read", [])
    bounded = [n for n, d, _ in used if d]
    unbounded = [n for n, d, _ in used if not d]
    evs = [ev[0] for _, _, ev in used]
    if unbounded:
        return _verdict("ABSENT", "No timeout set for %s: these clients wait indefinitely by default" % ", ".join(unbounded), evs)
    return _verdict("PARTIAL", "No timeout set explicitly; library defaults apply (%s)" %
                    "; ".join("%s %s" % (n, d) for n, d, _ in used if d), evs, "declared")


def retries_breakers(ctx, cfg):
    bk = [s for s in cfg if re.match(r"(?:resilience4j\.(?:circuitbreaker|bulkhead)|hystrix\.|spring\.cloud\.circuitbreaker)", s["k"])
          or (re.match(r"(?:spring\.cloud\.openfeign|feign)\.(?:hystrix|circuitbreaker)\.enabled$", s["k"]) and s["value"].lower() == "true")]
    rt = [s for s in cfg if re.match(r"resilience4j\.retry|spring\.cloud\.openfeign\.client\.config\.\w+\.retryer|feign\.client\.config\.\w+\.retryer", s["k"])]
    bc, rc = _code(ctx, BREAKER_CODE), _code(ctx, RETRY_CODE)
    # a breaker in code covers only the clients it wraps: one HystrixCommand does not protect three Feign clients
    if bc and not bk:
        clients = sorted({e["path"] for n, p, _ in HTTP_CLIENTS for e in _outbound(_code(ctx, p, 10))})
        covered = {e["path"] for e in bc}
        # a breaker class elsewhere covers a client configuration it is named after: DiscoveryCommand wraps what DiscoveryConfiguration builds
        stems = {re.sub(r"(?:Client)?(?:Configuration|Config|Factory)$", "", os.path.splitext(os.path.basename(c))[0]): c for c in clients}
        named = {c for stem, c in stems.items() if stem and any(stem in os.path.basename(b) for b in covered)}
        bare = [c for c in clients if c not in covered and c not in named and not grep_files(ctx.repo, [c], BREAKER_CODE, 1)]
        if bare:
            feign = any(grep_files(ctx.repo, [c], r"\bFeign\.builder\s*\(", 1) and not grep_files(ctx.repo, [c], r"\.retryer\s*\(", 1) for c in bare)
            return _verdict("PARTIAL", ("A circuit breaker wraps some calls (%s), but none is visible around the clients built in %s" + (
                " (Feign's default retryer still retries them up to 5 times)" if feign else "")) % (
                ", ".join(sorted({os.path.basename(e["path"]) for e in bc})[:3]), ", ".join(os.path.basename(c) for c in bare[:3])),
                bc[:2] + [e for n, p, _ in HTTP_CLIENTS for e in _code(ctx, p, 10) if e["path"] == bare[0]][:1])
    if bk or bc:
        what = "circuit breaker" + (" and retries" if rt or rc else "")
        return _verdict("PRESENT", "%s configured%s" % (what[0].upper() + what[1:], " (" + _keys(bk + rt) + ")" if bk + rt else " in code"),
                        [s["ev"] for s in bk + rt] + bc + rc)
    if rt or rc:
        return _verdict("PARTIAL", "Retries without a circuit breaker: during an outage every call is retried, adding load to the "
                        "failing dependency", [s["ev"] for s in rt] + rc)
    sdk = _code(ctx, HTTP_CLIENTS[-2][1], 1) or _code(ctx, HTTP_CLIENTS[-1][1], 1)
    if sdk and grep_files(ctx.repo, ctx.build_files, AWS_SDK, 1):
        return _verdict("PARTIAL", "AWS SDK clients retry by default (a few attempts with backoff), but nothing stops calls to a failing "
                        "dependency (no circuit breaker)", sdk, "declared")
    lib = grep_files(ctx.repo, ctx.build_files, r"resilience4j|spring-retry|spring-cloud-starter-circuitbreaker|hystrix|failsafe|smallrye-fault-tolerance", 1)
    return _verdict("ABSENT", "No retry or circuit breaker found in code or configuration" +
                    ("; a resilience library is declared but not used" if lib else ""), lib)


def messaging_errors(ctx, cfg):
    stream_in = [s for s in cfg if re.match(r"spring\.cloud\.stream\.bindings\.[\w.-]*(?:in0|input)", s["k"])]
    consumers = [(n, ev) for n, p in (("Kafka", KAFKA_IN), ("RabbitMQ", RABBIT_IN), ("JMS", JMS_IN), ("SQS", SQS_IN))
                 for ev in [_code(ctx, p, 1)] if ev]
    if stream_in and not any(n == "Kafka" for n, _ in consumers):
        consumers.append(("Spring Cloud Stream", [stream_in[0]["ev"]]))
    if not consumers:
        return _verdict("NOT_APPLICABLE", "No message consumer found (publishes only, or consumers are not in this repository)", [])
    names = ", ".join(n for n, _ in consumers)
    dead_cfg = [s for s in cfg if MSG_KEY.search(s["k"]) and re.search(r"dlq|deadletter|dlt", s["k"])]
    retry_cfg = [s for s in cfg if MSG_KEY.search(s["k"]) and (re.search(r"maxattempts|backoff|retry|redelivery|requeuerejected", s["k"])
                                                               or "ErrorHandlingDeserializer" in s["value"])]
    dead, retry = _code(ctx, DEAD_CODE), _code(ctx, MSG_RETRY_CODE)
    if dead or dead_cfg:
        return _verdict("PRESENT", "%s consumer: failed messages go to a dead-letter destination%s" %
                        (names, " after retries" if retry or retry_cfg else ""), [s["ev"] for s in dead_cfg] + dead + retry)
    if retry or retry_cfg:
        return _verdict("PARTIAL", "%s consumer: retries or an error handler are set, but no dead-letter destination: a message that "
                        "keeps failing is dropped or blocks the queue" % names, [s["ev"] for s in retry_cfg] + retry)
    if {n for n, _ in consumers} == {"SQS"}:
        infra = [f for f in ctx.files if f.endswith((".tf", ".yml", ".yaml", ".json", ".ts")) and not ctx._aux(f) and "src/test" not in f]
        rd = grep_files(ctx.repo, infra, r"redrive|deadLetterTargetArn|dead_letter|maxReceiveCount", 3)
        if rd:
            return _verdict("PRESENT", "SQS consumer: the queue has a redrive (dead-letter) policy", rd)
        return _verdict("UNKNOWN", "SQS consumer: dead-letter handling is a queue setting (redrive policy), normally kept in "
                        "infrastructure code; none is in this repository", [ev[0] for _, ev in consumers])
    return _verdict("ABSENT", "%s consumer with framework defaults only: no error handler, retry policy or dead-letter destination "
                    "found" % names, [ev[0] for _, ev in consumers])


def db_timeouts(ctx, cfg):
    ds = [s for s in cfg if DB_KEY.match(s["k"])]
    dsc = _code(ctx, DS_CODE, 1)
    to = [s for s in cfg if DB_TIMEOUT_KEY.search(s["k"]) and re.search(r"jpa|hibernate|persistence|jdbc|transaction|datasource|r2dbc|mongo", s["k"])]
    to += [s for s in ds if re.search(r"url$", s["k"]) and DB_TIMEOUT_URL.search(s["value"])]
    pool = [s for s in ds if POOL_KEY.search(s["k"])]
    code = _code(ctx, DB_TIMEOUT_CODE)
    off = [s for s in to + pool if re.search(r"timeout", s["k"]) and DISABLED.match(s["value"])]
    if off:
        return _verdict("ISSUE", "Database timeout disabled (0 or -1 waits forever): %s" % _keys(off), [s["ev"] for s in off])
    if to or code:
        return _verdict("PRESENT", "Query or transaction timeout set (%s)%s" % (_keys(to) or "in code", "; pool tuned" if pool else ""),
                        [s["ev"] for s in to] + code + [s["ev"] for s in pool])
    if pool:
        return _verdict("PARTIAL", "Connection pool configured (%s) but no query or transaction timeout: a slow query holds a "
                        "connection until the database gives up" % _keys(pool), [s["ev"] for s in pool])
    urls = [s["value"] for s in ds if s["k"].endswith("url")]
    if urls and all(MEMORY_DB.search(u) for u in urls) and not dsc:
        return _verdict("NOT_APPLICABLE", "In-memory database only (%s): no remote database to time out" % urls[0], [s["ev"] for s in ds[:1]])
    if not ds and not dsc:
        return _verdict("UNKNOWN", "The datasource is not configured in this repository's application files (it may be supplied by "
                        "the platform or the environment); timeouts cannot be read", [])
    return _verdict("ABSENT", "Datasource with pool defaults and no query or transaction timeout", [s["ev"] for s in ds[:1]] + dsc)


def _ver(v):
    return tuple(int(x) for x in re.findall(r"\d+", v or "")[:2]) or None


def graceful_shutdown(ctx, cfg):
    sd = [s for s in cfg if s["k"] == "server.shutdown"]
    phase = [s for s in cfg if s["k"] == "spring.lifecycle.timeoutpershutdownphase"]
    qk = [s for s in cfg if s["k"].startswith("quarkus.shutdown.")]
    if any(s["value"].strip("\"'").lower() == "immediate" for s in sd):
        return _verdict("ISSUE", "server.shutdown=immediate: in-flight requests are cut when an instance stops", [s["ev"] for s in sd])
    if any(s["value"].strip("\"'").lower() == "graceful" for s in sd):
        return _verdict("PRESENT", "server.shutdown=graceful" + (" with a shutdown phase timeout" if phase else ""),
                        [s["ev"] for s in sd + phase])
    if qk:
        return _verdict("PRESENT", "Quarkus shutdown timeout set (%s)" % _keys(qk), [s["ev"] for s in qk])
    stack = (getattr(ctx, "doc", None) or {}).get("stack") or {}
    sbf = stack.get("spring_boot_version") or {}
    boot = _ver(sbf.get("value"))
    if boot:
        if boot >= (3, 4):
            return _verdict("PRESENT", "server.shutdown not set: graceful by default since Spring Boot 3.4 (this is %s)" % sbf["value"],
                            (sbf.get("evidence") or [])[:1], "declared")
        if boot < (2, 3):
            return _verdict("ABSENT", "Spring Boot %s has no graceful shutdown setting (server.shutdown arrived in 2.3): the web server stops "
                            "immediately, cutting in-flight requests" % sbf["value"], (sbf.get("evidence") or [])[:1])
        return _verdict("ABSENT", "server.shutdown not set: before Spring Boot 3.4 (this is %s) the web server stops immediately, "
                        "cutting in-flight requests" % sbf["value"], (sbf.get("evidence") or [])[:1])
    quarkus = grep_files(ctx.repo, ctx.build_files, r"io\.quarkus", 1)
    if quarkus:
        return _verdict("ABSENT", "quarkus.shutdown.timeout not set: Quarkus stops without a drain period", quarkus)
    return _verdict("UNKNOWN", "No framework shutdown setting recognised (Spring Boot and Quarkus are read)", [])


def structured_logging(ctx, cfg):
    conf = [f for f in ctx.files if re.search(r"(^|/)(?:logback|log4j2)[^/]*\.xml$", f) and "src/test" not in f and not ctx._aux(f)]
    enc = grep_files(ctx.repo, conf, JSON_LOG, 2)
    keys = [s for s in cfg if re.match(r"logging\.structured\.format\.|quarkus\.log\.(?:console|file)\.json", s["k"])
            and s["value"].strip("\"'").lower() not in ("false", "")]
    if enc or keys:
        return _verdict("PRESENT", "Logs are written as JSON (%s)" % (_keys(keys) or "encoder in " + enc[0]["path"]), [s["ev"] for s in keys] + enc)
    dep = grep_files(ctx.repo, ctx.build_files, JSON_LOG_DEP, 1)
    if dep:
        return _verdict("PARTIAL", "A JSON logging library is declared but no logging configuration uses it", dep, "declared")
    return _verdict("ABSENT", "Plain-text logs: no JSON encoder or structured logging setting found", [])


SERVICE_URL_KEY = re.compile(r"(?:url|uri|baseurl|endpoint|address)$")
METRICS_KEY = re.compile(r"^management\.(?:metrics\.|prometheus\.|[\w-]+\.metrics\.export\.)|(?:^|\.)(?:mmv|pcp|parfait)[\w-]*(?:\.|$)|rootmetric")
METRICS_CODE = r"\bPcpMonitorBridge\b|\bMonitoringView\b|\bPrometheusMeterRegistry\b|\bMeterRegistry\b|@Timed\b|\bMetricRegistry\b"
OPEN_ALL = r"\.anyRequest\(\)\s*\.authenticated\(\)|\.anyExchange\(\)\s*\.authenticated\(\)"
OPEN_HEALTH = r"EndpointRequest\.to(?:AnyEndpoint)?\(|/actuator|/health|HealthEndpoint"


def service_urls(ctx, cfg):
    """Other services this application is configured to call: URL-valued settings that are not a database, broker or own server."""
    hits, seen = [], set()
    for st in cfg:  # one entry per key: the same URL in several profile files is one service
        if SERVICE_URL_KEY.search(st["k"]) and not NOT_HTTP.search(st["k"]) and not re.search(r"hazelcast|cluster|network|discovery\.client", st["k"]) \
                and re.match(r"(?i)\s*https?://", st["value"]) and st["k"] not in seen:
            seen.add(st["k"])
            hits.append(st)
    return fact([{"key": h["key"], "value": h["value"], "at": "%s:%s" % (h["ev"]["path"], h["ev"]["line_start"])} for h in hits],
                "CONFIRMED" if hits else "NOT_FOUND", [h["ev"] for h in hits][:12],
                "URL-valued settings naming another service")


def metrics_export(ctx, cfg):
    """Configuration or code that publishes metrics: the exposure of a metrics endpoint, an export setting, or a registry wired in code."""
    keyed = [s for s in cfg if METRICS_KEY.search(s["k"]) or (s["k"] == "management.endpoints.web.exposure.include" and re.search(r"prometheus|metrics|\*", s["value"]))]
    code = _code(ctx, METRICS_CODE, 2)
    evs = [s["ev"] for s in keyed][:3] + code
    return fact(bool(evs), "CONFIRMED" if evs else "NOT_FOUND", evs, "metrics export configured in settings or code" if evs else None)


def health(ctx, cfg):
    """A health endpoint or health check, and whether the security configuration lets an unauthenticated probe reach it."""
    hf = ((getattr(ctx, "doc", None) or {}).get("resilience") or {}).get("health_endpoint") or {}
    if not hf.get("value"):
        return _verdict("ABSENT", "No health endpoint or health check found (Actuator, MicroProfile Health, Micronaut management, Dropwizard health checks)", [])
    ev = hf.get("evidence") or []
    lock = _code(ctx, OPEN_ALL, 1)
    if lock and not grep_files(ctx.repo, [lock[0]["path"]], OPEN_HEALTH, 1):
        return _verdict("PARTIAL", "A health endpoint exists, but the security configuration requires authentication for every request it does not "
                        "list, and it does not open the health endpoint: an unauthenticated probe is refused (401 or 403)", ev[:1] + lock)
    where = "%s:%s" % (ev[0]["path"], ev[0]["line_start"]) if ev else "the build"
    return _verdict("PRESENT", "Health endpoint or check found (%s)" % where, ev[:2])


def detect(ctx) -> dict:
    cfg = settings(ctx)
    return {"health": health(ctx, cfg), "service_urls": service_urls(ctx, cfg), "metrics_export": metrics_export(ctx, cfg),
            "http_timeouts": http_timeouts(ctx, cfg), "retries_breakers": retries_breakers(ctx, cfg),
            "messaging_errors": messaging_errors(ctx, cfg), "db_timeouts": db_timeouts(ctx, cfg),
            "graceful_shutdown": graceful_shutdown(ctx, cfg), "structured_logging": structured_logging(ctx, cfg)}
