"""Dependency catalogue: real coordinates must map to the right technology, look-alikes must not."""
import os
import sys
import unittest

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(HERE, "..", "scripts"))
os.environ["DISCOVERY_FIXED_TIME"] = "2026-01-01T00:00:00Z"

import evidence  # noqa: E402
from detectors import integrations as I  # noqa: E402


def techs(coord):
    return {t for _, t, _, _, _, rxs in I.CATALOG if any(rx.fullmatch(coord) for rx in rxs)}


REAL = {
    "org.postgresql:postgresql": "PostgreSQL", "io.r2dbc:r2dbc-postgresql": "PostgreSQL", "io.quarkus:quarkus-jdbc-postgresql": "PostgreSQL",
    "mysql:mysql-connector-java": "MySQL", "com.mysql:mysql-connector-j": "MySQL", "org.mariadb.jdbc:mariadb-java-client": "MariaDB",
    "com.oracle.database.jdbc:ojdbc8": "Oracle", "com.oracle.database.jdbc:ojdbc11": "Oracle", "com.oracle:ojdbc6": "Oracle", "com.oracle.jdbc:ojdbc14": "Oracle",
    "com.microsoft.sqlserver:mssql-jdbc": "SQL Server", "com.h2database:h2": "H2 (embedded)", "org.hsqldb:hsqldb": "HSQLDB (embedded)",
    "org.mongodb:mongodb-driver-sync": "MongoDB", "org.mongodb:mongodb-driver-core": "MongoDB", "org.mongodb:mongodb-driver-reactivestreams": "MongoDB",
    "org.mongodb:mongo-java-driver": "MongoDB", "org.springframework.boot:spring-boot-starter-data-mongodb": "MongoDB",
    "com.datastax.oss:java-driver-core": "Cassandra", "redis.clients:jedis": "Redis", "io.lettuce:lettuce-core": "Redis",
    "org.springframework.boot:spring-boot-starter-data-redis": "Redis", "org.redisson:redisson-spring-boot-starter": "Redis", "io.quarkus:quarkus-redis-client": "Redis",
    "org.apache.kafka:kafka-clients": "Kafka", "org.springframework.kafka:spring-kafka": "Kafka", "io.micronaut.kafka:micronaut-kafka": "Kafka",
    "org.springframework.boot:spring-boot-starter-amqp": "RabbitMQ", "com.rabbitmq:amqp-client": "RabbitMQ",
    "org.apache.activemq:activemq-broker": "ActiveMQ / Artemis", "org.apache.activemq:artemis-jms-client": "ActiveMQ / Artemis", "com.ibm.mq:com.ibm.mq.allclient": "IBM MQ",
    "software.amazon.awssdk:sqs": "AWS SQS", "io.awspring.cloud:spring-cloud-aws-starter-sqs": "AWS SQS", "software.amazon.awssdk:s3": "AWS S3", "com.amazonaws:aws-java-sdk-s3": "AWS S3",
    "co.elastic.clients:elasticsearch-java": "Elasticsearch / OpenSearch", "org.elasticsearch.client:elasticsearch-rest-high-level-client": "Elasticsearch / OpenSearch",
    "org.springframework.boot:spring-boot-starter-oauth2-resource-server": "OAuth2 / OIDC provider", "io.quarkus:quarkus-oidc": "OAuth2 / OIDC provider",
    "org.springframework.boot:spring-boot-starter-data-ldap": "LDAP directory", "org.springframework.boot:spring-boot-starter-mail": "SMTP mail server",
    "org.flywaydb:flyway-core": "Flyway", "org.flywaydb:flyway-database-postgresql": "Flyway", "org.liquibase:liquibase-core": "Liquibase",
    "org.springframework.cloud:spring-cloud-starter-openfeign": "OpenFeign", "io.ktor:ktor-client-cio": "Ktor client",
    "org.testcontainers:postgresql": "PostgreSQL", "org.testcontainers:kafka": "Kafka", "com.github.tomakehurst:wiremock-jre8": "WireMock (HTTP stub)",
}
NOT_A_SERVICE = [
    "com.acme:redis-docs", "org.postgresql:postgresql-examples", "redis.clients:jedis-mock", "org.mongodb:mongodb-driver-docs", "org.apache.kafka:kafka-streams-test-utils",
    "org.springframework.boot:spring-boot-starter-web", "org.springframework.boot:spring-boot-starter-test", "com.github.ben-manes.caffeine:caffeine", "com.zaxxer:HikariCP",
    "org.slf4j:slf4j-api", "org.testcontainers:testcontainers", "org.testcontainers:junit-jupiter", "com.google.guava:guava", "org.apache.commons:commons-lang3",
]


class CatalogTest(unittest.TestCase):
    def test_real_coordinates_map_to_their_technology(self):
        for coord, tech in REAL.items():
            self.assertIn(tech, techs(coord), coord)

    def test_look_alikes_and_unrelated_libraries_map_to_nothing(self):
        for coord in NOT_A_SERVICE:
            self.assertEqual(techs(coord), set(), coord)

    def test_connection_url_credentials_are_redacted(self):
        for line in ("uri: postgres://app:Sup3rS3cret@db:5432/x", "REDIS=redis://:hunter2hunter2@cache:6379", "amqp://guest:guest@mq"):
            out = evidence.snip(line)
            self.assertNotIn("Sup3rS3cret", out)
            self.assertNotIn("hunter2hunter2", out)
            self.assertNotIn("guest:guest", out)
        self.assertIn("${USER}:${PASS}@", evidence.snip("amqp://${USER}:${PASS}@mq"))  # references are not secrets

    def test_database_words_are_not_read_from_a_url_or_placeholder_name(self):
        self.assertEqual(I.tech_of_text("org.hibernate.dialect.PostgreSQLDialect")[0], "PostgreSQL")
        self.assertEqual(I.tech_of_text("org.hibernate.dialect.H2Dialect"), ("H2 (embedded)", True))
        self.assertIsNone(I.tech_of_text("some_other_thing"))


class CommandPositionTest(unittest.TestCase):
    RX = r"kubectl\s+(?:apply|rollout)\b"

    def test_real_commands(self):
        for line in ("    - kubectl apply -f k8s/", "      - run: kubectl apply -f k8s/", "  sh 'kubectl apply -f k8s/'", "kubectl rollout status deploy/x",
                     "- cd k8s && kubectl apply -k .", "- sudo kubectl apply -f x", "- if kubectl apply -f x; then echo ok; fi"):
            self.assertTrue(I.at_command_position(line, self.RX), line)

    def test_text_that_only_mentions_a_command(self):
        for line in ('- run: echo "never run kubectl apply -f x here"', "- echo kubectl apply", "- printf 'kubectl apply'", "- grep -r 'kubectl apply' docs",
                     "- name: kubectl apply step", "- curl https://example.com/kubectl apply"):
            self.assertFalse(I.at_command_position(line, self.RX), line)


class HostileInputTest(unittest.TestCase):
    def test_pathological_pom_is_scanned_in_linear_time(self):
        import tempfile
        import time
        from detectors import Ctx
        d = tempfile.mkdtemp()
        with open(os.path.join(d, "pom.xml"), "w") as fh:
            fh.write("<project>" + "<plugin " * 100000 + "<!-- " * 50000 + "<dependency>" * 40000 + "</project>")
        ctx = Ctx(d)
        t = time.time()
        self.assertEqual(I.maven_deps(ctx, "pom.xml"), [])
        self.assertLess(time.time() - t, 5, "XML scanning must stay linear on a hostile pom")

    def test_nested_and_self_closing_elements(self):
        text = "<a><dependency/><dependency><x>1</x></dependency><plugin><plugin></plugin></plugin></a>"
        self.assertEqual(len(I._elements(text, "dependency")), 1)
        self.assertEqual(len(I._elements(text, "plugin")), 1)  # outermost only
        self.assertEqual(I._elements("<dependency><artifactId>x", "dependency"), [])  # unclosed: ignored


if __name__ == "__main__":
    unittest.main()
