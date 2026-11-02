"""Runtime resilience read from configuration and main code: each check decides PRESENT / PARTIAL / ABSENT / ISSUE / UNKNOWN from
the lines it cites, a disabled timeout is an issue, library defaults are not a configured timeout, and evidence re-verifies."""
import os
import sys
import tempfile
import unittest

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(HERE, "..", "scripts"))
sys.path.insert(1, HERE)
os.environ["DISCOVERY_FIXED_TIME"] = "2026-01-01T00:00:00Z"

import graph_fixtures as F  # noqa: E402
import discover  # noqa: E402
import evidence  # noqa: E402
from detectors import Ctx, runtime  # noqa: E402

J = "src/main/java/com/acme/"
POM_32 = F.pom("svc", "3.2.4", "17", [F.dep("spring-boot-starter-web")])
POM_34 = F.pom("svc", "3.4.1", "21", [F.dep("spring-boot-starter-web"), F.dep("logstash-logback-encoder", "net.logstash.logback")])

GOOD = {
    "pom.xml": POM_32,
    "src/main/resources/application.yml": """spring:
  datasource:
    url: jdbc:postgresql://db:5432/orders
    hikari:
      maximum-pool-size: 20
  transaction:
    default-timeout: 30s
  kafka:
    listener:
      ack-mode: record
  http:
    client:
      connect-timeout: 2s
      read-timeout: 5s
server:
  shutdown: graceful
spring.lifecycle.timeout-per-shutdown-phase: 20s
resilience4j:
  circuitbreaker:
    instances:
      payments:
        failure-rate-threshold: 50
logging:
  structured:
    format:
      console: ecs
""",
    J + "Client.java": "package com.acme;\nimport org.springframework.web.client.RestClient;\nclass Client {\n  RestClient c = RestClient.builder().build();\n}\n",
    J + "Listener.java": """package com.acme;
class Listener {
  @KafkaListener(topics = "orders")
  void on(String m) {}
  @Bean DefaultErrorHandler errors(KafkaTemplate t) { return new DefaultErrorHandler(new DeadLetterPublishingRecoverer(t)); }
}
""",
}

WEAK = {
    "pom.xml": POM_32,
    "src/main/resources/application.properties": "spring.datasource.url=jdbc:postgresql://db/orders\nspring.datasource.hikari.maximum-pool-size=10\n",
    J + "Client.java": "package com.acme;\nimport org.springframework.web.client.RestTemplate;\nclass Client {\n  RestTemplate t = new RestTemplate();\n  @Retryable void call() {}\n}\n",
    J + "Listener.java": "package com.acme;\nclass Listener {\n  @RabbitListener(queues = \"q\")\n  void on(String m) {}\n}\n",
}

BROKEN = {
    "pom.xml": POM_34,
    "src/main/resources/application.properties": "feign.client.config.default.read-timeout=0\nserver.shutdown=immediate\n"
                                                 "spring.jpa.properties.jakarta.persistence.query.timeout=-1\nspring.datasource.url=jdbc:h2:mem:x\n",
    J + "Api.java": "package com.acme;\n@FeignClient(name = \"x\")\ninterface Api {}\n",
}

DEFAULTS = {
    "pom.xml": POM_34,
    "src/main/resources/logback-spring.xml": "<configuration>\n</configuration>\n",
    J + "Api.java": "package com.acme;\nimport okhttp3.OkHttpClient;\nclass Api {\n  OkHttpClient c = new OkHttpClient.Builder().connectTimeout(Duration.ofSeconds(1)).build();\n}\n",
}

EDGES = {
    "pom.xml": POM_32,
    "src/main/resources/application.properties": "spring.datasource.url=jdbc:h2:mem:testdb\n",
    J + "Cmd.java": "package com.acme;\nclass Cmd extends HystrixCommand<String> {\n}\n",
    J + "Queue.java": "package com.acme;\nclass Queue {\n  @SqsListener(\"orders\")\n  void on(String m) {}\n}\n",
}

BARE = {"pom.xml": F.pom("lib", "", "17", []).replace("<version></version>", ""), J + "X.java": "package com.acme;\nclass X {}\n"}


class RuntimeTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        root = tempfile.mkdtemp()
        cls.repos = {n: F.make_repo(root, n, files) for n, files in
                     (("good", GOOD), ("weak", WEAK), ("broken", BROKEN), ("defaults", DEFAULTS), ("edges", EDGES), ("bare", BARE))}
        cls.docs = {n: discover.build(r) for n, r in cls.repos.items()}

    def st(self, app, key):
        return self.docs[app]["runtime"][key]["value"]["state"]

    def test_well_configured_service_is_present_on_every_check(self):
        for key in ("http_timeouts", "retries_breakers", "messaging_errors", "db_timeouts", "graceful_shutdown", "structured_logging"):
            self.assertEqual(self.st("good", key), "PRESENT", key)
        self.assertIn("dead-letter", self.docs["good"]["runtime"]["messaging_errors"]["value"]["summary"])

    def test_weak_service_shows_the_gap_and_why(self):
        rt = self.docs["weak"]["runtime"]
        self.assertEqual(self.st("weak", "http_timeouts"), "ABSENT")
        self.assertIn("RestTemplate", rt["http_timeouts"]["value"]["summary"])
        self.assertEqual(self.st("weak", "retries_breakers"), "PARTIAL")  # retries without a breaker
        self.assertEqual(self.st("weak", "messaging_errors"), "ABSENT")
        self.assertEqual(self.st("weak", "db_timeouts"), "PARTIAL")  # pool only
        self.assertEqual(self.st("weak", "graceful_shutdown"), "ABSENT")  # Boot 3.2 stops immediately by default
        self.assertEqual(self.st("weak", "structured_logging"), "ABSENT")

    def test_disabled_timeouts_and_immediate_shutdown_are_issues(self):
        for key in ("http_timeouts", "db_timeouts", "graceful_shutdown"):
            self.assertEqual(self.st("broken", key), "ISSUE", key)
        self.assertEqual(self.st("broken", "messaging_errors"), "NOT_APPLICABLE")

    def test_defaults_are_declared_not_configured(self):
        self.assertEqual(self.st("defaults", "http_timeouts"), "PARTIAL")  # connect timeout only
        gs = self.docs["defaults"]["runtime"]["graceful_shutdown"]["value"]
        self.assertEqual((gs["state"], gs["level"]), ("PRESENT", "declared"))  # graceful by default from Boot 3.4
        self.assertEqual(self.st("defaults", "structured_logging"), "PARTIAL")  # encoder declared, not used

    def test_hystrix_subclass_in_memory_database_and_sqs_redrive(self):
        self.assertEqual(self.st("edges", "retries_breakers"), "PRESENT")  # extends HystrixCommand
        self.assertEqual(self.st("edges", "db_timeouts"), "NOT_APPLICABLE")  # H2 in memory
        self.assertEqual(self.st("edges", "messaging_errors"), "UNKNOWN")  # SQS redrive is a queue setting kept elsewhere
        repo = F.make_repo(tempfile.mkdtemp(), "sqs", dict(EDGES, **{"infra/queue.tf": 'resource "aws_sqs_queue" "q" {\n  redrive_policy = jsonencode({maxReceiveCount = 5})\n}\n'}))
        self.assertEqual(discover.build(repo)["runtime"]["messaging_errors"]["value"]["state"], "PRESENT")

    def test_nothing_to_read_is_unknown_not_absent(self):
        self.assertEqual(self.st("bare", "http_timeouts"), "UNKNOWN")
        self.assertEqual(self.st("bare", "db_timeouts"), "UNKNOWN")
        self.assertEqual(self.st("bare", "graceful_shutdown"), "UNKNOWN")

    def test_yaml_keys_are_flattened_with_their_line(self):
        cfg = runtime.settings(Ctx(self.repos["good"]))
        by = {s["key"]: s for s in cfg}
        self.assertEqual(by["spring.http.client.read-timeout"]["value"], "5s")
        self.assertEqual(by["spring.http.client.read-timeout"]["ev"]["line_start"], 14)
        self.assertEqual(by["server.shutdown"]["k"], "server.shutdown")
        self.assertIn("spring.lifecycle.timeout-per-shutdown-phase", by)

    def test_every_cited_line_verifies(self):
        for n, doc in self.docs.items():
            for fid, f in evidence.iter_facts(doc):
                if fid.startswith("runtime."):
                    for e in f["evidence"]:
                        self.assertIsNone(evidence.verify(self.repos[n], e), (n, fid, e))


if __name__ == "__main__":
    unittest.main()
