"""What the application depends on and how it is packaged: external services, modules, containers.

Read from files only. A dependency is reported when a build file declares a known coordinate, a configuration file or
source literal names a connection (jdbc:postgresql://, redis://, bootstrap.servers ...), or a compose file starts a known
image. Every item says WHERE it applies (the application, tests only, docker-compose only) and HOW STRONG the evidence is
(a connection setting, or only a declared dependency). Nothing is guessed from a substring: coordinates are matched whole.
"""
from __future__ import annotations

import os
import re

from evidence import fact, file_ev, find_lines, grep_files, read_lines

VERSION = "0.1.0"

DB, CACHE, MQ, STORE, SEARCH, IDP, MAIL, PLAT, SVC, HTTP, MON, MIG, STUB = (
    "Database", "Cache and data grid", "Messaging", "Object storage", "Search", "Identity and access", "Notifications",
    "Configuration, secrets and discovery", "Services it calls", "HTTP client libraries", "Observability", "Schema migrations",
    "Stubs and emulators")
KIND_ORDER = [DB, CACHE, SEARCH, STORE, MIG, MQ, SVC, IDP, PLAT, MON, MAIL, STUB, HTTP]
# the group an item is shown under: what the application needs, not how it is built
GROUP = {DB: "Data stores", CACHE: "Data stores", SEARCH: "Data stores", STORE: "Data stores", MIG: "Data stores", MQ: "Messaging", SVC: "Services it calls",
         IDP: "Identity and access", PLAT: "Configuration, secrets and discovery", MON: "Observability", MAIL: "Notifications", STUB: "Stubs and emulators"}
GROUP_ORDER = ["Data stores", "Messaging", "Services it calls", "Identity and access", "Configuration, secrets and discovery", "Observability", "Notifications", "Stubs and emulators"]
GENERIC_SQL = "SQL database (type not stated)"
GENERIC_JMS = "JMS broker (not identified)"

# (kind, technology, family, embedded, generic, [coordinate patterns matched against group:artifact])
CATALOG = []


def _e(kind, tech, *rx, family=None, embedded=False, generic=False):
    CATALOG.append((kind, tech, family, embedded, generic, [re.compile(x, re.I) for x in rx]))


_e(DB, "PostgreSQL", r"org\.postgresql:(?:postgresql|r2dbc-postgresql)", r"io\.r2dbc:r2dbc-postgresql", r"io\.quarkus:quarkus-(?:jdbc-postgresql|reactive-pg-client)",
   r"io\.vertx:vertx-pg-client", r"com\.impossibl\.pgjdbc-ng:pgjdbc-ng", r"org\.testcontainers:postgresql", r"io\.zonky\.test:embedded-postgres",
   r"com\.opentable\.components:otj-pg-embedded", family="sql")
_e(DB, "MySQL", r"mysql:mysql-connector-java", r"com\.mysql:mysql-connector-j", r"io\.quarkus:quarkus-(?:jdbc-mysql|reactive-mysql-client)",
   r"io\.asyncer:r2dbc-mysql", r"io\.vertx:vertx-mysql-client", r"org\.testcontainers:mysql", family="sql")
_e(DB, "MariaDB", r"org\.mariadb\.jdbc:mariadb-java-client", r"io\.quarkus:quarkus-jdbc-mariadb", r"org\.mariadb:r2dbc-mariadb",
   r"org\.testcontainers:mariadb", family="sql")
_e(DB, "Oracle", r"(?:com\.oracle(?:\.database)?\.jdbc|com\.oracle\.ojdbc|com\.oracle|oracle):ojdbc\w*", r"io\.quarkus:quarkus-jdbc-oracle",
   r"com\.oracle\.database\.r2dbc:oracle-r2dbc", r"org\.testcontainers:oracle-(?:xe|free)", family="sql")
_e(DB, "SQL Server", r"com\.microsoft\.sqlserver:mssql-jdbc", r"io\.quarkus:quarkus-jdbc-mssql", r"io\.r2dbc:r2dbc-mssql",
   r"net\.sourceforge\.jtds:jtds", r"org\.testcontainers:mssqlserver", family="sql")
_e(DB, "IBM Db2", r"com\.ibm\.db2:jcc", r"io\.quarkus:quarkus-jdbc-db2", family="sql")
_e(DB, "H2 (embedded)", r"com\.h2database:h2", r"io\.r2dbc:r2dbc-h2", r"io\.quarkus:quarkus-jdbc-h2", family="sql", embedded=True)
_e(DB, "HSQLDB (embedded)", r"org\.hsqldb:hsqldb", family="sql", embedded=True)
_e(DB, "Apache Derby (embedded)", r"org\.apache\.derby:derby\w*", family="sql", embedded=True)
_e(DB, "SQLite (embedded)", r"org\.xerial:sqlite-jdbc", family="sql", embedded=True)
_e(DB, GENERIC_SQL, r"org\.springframework\.boot:spring-boot-starter-(?:data-jpa|jdbc|data-jdbc|data-r2dbc)", r"org\.springframework:spring-jdbc",
   r"org\.hibernate(?:\.orm)?:hibernate-core", r"io\.quarkus:quarkus-(?:hibernate-orm\w*|hibernate-reactive\w*|agroal)",
   r"io\.micronaut\.(?:data|sql):micronaut-(?:data-(?:jdbc|jpa|r2dbc|hibernate-jpa)|jdbc-hikari|jdbc-tomcat|hibernate-jpa)",
   r"org\.jetbrains\.exposed:exposed-(?:core|jdbc|dao)", r"org\.jooq:jooq", r"org\.mybatis\.spring\.boot:mybatis-spring-boot-starter",
   r"org\.jdbi:jdbi3-core", family="sql", generic=True)
_e(DB, "MongoDB", r"org\.mongodb:(?:mongodb-driver(?:-sync|-core|-legacy|-reactivestreams|-kotlin-\w+)?|mongo-java-driver)", r"org\.springframework\.boot:spring-boot-starter-data-mongodb(?:-reactive)?",
   r"org\.springframework\.data:spring-data-mongodb", r"io\.quarkus:quarkus-mongodb-(?:client|panache)\w*", r"io\.micronaut\.mongodb:[\w-]+",
   r"org\.litote\.kmongo:[\w-]+", r"org\.testcontainers:mongodb", r"de\.flapdoodle\.embed:de\.flapdoodle\.embed\.mongo")
_e(DB, "Cassandra", r"org\.springframework\.boot:spring-boot-starter-data-cassandra(?:-reactive)?", r"com\.datastax\.oss:java-driver-core",
   r"com\.datastax\.cassandra:cassandra-driver-core", r"io\.quarkus:quarkus-cassandra-client", r"org\.testcontainers:cassandra")
_e(DB, "DynamoDB", r"software\.amazon\.awssdk:dynamodb(?:-enhanced)?", r"com\.amazonaws:aws-java-sdk-dynamodb", r"io\.quarkus:quarkus-amazon-dynamodb")
_e(DB, "Neo4j", r"org\.neo4j\.driver:neo4j-java-driver", r"org\.springframework\.boot:spring-boot-starter-data-neo4j", r"org\.testcontainers:neo4j")
_e(DB, "InfluxDB", r"com\.influxdb:[\w-]+", r"org\.influxdb:influxdb-java")
_e(MIG, "Flyway", r"org\.flywaydb:flyway-[\w-]+", r"io\.quarkus:quarkus-flyway")
_e(MIG, "Liquibase", r"org\.liquibase:liquibase-core", r"io\.quarkus:quarkus-liquibase")

_e(CACHE, "Redis", r"org\.springframework\.boot:spring-boot-starter-data-redis(?:-reactive)?", r"org\.springframework\.data:spring-data-redis",
   r"redis\.clients:jedis", r"io\.lettuce:lettuce-core", r"org\.redisson:redisson[\w-]*", r"io\.quarkus:quarkus-redis-(?:client|cache)",
   r"io\.micronaut\.redis:[\w-]+", r"org\.springframework\.session:spring-session-data-redis", r"io\.vertx:vertx-redis-client",
   r"com\.redis:testcontainers-redis", r"com\.redis\.testcontainers:testcontainers-redis", r"com\.github\.codemonstur:embedded-redis", r"it\.ozimov:embedded-redis")
_e(CACHE, "Memcached", r"net\.spy:spymemcached", r"com\.googlecode\.xmemcached:xmemcached")
_e(CACHE, "Hazelcast (embedded or remote)", r"com\.hazelcast:hazelcast[\w-]*")
_e(CACHE, "Apache Ignite (embedded or remote)", r"org\.apache\.ignite:ignite-[\w-]+")
_e(CACHE, "Infinispan (embedded or remote)", r"org\.infinispan:[\w-]+")

_e(MQ, "Kafka", r"org\.apache\.kafka:(?:kafka-clients|kafka-streams)", r"org\.springframework\.kafka:spring-kafka(?:-test)?",
   r"io\.quarkus:quarkus-(?:smallrye-reactive-messaging-kafka|kafka-client|kafka-streams)", r"io\.micronaut\.kafka:[\w-]+", r"io\.vertx:vertx-kafka-client",
   r"org\.springframework\.cloud:spring-cloud-stream-binder-kafka[\w-]*", r"org\.testcontainers:(?:kafka|redpanda)")
_e(MQ, "RabbitMQ", r"org\.springframework\.boot:spring-boot-starter-amqp", r"org\.springframework\.amqp:spring-rabbit", r"com\.rabbitmq:amqp-client",
   r"io\.quarkus:quarkus-(?:smallrye-reactive-messaging-rabbitmq|rabbitmq-client)", r"io\.micronaut\.rabbitmq:[\w-]+",
   r"org\.springframework\.cloud:spring-cloud-stream-binder-rabbit", r"org\.testcontainers:rabbitmq")
_e(MQ, "ActiveMQ / Artemis", r"org\.apache\.activemq:[\w-]+", r"org\.springframework\.boot:spring-boot-starter-(?:activemq|artemis)",
   r"io\.quarkus:quarkus-artemis-jms", family="jms")
_e(MQ, "IBM MQ", r"com\.ibm\.mq:[\w.-]+", family="jms")
_e(MQ, GENERIC_JMS, r"(?:javax|jakarta)\.jms:[\w.-]+", r"org\.springframework:spring-jms", r"org\.springframework\.boot:spring-boot-starter-jms", family="jms", generic=True)
_e(MQ, "AWS SQS", r"software\.amazon\.awssdk:sqs", r"com\.amazonaws:aws-java-sdk-sqs", r"io\.awspring\.cloud:spring-cloud-aws-(?:starter-)?sqs",
   r"io\.quarkus:quarkus-amazon-sqs", r"com\.amazonaws:amazon-sqs-java-messaging-lib")
_e(MQ, "AWS SNS", r"software\.amazon\.awssdk:sns", r"com\.amazonaws:aws-java-sdk-sns", r"io\.awspring\.cloud:spring-cloud-aws-(?:starter-)?sns", r"io\.quarkus:quarkus-amazon-sns")
_e(MQ, "AWS Kinesis", r"software\.amazon\.awssdk:kinesis", r"com\.amazonaws:aws-java-sdk-kinesis")
_e(MQ, "Google Pub/Sub", r"com\.google\.cloud:google-cloud-pubsub", r"com\.google\.cloud:spring-cloud-gcp-starter-pubsub")
_e(MQ, "Azure Service Bus / Event Hubs", r"com\.azure:azure-messaging-(?:servicebus|eventhubs)")
_e(MQ, "NATS", r"io\.nats:jnats")
_e(MQ, "Apache Pulsar", r"org\.apache\.pulsar:pulsar-client[\w-]*")

_e(STORE, "AWS S3", r"software\.amazon\.awssdk:s3(?:-transfer-manager)?", r"com\.amazonaws:aws-java-sdk-s3", r"io\.awspring\.cloud:spring-cloud-aws-(?:starter-)?s3",
   r"io\.quarkus:quarkus-amazon-s3")
_e(STORE, "MinIO", r"io\.minio:minio")
_e(STORE, "Google Cloud Storage", r"com\.google\.cloud:google-cloud-storage")
_e(STORE, "Azure Blob Storage", r"com\.azure:azure-storage-blob")

_e(SEARCH, "Elasticsearch / OpenSearch", r"org\.elasticsearch\.client:[\w-]+", r"co\.elastic\.clients:elasticsearch-java", r"org\.springframework\.boot:spring-boot-starter-data-elasticsearch",
   r"org\.springframework\.data:spring-data-elasticsearch", r"io\.quarkus:quarkus-elasticsearch-[\w-]+", r"org\.opensearch\.client:[\w-]+", r"org\.testcontainers:(?:elasticsearch|opensearch)")
_e(SEARCH, "Apache Solr", r"org\.apache\.solr:solr-solrj")

_e(IDP, "OAuth2 / OIDC provider", r"org\.springframework\.boot:spring-boot-starter-oauth2-(?:resource-server|client)", r"org\.springframework\.security:spring-security-oauth2-(?:resource-server|client|jose)",
   r"io\.quarkus:quarkus-(?:oidc|oidc-client|keycloak-authorization)", r"io\.micronaut\.security:micronaut-security-(?:jwt|oauth2)",
   r"org\.keycloak:keycloak-(?:[\w-]*adapter[\w-]*|admin-client|authz-client|spring-boot-starter|spring-security-adapter|servlet-filter-adapter)")
_e(STUB, "Keycloak (test container)", r"com\.github\.dasniko:testcontainers-keycloak")
_e(IDP, "LDAP directory", r"org\.springframework\.boot:spring-boot-starter-data-ldap", r"org\.springframework\.ldap:spring-ldap-core", r"org\.springframework\.security:spring-security-ldap",
   r"com\.unboundid:unboundid-ldapsdk", r"org\.testcontainers:ldap")

_e(PLAT, "Spring Cloud Config Server", r"org\.springframework\.cloud:spring-cloud-(?:starter-config|config-client)")
_e(PLAT, "Service discovery (Eureka / Consul)", r"org\.springframework\.cloud:spring-cloud-starter-(?:netflix-eureka-client|consul-discovery)", r"org\.springframework\.cloud:spring-cloud-starter-consul-config")
_e(PLAT, "HashiCorp Vault", r"org\.springframework\.cloud:spring-cloud-starter-vault-config", r"org\.springframework\.vault:spring-vault-core", r"io\.quarkus:quarkus-vault")
_e(PLAT, "Google Secret Manager", r"com\.google\.cloud:spring-cloud-gcp-starter-secretmanager", r"com\.google\.cloud:google-cloud-secretmanager")
_e(PLAT, "AWS Secrets Manager", r"software\.amazon\.awssdk:secretsmanager", r"io\.awspring\.cloud:spring-cloud-aws-(?:starter-)?secrets-manager")

_e(MAIL, "SMTP mail server", r"org\.springframework\.boot:spring-boot-starter-mail", r"io\.quarkus:quarkus-mailer", r"org\.simplejavamail:simple-java-mail", r"com\.sun\.mail:(?:jakarta|javax)\.mail")
_e(MAIL, "Twilio", r"com\.twilio\.sdk:twilio")
_e(MAIL, "SendGrid", r"com\.sendgrid:sendgrid-java")

_e(STUB, "WireMock (HTTP stub)", r"com\.github\.tomakehurst:wiremock[\w-]*", r"org\.wiremock:wiremock[\w-]*")
_e(STUB, "LocalStack (AWS emulator)", r"org\.testcontainers:localstack")

_e(HTTP, "OpenFeign", r"org\.springframework\.cloud:spring-cloud-starter-openfeign", r"io\.github\.openfeign:feign-[\w-]+")
_e(HTTP, "MicroProfile / Quarkus REST client", r"io\.quarkus:quarkus-rest-client[\w-]*", r"org\.eclipse\.microprofile\.rest\.client:microprofile-rest-client-api")
_e(HTTP, "Micronaut HTTP client", r"io\.micronaut:micronaut-http-client")
_e(HTTP, "Ktor client", r"io\.ktor:ktor-client-[\w-]+")
_e(HTTP, "Dropwizard client (Jersey / Apache)", r"io\.dropwizard:dropwizard-client")
_e(HTTP, "http4k client", r"org\.http4k:http4k-client-[\w-]+")
_e(HTTP, "OkHttp", r"com\.squareup\.okhttp3:okhttp")
_e(HTTP, "Retrofit", r"com\.squareup\.retrofit2:retrofit")
_e(HTTP, "Apache HttpClient", r"org\.apache\.httpcomponents(?:\.client5)?:httpclient5?")

_e(MON, "Datadog", r"io\.micrometer:micrometer-registry-datadog", r"com\.datadoghq:[\w-]+")
_e(MON, "New Relic", r"io\.micrometer:micrometer-registry-new-?relic", r"com\.newrelic\.agent\.java:newrelic-api")
_e(MON, "Sentry", r"io\.sentry:sentry[\w-]*")
_e(MON, "OpenTelemetry collector (OTLP)", r"io\.opentelemetry:opentelemetry-exporter-otlp", r"io\.micrometer:micrometer-registry-otlp")
_e(MON, "Zipkin", r"io\.zipkin\.[\w.]+:[\w-]+", r"io\.opentelemetry:opentelemetry-exporter-zipkin")
_e(MON, "PCP metrics (Parfait)", r"com\.custardsource\.parfait:parfait-(?:pcp|dropwizard|core)", r"io\.pcp\.parfait:[\w-]+", r"[\w.]+:[\w-]*pcp-monitoring")
_e(MON, "Prometheus (metrics endpoint exposed)", r"io\.micrometer:micrometer-registry-prometheus", r"io\.prometheus:simpleclient[\w-]*")

# connection strings: the scheme is the evidence; family/embedded as in the catalogue
SCHEMES = [
    (r"\b(?:jdbc|r2dbc):(?:pool:)?postgresql:|(?<![\w+.-])postgres(?:ql)?://", DB, "PostgreSQL", "sql", False),
    (r"\b(?:jdbc|r2dbc):(?:pool:)?mariadb:", DB, "MariaDB", "sql", False),
    (r"\b(?:jdbc|r2dbc):(?:pool:)?mysql:|(?<![\w+.-])mysql://", DB, "MySQL", "sql", False),
    (r"\b(?:jdbc|r2dbc):(?:pool:)?oracle:", DB, "Oracle", "sql", False),
    (r"\bjdbc:sqlserver:|\bjdbc:jtds:|\br2dbc:(?:pool:)?mssql:", DB, "SQL Server", "sql", False),
    (r"\bjdbc:db2:", DB, "IBM Db2", "sql", False),
    (r"\b(?:jdbc|r2dbc):(?:pool:)?h2:", DB, "H2 (embedded)", "sql", True),
    (r"\bjdbc:hsqldb:", DB, "HSQLDB (embedded)", "sql", True),
    (r"\bjdbc:derby:", DB, "Apache Derby (embedded)", "sql", True),
    (r"\bjdbc:sqlite:", DB, "SQLite (embedded)", "sql", True),
    (r"(?<![\w+.-])mongodb(?:\+srv)?://", DB, "MongoDB", None, False),
    (r"(?<![\w+.-])(?:bolt|neo4j)(?:\+s|\+ssc)?://", DB, "Neo4j", None, False),
    (r"(?<![\w+.-])rediss?://", CACHE, "Redis", None, False),
    (r"(?<![\w+.-])amqps?://", MQ, "RabbitMQ", None, False),
    (r"(?<![\w+.-])failover:\(?(?:tcp|ssl)://|(?<![\w+.-])(?:tcp|ssl)://[\w.-]+:61616\b", MQ, "ActiveMQ / Artemis", "jms", False),
    (r"(?<![\w+.-])nats://", MQ, "NATS", None, False),
    (r"(?<![\w+.-])pulsar(?:\+ssl)?://", MQ, "Apache Pulsar", None, False),
    (r"(?<![\w+.-])ldaps?://", IDP, "LDAP directory", None, False),
    (r"(?<![\w+.-])smtps?://", MAIL, "SMTP mail server", None, False),
    (r"(?<![\w+.-])s3://", STORE, "AWS S3", None, False),
    (r"(?<![\w+.-])gs://", STORE, "Google Cloud Storage", None, False),
]
SCHEMES = [(re.compile(rx, re.I), k, t, fam, emb) for rx, k, t, fam, emb in SCHEMES]
DRIVER_CLASS = re.compile(
    r"\b(?:org\.postgresql\.Driver|oracle\.jdbc\.(?:driver\.)?OracleDriver|com\.mysql\.(?:cj\.)?jdbc\.Driver|org\.mariadb\.jdbc\.Driver|"
    r"com\.microsoft\.sqlserver\.jdbc\.SQLServerDriver|net\.sourceforge\.jtds\.jdbc\.Driver|com\.ibm\.db2\.jcc\.DB2Driver|org\.h2\.Driver|"
    r"org\.hsqldb\.jdbc(?:\.JDBCDriver|Driver)|org\.apache\.derby\.jdbc\.\w+|org\.sqlite\.JDBC)\b")
JNDI_SQL = re.compile(r"[\"'>=](?:java:(?:comp/env|jboss|global)/)?jdbc/[\w/.-]+")
# value words naming a database (a dialect, a driver class, a db-kind)
DB_TEXT = [(re.compile(rx), t, emb) for rx, t, emb in (
    (r"(?i)postgres|pgsql|postgis", "PostgreSQL", False), (r"(?i)mariadb", "MariaDB", False), (r"(?i)mysql", "MySQL", False),
    (r"(?i)oracle", "Oracle", False), (r"(?i)sqlserver|mssql|sql[-_ ]?server|jtds", "SQL Server", False), (r"(?i)\bdb2|db2dialect|jcc", "IBM Db2", False),
    (r"(?<![A-Za-z0-9])[Hh]2(?:Dialect|(?![A-Za-z0-9]))", "H2 (embedded)", True), (r"(?i)hsql", "HSQLDB (embedded)", True),
    (r"(?i)derby", "Apache Derby (embedded)", True), (r"(?i)sqlite", "SQLite (embedded)", True))]
FAMILY = {t: fam for _, t, fam, _, _, _ in CATALOG if fam}

# configuration keys. Keys are normalised first: lower case, `_` -> `.`, `-` removed, quotes removed.
SQL_KEY = re.compile(r"(?:^|\.)(?:datasources?\.\w+\.(?:url|jdbcurl|dialect|driverclassname|driver|dbkind|jndiname)|datasource\.(?:url|jdbcurl|jdbc\.url|hikari\.jdbcurl|hikari\.driverclassname|driverclassname|dbkind|jndiname|reactive\.url)"
                     r"|r2dbc\.url|jdbc\.(?:url|driver|driverclassname|jndiname)|dbkind|jpa\.databaseplatform|jpa\.database|(?:hibernate|jpa\.properties\.hibernate)\.dialect|hibernate\.connection\.url"
                     r"|persistence\.jdbc\.(?:url|driver))$")
LOOSE_DB_KEY = re.compile(r"(?:^|\.)(?:db|database)\.(?:url|jdbcurl|driver|driverclassname)$")
KEYS = [(re.compile(e[0]), e[1], e[2], re.compile(e[3]) if len(e) > 3 else None) for e in (
    (r"^spring\.(?:data\.)?redis\.(?:host|port|url|cluster|sentinel|username|password|database|ssl|timeout|lettuce|jedis)|^quarkus\.redis\.|^redis\.(?:host|hosts|uri|url|port|servers)$", CACHE, "Redis"),
    (r"^spring\.kafka\.(?:bootstrapservers|consumer|producer|streams|admin|properties)|(?:^|\.)bootstrap\.?servers$|^kafka\.(?:brokers|servers|host)", MQ, "Kafka"),
    (r"(?:^|\.)schema\.?registry\.url$", MQ, "Confluent Schema Registry"),
    (r"^spring\.rabbitmq\.(?:host|addresses|port|username|virtualhost|ssl)|^quarkus\.rabbitmq\.|^rabbitmq\.(?:host|uri|servers|port)", MQ, "RabbitMQ"),
    (r"^spring\.activemq\.(?:brokerurl|user)|^spring\.artemis\.|^quarkus\.artemis\.", MQ, "ActiveMQ / Artemis"),
    (r"^spring\.(?:data\.)?mongodb\.(?:uri|host|port|database|username|authentication)|^quarkus\.mongodb\.|^mongodb\.(?:uri|servers)", DB, "MongoDB"),
    (r"^spring\.(?:data\.)?elasticsearch\.(?:uris|url|rest|host|port|username)|^quarkus\.elasticsearch\.hosts|^elasticsearch\.(?:host|hosts|url|uris)", SEARCH, "Elasticsearch / OpenSearch"),
    (r"^spring\.(?:data\.)?cassandra\.(?:contactpoints|keyspacename|localdatacenter)|^datastax\.java\.driver", DB, "Cassandra"),
    (r"^spring\.(?:data\.)?neo4j\.(?:uri|username)", DB, "Neo4j"),
    (r"^spring\.ldap\.(?:urls|base)", IDP, "LDAP directory"),
    (r"^spring\.mail\.host|^quarkus\.mailer\.host", MAIL, "SMTP mail server"),
    (r"^(?:spring\.cloud\.aws|quarkus|aws)\.s3\.", STORE, "AWS S3"),
    (r"^(?:spring\.cloud\.aws|quarkus|aws)\.sqs\.", MQ, "AWS SQS"),
    (r"^(?:spring\.cloud\.aws|quarkus|aws)\.sns\.", MQ, "AWS SNS"),
    (r"^(?:spring\.cloud\.aws|quarkus|aws)\.dynamodb\.", DB, "DynamoDB"),
    (r"^spring\.security\.oauth2\.(?:resourceserver|client)\.[\w.]*(?:issueruri|jwksuri|jwtseturi|providers?\.)|^quarkus\.oidc\.(?:authserverurl|clientid)|^micronaut\.security\.oauth2\.", IDP, "OAuth2 / OIDC provider"),
    (r"^spring\.cloud\.vault\.|^quarkus\.vault\.", PLAT, "HashiCorp Vault"),
    (r"^spring\.cloud\.config\.uri$", PLAT, "Spring Cloud Config Server"),
    # spring.config.import names what it imports: only the value says which service that is
    (r"^spring\.config\.import$", PLAT, "Spring Cloud Config Server", r"configserver:"),
    (r"^spring\.config\.import$", PLAT, "Google Secret Manager", r"\bsm://"),
    (r"^spring\.config\.import$", PLAT, "HashiCorp Vault", r"\bvault:"),
    (r"^spring\.config\.import$", PLAT, "AWS Secrets Manager", r"aws-secretsmanager:"),
    (r"^spring\.config\.import$", PLAT, "Service discovery (Eureka / Consul)", r"\bconsul:"),
    (r"^eureka\.client\.serviceurl", PLAT, "Service discovery (Eureka / Consul)"),
    (r"(?:^|\.)(?:elastic\.)?apm(?:\.|$)", MON, "APM agent"), (r"(?:^|\.)sentry\.dsn$", MON, "Sentry"),
    (r"(?:^|\.)(?:es|elasticsearch)\.(?:url|uri|host|hosts|endpoint)s?$", SEARCH, "Elasticsearch / OpenSearch"),
    (r"(?:^|\.)auth0(?:\.|$)", IDP, "Auth0"), (r"(?:^|\.)ping\.?federate(?:\.|$)", IDP, "PingFederate"), (r"(?:^|\.)okta(?:\.|$)", IDP, "Okta"),
    (r"(?:^|\.)cognito(?:\.|$)", IDP, "AWS Cognito"),
    (r"^spring\.flyway\.|^quarkus\.flyway\.|^flyway\.(?:url|locations|schemas)", MIG, "Flyway"),
    (r"^spring\.liquibase\.|^quarkus\.liquibase\.", MIG, "Liquibase"),
)]
# docker images (name without registry tag) that identify a service
IMAGES = [(re.compile(rx, re.I), k, t, fam) for rx, k, t, fam in (
    (r"(?:^|/)(?:postgres|postgresql|postgis|timescaledb)$", DB, "PostgreSQL", "sql"), (r"(?:^|/)mysql(?:-server)?$", DB, "MySQL", "sql"),
    (r"(?:^|/)mariadb$", DB, "MariaDB", "sql"), (r"oracle-(?:xe|free)$|(?:^|/)oracle/database$|container-registry\.oracle\.com/database", DB, "Oracle", "sql"),
    (r"mcr\.microsoft\.com/(?:mssql/server|azure-sql-edge)", DB, "SQL Server", "sql"), (r"(?:^|/)mongo(?:db)?$", DB, "MongoDB", None),
    (r"(?:^|/)cassandra$", DB, "Cassandra", None), (r"(?:^|/)neo4j$", DB, "Neo4j", None),
    (r"(?:^|/)(?:redis|redis-stack(?:-server)?|valkey)$", CACHE, "Redis", None), (r"(?:^|/)memcached$", CACHE, "Memcached", None),
    (r"(?:^|/)(?:cp-kafka|kafka|redpanda)$", MQ, "Kafka", None), (r"(?:^|/)cp-schema-registry$", MQ, "Confluent Schema Registry", None),
    (r"(?:^|/)rabbitmq$", MQ, "RabbitMQ", None), (r"activemq(?:-artemis)?(?:-classic)?$", MQ, "ActiveMQ / Artemis", "jms"),
    (r"(?:^|/)(?:elasticsearch|opensearch)$", SEARCH, "Elasticsearch / OpenSearch", None), (r"(?:^|/)minio$", STORE, "MinIO", None),
    (r"(?:^|/)localstack$", STUB, "LocalStack (AWS emulator)", None), (r"(?:^|/)keycloak$", IDP, "OAuth2 / OIDC provider", None),
    (r"(?:^|/)(?:openldap|docker-test-openldap)$", IDP, "LDAP directory", None), (r"(?:^|/)wiremock$", STUB, "WireMock (HTTP stub)", None),
    (r"(?:^|/)(?:mailhog|mailpit)$", MAIL, "SMTP mail server", None), (r"(?:^|/)vault$", PLAT, "HashiCorp Vault", None),
    (r"(?:^|/)consul$", PLAT, "Service discovery (Eureka / Consul)", None), (r"(?:^|/)zipkin$", MON, "Zipkin", None))]

HOSTS = [(re.compile(rx, re.I), k, t) for rx, k, t in (
    (r"[\w-]+\.auth0\.com\b", IDP, "Auth0"), (r"[\w-]+\.okta(?:preview)?\.com\b", IDP, "Okta"),
    (r"login\.microsoftonline\.com|sts\.windows\.net", IDP, "Azure AD / Entra ID"), (r"cognito-idp\.[\w-]+\.amazonaws\.com", IDP, "AWS Cognito"),
    (r"[\w-]+\.pingone\.(?:com|eu|asia)\b|[\w-]+\.pingidentity\.com\b", IDP, "PingOne"))]
QUICK = re.compile(r"://|jdbc:|r2dbc:|Driver|JDBC|jdbc/|failover:|auth0|okta|microsoftonline|windows\.net|cognito|pingone|pingidentity", re.I)
# an endpoint named in configuration: key ends in url/uri/endpoint/host and the value is a literal http(s) URL
ENDPOINT_KEY = re.compile(r"(?:^|[._-])(?:url|uri|endpoint|host|hostname|baseurl|base[-_]url|address)s?$", re.I)
ENDPOINT_NOT = re.compile(r"(?:^|[._-])(?:springdoc|swagger|openapi|api[-_]?docs|cancel|return|failure|success|ignore|contrast|sonar|snyk|artifactory|nexus|licen[sc]e|contact|terms|documentation|docs?|schema|namespace|xmlns|redirect|callback|logout|login|"
                          r"self|public|frontend|website|homepage|issuer|jwks?|metadata|scm|repository|repo|mirror|proxy|help|support|link|links|image|icon|logo|cdn|static|assets?)(?:[._-]|$)", re.I)
ENDPOINT_VAL = re.compile(r"^(?:https?|wss?|grpcs?)://([A-Za-z0-9][A-Za-z0-9._-]*)(?::\d+)?(?:[/?#].*)?$")
ENDPOINT_HOST_NOT = re.compile(r"^(?:localhost|127\.\d+\.\d+\.\d+|0\.0\.0\.0|host\.docker\.internal|(?:[\w-]+\.)*example\.(?:com|org|net)|(?:www\.)?w3\.org|[\w.-]*\.local)$", re.I)
CONFIG_EXT = (".properties", ".yml", ".yaml", ".conf", ".xml")


def tech_of_text(text):
    """(tech, embedded) from a dialect, driver class or db-kind word, or None."""
    for rx, t, emb in DB_TEXT:
        if rx.search(text):
            return t, emb
    return None


def norm_key(k):
    return k.lower().replace("_", ".").replace("-", "").replace('"', "").replace("'", "")


def flatten(lines, kind):
    """(flat_key, value, line number) for key/value lines of a .properties, .env, HOCON-ish or YAML file. Indentation decides
    YAML nesting; lists and anchors are not followed."""
    out, stack = [], []
    for i, raw in enumerate(lines, 1):
        s = raw.strip()
        if not s or s.startswith(("#", "!", "//", "/*", "*")):
            continue
        if kind == "yaml":
            if s == "---":
                stack = []
                continue
            m = re.match(r"^\s*-\s*([A-Za-z_][\w.]*)=(.*)$", raw)
            if m:  # compose `environment: - KEY=value`
                out.append((m.group(1), m.group(2).strip().strip("'\""), i))
                continue
            m = re.match(r"^(\s*)(?:-\s+)?([^\s:#][^:#]*?):(?:\s+(.*?))?\s*$", raw)
            if not m:
                continue
            ind, key, val = len(m.group(1)), m.group(2).strip().strip("'\""), (m.group(3) or "")
            while stack and stack[-1][0] >= ind:
                stack.pop()
            val = re.sub(r"\s+#.*$", "", val).strip().strip("'\"")
            if val == "" or val in ("|", ">"):
                stack.append((ind, key))
            else:
                out.append((".".join([k for _, k in stack] + [key]), val, i))
        else:
            m = re.match(r"^(?:export\s+)?(?:ENV\s+)?(%?[\w.\-\[\]\"']+)\s*[=:]\s*(.*?)\s*$", raw.strip())
            if m:
                out.append((m.group(1), m.group(2).strip().strip("'\""), i))
    return out


ENV_TOKEN = re.compile(r"(?:^|[/._-])(prod(?:uction)?|live|preprod|ppd|uat|acpt|stag(?:e|ing)|integration|int|stubs?|sandbox|dev(?:elopment)?|qa)(?:[/._-]|$)", re.I)


def env_of(path):
    m = ENV_TOKEN.search(path)
    if not m:
        return None
    e = m.group(1).lower()
    return {"production": "prod", "live": "prod", "stub": "stubs", "development": "dev", "staging": "stage", "int": "integration"}.get(e, e)


LOCAL_FILE = re.compile(r"(?:^|[/._-])(?:local|dev|development|sandbox)(?:[/._-]|$)", re.I)
DEPLOY_DIR = re.compile(r"(?:^|/)(?:k8s|kubernetes|deploy|deployments?|helm|charts?|manifests?)/", re.I)


def is_local_file(path):
    """A file named for a developer's machine (application-local.properties, local.secrets.properties). A deployment directory
    named dev is an environment, not a laptop."""
    return bool(LOCAL_FILE.search(path)) and not DEPLOY_DIR.search(path)


class Findings:
    def __init__(self):
        self.items = {}
        self.endpoints = {}

    def add(self, kind, tech, scope, basis, ev, family=None, embedded=False, generic=False):
        it = self.items.setdefault((kind, tech), {"kind": kind, "tech": tech, "family": family or FAMILY.get(tech), "embedded": embedded,
                                                  "generic": generic, "pairs": set(), "ev": []})
        it["pairs"].add((scope, basis))  # what was found AND where it applies stay together
        if not any(x[0]["path"] == ev["path"] and x[0]["line_start"] == ev["line_start"] and x[1] == scope for x in it["ev"]):
            it["ev"].append((ev, scope, basis))  # each citation remembers the scope and basis it supports

    def line_hits(self, path, ln, text, scope, basis):
        """Connection strings, driver classes, vendor hosts and JNDI data sources named on one line."""
        if not QUICK.search(text):
            return
        ev = None
        for rx, kind, tech, fam, emb in SCHEMES:
            if rx.search(text):
                ev = ev or file_ev(path, ln, text)
                self.add(kind, tech, scope, basis, ev, fam, emb)
        for rx, kind, tech in HOSTS:
            if rx.search(text):
                ev = ev or file_ev(path, ln, text)
                self.add(kind, tech, scope, basis, ev)
        for m in DRIVER_CLASS.finditer(text):
            t = tech_of_text(m.group(0))
            if t:
                ev = ev or file_ev(path, ln, text)
                self.add(DB, t[0], scope, basis, ev, "sql", t[1])
        if JNDI_SQL.search(text):
            ev = ev or file_ev(path, ln, text)
            self.add(DB, GENERIC_SQL, scope, basis, ev, "sql", False, True)

    def key_hits(self, path, ln, key, val, text, scope, basis):
        cands = {norm_key(key)}
        last = key.split(".")[-1]
        if re.fullmatch(r"[A-Z][A-Z0-9_]{3,}", last):  # an environment variable: SPRING_DATA_REDIS_HOST
            cands.add(norm_key(last))
        typed = False
        for k in cands:
            if SQL_KEY.search(k) or LOOSE_DB_KEY.search(k):
                typed = True
                if any(rx.search(val) for rx, *_ in SCHEMES):
                    continue  # the connection string names the database; line_hits recorded it
                v = re.sub(r"\$\{[^}]*\}", "", val)  # a placeholder's NAME is not evidence of the database type
                t = tech_of_text(v) if "://" not in v and "jdbc:" not in v else None
                ev = file_ev(path, ln, text)
                if t:
                    self.add(DB, t[0], scope, basis, ev, "sql", t[1])
                elif SQL_KEY.search(k):
                    self.add(DB, GENERIC_SQL, scope, basis, ev, "sql", False, True)
                continue
            for rx, kind, tech, vrx in KEYS:
                if rx.search(k) and (vrx is None or vrx.search(val)):
                    typed = True
                    self.add(kind, tech, scope, basis, file_ev(path, ln, text))
        if not typed and scope == "runtime" and basis != "local configuration":
            self.endpoint(path, ln, key, val, text)

    def endpoint(self, path, ln, key, val, text):
        """A literal http(s) URL under a url/uri/endpoint/host key. It names an address the application is configured with,
        not what runs there: the report says so."""
        b = os.path.basename(path)
        if b.startswith(".") or re.search(r"(?i)newrelic|logback|log4j|sonar|ignore|checkstyle|pmd|swagger|openapi|jacoco|dependabot|renovate|gitlab|github|jreleaser|goreleaser|release-please|semantic-release", b):
            return  # tool configuration, not the application's own
        if not ENDPOINT_KEY.search(key) or ENDPOINT_NOT.search(key):
            return
        m = ENDPOINT_VAL.match(val.strip())
        if not m or "${" in val or "{{" in val or ENDPOINT_HOST_NOT.match(m.group(1)):
            return
        e = self.endpoints.setdefault(key, {"by": {}})
        e["by"].setdefault(m.group(1).lower(), file_ev(path, ln, text))


def _strip_comments(text):
    """Blank XML comments but keep line numbers. Linear time: an unclosed comment runs to the end of the file."""
    out, i = [], 0
    while True:
        j = text.find("<!--", i)
        if j < 0:
            out.append(text[i:])
            break
        out.append(text[i:j])
        k = text.find("-->", j + 4)
        end = len(text) if k < 0 else k + 3
        out.append("\n" * text.count("\n", j, end))
        i = end
    return "".join(out)


def _elements(text, tag):
    """Outermost <tag ...>...</tag> elements as (outer_start, inner_start, inner_end, outer_end), in one linear pass. An element that is
    never closed is ignored, so a hostile file with thousands of unclosed tags costs no more than a clean one."""
    import bisect
    rx = re.compile(r"<(/?)%s(?=[\s>/])" % re.escape(tag))
    gts = [m.start() for m in re.finditer(">", text)]

    def gt_after(pos):
        i = bisect.bisect_left(gts, pos)
        return gts[i] if i < len(gts) else None
    out, depth, start, inner = [], 0, None, None
    for m in rx.finditer(text):
        g = gt_after(m.end())
        if g is None:
            break
        if m.group(1) == "":
            if text[g - 1] == "/":  # <tag/>
                continue
            if depth == 0:
                start, inner = m.start(), g + 1
            depth += 1
        elif depth:
            depth -= 1
            if depth == 0:
                out.append((start, inner, m.start(), g + 1))
    return out


def _strip_xml(text, tags=()):
    """Blank XML comments and the given elements, keeping line numbers."""
    text = _strip_comments(text)
    for t in tags:
        spans = _elements(text, t)
        if not spans:
            continue
        out, i = [], 0
        for a, _, _, b in spans:
            out.append(text[i:a])
            out.append("\n" * text.count("\n", a, b))
            i = b
        out.append(text[i:])
        text = "".join(out)
    return text


def maven_deps(ctx, pom):
    """(coordinate, scope, line) for each real dependency of a pom: not a comment, a plugin's own dependency, a managed
    (dependencyManagement) entry or an exclusion. Unresolved ${...} coordinates are skipped."""
    from detectors.tests import _in_optin_profile
    lines = read_lines(ctx.repo, pom)
    if not lines:
        return []
    import bisect
    text = _strip_xml("\n".join(lines), ("pluginManagement", "dependencyManagement", "plugin", "exclusions"))
    nl = [m.start() for m in re.finditer("\n", text)]
    test_mod = ctx._test_module(pom)
    out = []
    for _, i0, i1, _ in _elements(text, "dependency"):
        blk = text[i0:i1]
        g = re.search(r"<groupId>\s*([^<\s]+)\s*<", blk)
        a = re.search(r"<artifactId>\s*([^<\s]+)\s*<", blk)
        if not g or not a or "${" in g.group(1) or "${" in a.group(1):
            continue
        sc = re.search(r"<scope>\s*(\w+)\s*<", blk)
        ln = bisect.bisect_left(nl, i0 + a.start()) + 1
        scope = "test" if (sc and sc.group(1) == "test") or test_mod else "runtime"
        if scope == "runtime" and _in_optin_profile(ctx.repo, pom, ln):
            scope = "profile"
        out.append(("%s:%s" % (g.group(1), a.group(1)), scope, ln))
    return out


GRADLE_CONF = re.compile(r"^(?:api|implementation|compile|runtime|runtimeOnly|compileOnly|developmentOnly|providedRuntime|providedCompile|optional|\w*(?:Api|Implementation|RuntimeOnly|CompileOnly))$")
GRADLE_DEP = re.compile(r"^\s*(\w+)\s*\(?\s*(?:group\s*[:=]\s*['\"]([\w.-]+)['\"]\s*,\s*name\s*[:=]\s*['\"]([\w.-]+)['\"]"
                        r"|['\"]([\w.-]+):([\w.-]+)(?::[^'\"]*)?['\"]|(\w+)\.((?:bundles\.)?[\w.]+?)(?:\.get\(\)|\.asProvider\(\))?\s*[,)]?\s*(?:\{.*)?$)")


def catalogs(ctx):
    """{catalog name: {alias: coordinate}} and bundles, from *.versions.toml files (`libs` is the default name)."""
    cats = {}
    for f in sorted(x for x in ctx.files if x.endswith(".versions.toml") and not ctx._aux(x)):
        name = os.path.basename(f)[:-len(".versions.toml")]
        libs, bundles, section = {}, {}, None
        for ln in read_lines(ctx.repo, f) or []:
            t = ln.strip()
            if not t or t.startswith("#"):
                continue
            if t.startswith("["):
                section = t.strip("[]").strip()
                continue
            m = re.match(r"([\w.-]+)\s*=\s*(.*)$", t)
            if not m:
                continue
            alias, rest = m.group(1), m.group(2)
            if section == "libraries":
                mod = re.search(r"module\s*=\s*\"([^\":]+:[^\":]+)\"", rest) or re.match(r"\"([^\":]+:[^\":]+)(?::[^\"]*)?\"", rest)
                if mod:
                    libs[alias] = mod.group(1)
                else:
                    g, n = re.search(r"group\s*=\s*\"([^\"]+)\"", rest), re.search(r"name\s*=\s*\"([^\"]+)\"", rest)
                    if g and n:
                        libs[alias] = "%s:%s" % (g.group(1), n.group(1))
            elif section == "bundles":
                bundles[alias] = re.findall(r"\"([^\"]+)\"", rest)
        cats[name] = (libs, bundles)
    return cats


def gradle_deps(ctx, path, cats):
    test_mod = ctx._test_module(path) or re.search(r"(?i)(^|[./_-])tests?([./_-]|$)", os.path.basename(path))
    out = []
    for i, ln in enumerate(read_lines(ctx.repo, path) or [], 1):
        if ln.strip().startswith(("//", "*", "/*")):
            continue
        m = GRADLE_DEP.match(ln)
        if not m or not GRADLE_CONF.match(m.group(1)):
            continue
        conf = m.group(1)
        scope = "test" if test_mod or conf == "developmentOnly" or re.match(r"(?i)^\w*test\w*?(?:api|implementation|runtimeonly|compileonly|runtime|compile)$", conf) else "runtime"
        coords = []
        if m.group(2):
            coords = ["%s:%s" % (m.group(2), m.group(3))]
        elif m.group(4):
            coords = ["%s:%s" % (m.group(4), m.group(5))]
        elif m.group(6) in cats:
            libs, bundles = cats[m.group(6)]
            ref = m.group(7)
            norm = lambda s: re.sub(r"[-_.]", ".", s)
            if ref.startswith("bundles."):
                key = next((b for b in bundles if norm(b) == norm(ref[len("bundles."):])), None)
                names = bundles.get(key, [])
                coords = [libs[a] for a in names if a in libs]
            else:
                key = next((a for a in libs if norm(a) == norm(ref)), None)
                coords = [libs[key]] if key else []
        out.extend((c, scope, i) for c in coords)
    return out


CLIENT_ANN = [(re.compile(r"@FeignClient\s*\(([^)]*)"), "feign"), (re.compile(r"@RegisterRestClient\b\s*\(?([^)]*)"), "rest"),
              (re.compile(r"@Client\s*\(([^)]*)"), "micronaut")]


def client_name(ctx, path, ln, args, how):
    """Name a declared HTTP client: the literal name/value/url/configKey in the annotation. A ${placeholder} is not a name."""
    m = (re.search(r"(?:\bname|\bvalue|\bid|\bconfigKey|\bbaseUri)\s*=\s*\"([^\"]+)\"", args) or re.match(r"\s*\"([^\"]+)\"", args)
         or re.search(r"\burl\s*=\s*\"([^\"]+)\"", args))
    if m and "${" not in m.group(1):
        return "HTTP service: " + m.group(1)
    return None


def _is_env_file(f):
    """A real .env file, not a sample: .env.example / .env.sample / .env.template document variables and configure nothing."""
    b = os.path.basename(f)
    return b.startswith(".env") and not re.search(r"(?i)example|sample|template|dist|tmpl", b)


def detect_dependencies(ctx):
    r = ctx.repo
    F = Findings()
    H = Findings()  # HTTP client libraries: how the application calls services, not what it depends on
    cats = catalogs(ctx)
    declared = []
    for pom in ctx.poms:
        declared += [(pom,) + d for d in maven_deps(ctx, pom)]
    for g in ctx.gradle:
        declared += [(g,) + d for d in gradle_deps(ctx, g, cats)]
    for path, coord, scope, ln in declared:
        for kind, tech, fam, emb, gen, rxs in CATALOG:
            if any(rx.fullmatch(coord) for rx in rxs):
                (H if kind == HTTP else F).add(kind, tech, scope, "dependency", file_ev(path, ln, (read_lines(r, path) or [""])[ln - 1]), fam, emb, gen)
    # configuration files, deployment files, Dockerfiles and .env files
    from detectors.resilience import dockerfiles
    deploy = set(ctx.deploy_files)
    build = set(ctx.build_files) | set(ctx.ci_files)

    def is_config(f):
        b = os.path.basename(f)
        if f in build or f in deploy or ctx._aux(f) or ctx._test_module(f) or b in ("pom.xml", "package.json") \
                or re.match(r"(?:.*/)?bin/(?:main|test|default|production)/", f):  # an IDE's compiled output copy, not the source
            return False
        if not (f.endswith(CONFIG_EXT) or _is_env_file(f)):
            return False
        return ("/src/main/" in "/" + f or "/" not in f or _is_env_file(f) or b.startswith(("application", "bootstrap"))
                or re.search(r"(^|/)(?:config|conf|configs|etc|WEB-INF)/", f) is not None) and not b.startswith(("logback", "log4j", "pom."))
    cfg_files = sorted(x for x in ctx.files if is_config(x))
    for f in cfg_files:
        lines = read_lines(r, f) or []
        cbasis = "local configuration" if is_local_file(f) else "connection setting"
        kind = "yaml" if f.endswith((".yml", ".yaml")) else "props"
        live = _strip_xml("\n".join(lines)).split("\n") if f.endswith(".xml") else lines
        for i, raw in enumerate(live, 1):
            if raw.strip() and not raw.strip().startswith(("#", "!", "//")):
                F.line_hits(f, i, lines[i - 1], "runtime", cbasis)
        if not f.endswith(".xml"):
            for key, val, i in flatten(lines, kind):
                F.key_hits(f, i, key, val, lines[i - 1], "runtime", cbasis)
    dep_files = sorted(deploy | set(dockerfiles(ctx)) | {x for x in ctx.files if _is_env_file(x) and not ctx._aux(x)})
    for f in dep_files:
        lines = read_lines(r, f) or []
        is_compose = re.match(r"(?i)(?:docker-)?compose[^/]*\.ya?ml$", os.path.basename(f)) is not None
        basis, scope = ("docker-compose", "compose") if is_compose else ("deployment file", "runtime")
        kind = "yaml" if f.endswith((".yml", ".yaml")) else "props"
        for i, raw in enumerate(lines, 1):
            if raw.strip() and not raw.strip().startswith(("#", "//")):
                F.line_hits(f, i, raw, scope, basis)
        is_docker = os.path.basename(f).lower().startswith("dockerfile") or f.lower().endswith(".dockerfile")
        for key, val, i in flatten(lines, kind) if not is_docker else \
                [(m.group(1), m.group(2), i) for i, l in enumerate(lines, 1) for m in [re.match(r"\s*ENV\s+(\w+)[=\s]+(.*)$", l)] if m]:
            if is_compose:
                m = re.match(r"^services\.[^.]+\.image$", key)
                if m:
                    name = re.split(r"[:@]", val)[0]
                    for rx, k, t, fam in IMAGES:
                        if rx.search(name):
                            F.add(k, t, "compose", "docker-compose", file_ev(f, i, lines[i - 1]), fam)
                            break
            F.key_hits(f, i, key, val, lines[i - 1], scope, basis)
    # source literals and declared HTTP clients
    named = {}
    for f in ctx.src_main_java:
        lines = read_lines(r, f)
        if not lines:
            continue
        for i, ln in enumerate(lines, 1):
            s = ln.strip()
            if s.startswith(("//", "*", "/*")):
                continue
            if "\"" in ln or "'" in ln:
                F.line_hits(f, i, ln, "runtime", "source code")
            if "@" in ln and ("FeignClient" in ln or "RegisterRestClient" in ln or "@Client" in ln):
                for rx, how in CLIENT_ANN:
                    m = rx.search(ln)
                    if m and (how != "micronaut" or any("io.micronaut.http.client.annotation.Client" in x for x in lines[:80])):
                        n = client_name(ctx, f, i, m.group(1), how)
                        if n:
                            named.setdefault(n, file_ev(f, i, ln))
    for n, ev in sorted(named.items()):
        F.add(SVC, n, "runtime", "client declaration", ev)
    ends = sorted(F.endpoints.items())
    prod = lambda host_ev: (0 if re.search(r"(?:^|/)(?:prod|production|live)(?:/|[-_.])", host_ev[1]["path"]) else 1, host_ev[0])
    for key, e in ends[:40]:
        # the same key is often set per environment: lead with the production value, cite it, and say which environment each host is from
        ordered = sorted(e["by"].items(), key=prod)
        last = key.split(".")[-1]
        label = last if re.fullmatch(r"[A-Z][A-Z0-9_]{3,}", last) else key  # an environment variable is named by itself, not by its YAML parents
        F.add(SVC, "Endpoint: " + label, "runtime", "endpoint in configuration", ordered[0][1])
        it = F.items[(SVC, "Endpoint: " + label)]
        it["hosts"] = [h for h, _ in ordered][:3]
        it["host_envs"] = [{"host": h, "env": env_of(ev["path"])} for h, ev in ordered][:3]
    counts = {"build_files": len(ctx.build_files), "configuration_files": len(cfg_files), "deployment_files": len(dep_files),
              "source_files": len(ctx.src_main_java), "endpoints_not_listed": max(0, len(ends) - 40)}
    return finish(F, ctx), finish(H, ctx), counts


STRONG = {"connection setting", "deployment file", "client declaration", "endpoint in configuration"}


def finish(F, ctx):
    items = list(F.items.values())
    app = lambda it: any(sc in ("runtime", "profile") for sc, _ in it["pairs"])
    specific = [it for it in items if it["family"] == "sql" and not it["generic"] and app(it)]
    jms = [it for it in items if it["family"] == "jms" and not it["generic"] and app(it)]
    for it in [x for x in items if x["generic"]]:
        pool = specific if it["family"] == "sql" else jms
        if pool:
            items.remove(it)
            if len(pool) == 1:  # the one named database/broker is the one this setting configures
                pool[0]["pairs"] |= {(sc, b) for sc, b in it["pairs"] if b != "dependency" and sc in ("runtime", "profile")}
                for t in it["ev"]:
                    if t[2] != "dependency" and not any(x[0]["path"] == t[0]["path"] and x[0]["line_start"] == t[0]["line_start"] for x in pool[0]["ev"]):
                        pool[0]["ev"].append(t)
    out = []
    for it in items:
        s = {sc for sc, _ in it["pairs"]}
        if "runtime" in s:
            where, here = "application", "runtime"
        elif "profile" in s:
            where, here = "a build profile only", "profile"
        elif "compose" in s:
            where, here = ("tests and docker-compose only" if "test" in s else "docker-compose only"), "compose"
        else:
            where, here = "tests only", "test"
        # the strength of the claim comes only from what was found where it applies: a test dependency does not strengthen it
        basis_here = {b for sc, b in it["pairs"] if sc == here}
        basis = sorted({b for _, b in it["pairs"]})
        if where == "application":
            strength = ("configured" if basis_here & STRONG else "local setting" if "local configuration" in basis_here
                        else "declared" if "dependency" in basis_here else "named in source")
        else:
            strength = "compose" if where == "docker-compose only" else "declared"
        # cite first what supports the claim shown: evidence from the scope that decides `where`, strongest basis first
        deciding = [t for t in it["ev"] if t[1] == here]
        pool = deciding or it["ev"]
        want = {"configured": STRONG, "local setting": {"local configuration"}, "declared": {"dependency"}, "named in source": {"source code"}}.get(strength)
        narrowed = [t for t in pool if want and t[2] in want] or pool  # cite only the kind of evidence that supports the claim shown
        ordered = sorted(narrowed, key=lambda t: (t[2] not in STRONG and t[2] != "local configuration", t[2] != "dependency"))[:3]
        mods = sorted({ctx.module_of(t[0]["path"]) for t in it["ev"] if t[1] == here})
        out.append({"group": GROUP.get(it["kind"]), "kind": it["kind"], "technology": it["tech"], "where": where, "evidence_strength": strength,
                    "embedded": it["embedded"], "basis": basis, "modules": mods[:5], "hosts": it.get("hosts", []), "host_envs": it.get("host_envs", []),
                    "at": ["%s:%d" % (t[0]["path"], t[0]["line_start"]) for t in ordered], "_ev": [t[0] for t in ordered]})
    out.sort(key=lambda x: (GROUP_ORDER.index(x["group"]) if x["group"] in GROUP_ORDER else 99, KIND_ORDER.index(x["kind"]), {"application": 0, "a build profile only": 1, "docker-compose only": 2, "tests and docker-compose only": 3, "tests only": 4}[x["where"]], x["technology"]))
    ev, seen = [], set()
    for x in out:
        for e in x.pop("_ev"):
            if (e["path"], e["line_start"]) not in seen:
                seen.add((e["path"], e["line_start"]))
                ev.append(e)
    return out, ev


def detect_modules(ctx):
    r = ctx.repo
    dirs = ctx.module_dirs()
    out, ev = [], []
    settings_name = {}
    for f in ctx.gradle_settings:
        m = next(iter(grep_files(r, [f], r"rootProject\.name\s*=\s*[\"']([^\"']+)[\"']", 1)), None)
        if m:
            settings_name[os.path.dirname(f) or "."] = re.search(r"[\"']([^\"']+)[\"']", m["snippet"].split("=", 1)[1]).group(1)
    gm = set(ctx.gradle_modules())
    own_main = {ctx.module_of(f) for f in ctx.src_main_java}
    own_test = {ctx.module_of(f) for f in ctx.test_sources}
    for d in dirs:
        pom = "pom.xml" if d == "." else d + "/pom.xml"
        pom = pom if pom in ctx.fileset and pom in ctx.poms else None
        gfiles = [f for f in ctx.gradle if (os.path.dirname(f) or ".") == d]
        # a directory of Gradle script plugins (gradle/deps.gradle) is not a module: only a project that settings.gradle
        # includes, or one with a build.gradle(.kts) of its own, is
        if not pom and d not in gm and gfiles and not any(os.path.basename(f) in ("build.gradle", "build.gradle.kts") for f in gfiles):
            continue
        build = pom or (gfiles[0] if gfiles else None)
        kind = "maven" if pom else "gradle"
        name, role = (os.path.basename(d) if d != "." else os.path.basename(os.path.abspath(r))), None
        text = "\n".join(read_lines(r, build) or []) if build else ""
        has_children = any(x != d and (d == "." or x.startswith(d + "/")) for x in dirs)
        own_src = d in own_main
        if pom:
            t = _strip_xml(text, ("parent", "build", "profiles", "dependencies", "dependencyManagement", "properties"))
            a = re.search(r"<artifactId>\s*([^<\s$]+)\s*<", t)
            name = a.group(1) if a else name
            pk = re.search(r"<packaging>\s*(\w+)\s*<", _strip_xml(text, ("parent", "build", "profiles", "dependencyManagement")))
            pk = pk.group(1) if pk else "jar"
            if pk == "pom":
                role = "aggregator" if re.search(r"<modules>", text) else "parent / BOM"
            elif pk == "war":
                role = "web application (war)"
            elif re.search(r"spring-boot-maven-plugin|quarkus-maven-plugin|micronaut-maven-plugin", text):
                role = "application"
            else:
                role = "jar"
        elif build:
            if re.search(r"id\s*\(?\s*[\"']org\.springframework\.boot[\"']|apply\s+plugin:\s*[\"']org\.springframework\.boot[\"']|\bbootJar\b|id\s*\(?\s*[\"']application[\"']|apply\s+plugin:\s*[\"']application[\"']|^\s*application\s*\{|id\s*\(?\s*[\"']io\.quarkus[\"']|io\.micronaut\.application|io\.ktor\.plugin", text, re.M):
                role = "application"
            elif has_children and not own_src:
                role = "aggregator"
            elif re.search(r"java-library|maven-publish", text):
                role = "library"
            else:
                role = "jar" if own_src else "aggregator" if has_children else None
        else:  # a directory included by settings.gradle without its own build file
            role = "aggregator" if has_children and not own_src else None
        if not pom and d in settings_name:
            name = settings_name[d]
        if ctx._test_module(build or d + "/x") or (role != "aggregator" and d in own_test and not own_src):
            role = "tests"  # named as a test module, or it has test sources and no production sources
        out.append({"name": name, "path": d, "build": kind if build else "gradle", "role": role})
        if build and len(ev) < 60:
            ln = next((i for i, x in enumerate(read_lines(r, build) or [""], 1) if x.strip()), 1)
            ev.append(file_ev(build, ln, (read_lines(r, build) or [""])[ln - 1]))
    return out, ev


JIB_CI = re.compile(r"(?:^|[\s;&|'\"])(?:\./)?(?:gradlew?|mvnw?|_gradle|_mvn)?\s*(?:[\w:.-]+\s+)*?(?:jib(?:DockerBuild|BuildTar)?\b|jib:(?:build|dockerBuild|buildTar)\b)")


def _brace_end(lines, start):
    """Index of the line that closes the block opened on lines[start] (braces counted outside strings), or None."""
    depth, seen = 0, False
    for i in range(start, len(lines)):
        code = re.sub(r"\"[^\"]*\"|'[^']*'", "", lines[i])
        for ch in code:
            if ch == "{":
                depth += 1
                seen = True
            elif ch == "}":
                depth -= 1
        if seen and depth <= 0:
            return i
    return None


def _gradle_sub(lines, lo, hi, name):
    """(start, end) of a `name { ... }` block between lo and hi, or None."""
    for i in range(lo, hi + 1):
        if re.match(r"^\s*%s\s*\{" % name, lines[i]) and not lines[i].lstrip().startswith(("//", "*", "/*")):
            e = _brace_end(lines, i)
            return (i, e if e is not None else hi)
    return None


def _jib_value(rx, lines, lo, hi):
    """(value, line number, text) for the first literal match of rx in lines[lo..hi]. A value holding a $variable, ${property} or
    <placeholder> is not a value: the build resolves it, this scan does not."""
    for i in range(lo, hi + 1):
        if lines[i].lstrip().startswith(("//", "*", "/*")):
            continue
        m = re.search(rx, lines[i])
        if m:
            v = m.group(1).strip()
            return (None, i + 1, lines[i]) if (not v or re.search(r"[$<{]", v)) else (v, i + 1, lines[i])
    return None


def read_jib(ctx):
    """What Jib is configured to build, from Maven (<configuration><from><image>) and Gradle (jib { from { image = } }), plus
    -Djib.* properties in pipeline files and gradle.properties. Commented configuration is ignored; unresolved variables are reported
    as 'set by a variable', never as a value."""
    import bisect
    r = ctx.repo
    out = {"base_image": None, "base_image_variable": False, "target_image": None, "target_image_variable": False, "ports": [], "main_class": None, "ev": [],
           "base_image_env": None, "target_image_env": None}

    def put(key, got, ev_path):
        if not got:
            return
        v, ln, text = got
        if v is None:
            out[key + "_variable"] = True
        elif out[key] is None:
            out[key] = v
        out["ev"].append(file_ev(ev_path, ln, text))
    for pom in ctx.poms:
        lines = read_lines(r, pom) or []
        text = _strip_comments("\n".join(lines))
        if "jib-maven-plugin" not in text:
            continue
        nl = [m.start() for m in re.finditer("\n", text)]
        for _, i0, i1, _ in _elements(text, "plugin"):
            blk = text[i0:i1]
            if "jib-maven-plugin" not in blk:
                continue
            for tag, key in (("from", "base_image"), ("to", "target_image")):
                for _, j0, j1, _ in _elements(blk, tag)[:1]:
                    m = re.search(r"<image>\s*([^<]+?)\s*</image>", blk[j0:j1])
                    if m:
                        ln = bisect.bisect_left(nl, i0 + j0 + m.start()) + 1
                        v = m.group(1)
                        put(key, (None if re.search(r"[$<{]", v) else v, ln, lines[ln - 1]), pom)
            for _, j0, j1, _ in _elements(blk, "container")[:1]:
                inner = blk[j0:j1]
                for m in re.finditer(r"<port>\s*(\d+)\s*</port>", inner):
                    out["ports"].append(m.group(1))
                m = re.search(r"<mainClass>\s*([^<$\s]+)\s*</mainClass>", inner)
                if m and not out["main_class"]:
                    out["main_class"] = m.group(1)
    for g in ctx.gradle:
        lines = read_lines(r, g) or []
        for i, ln in enumerate(lines):
            if not re.match(r"^\s*jib\s*\{", ln) or ln.lstrip().startswith(("//", "*", "/*")):
                continue
            end = _brace_end(lines, i)
            end = len(lines) - 1 if end is None else end
            for name, key in (("from", "base_image"), ("to", "target_image")):
                sub = _gradle_sub(lines, i + 1, end, name)
                if sub:
                    got = _jib_value(r"\bimage\s*(?:=|\.set\()\s*[\"']([^\"']+)[\"']", lines, sub[0], sub[1]) or _jib_value(r"\bimage\s*(?:=|\.set\()\s*()\S", lines, sub[0], sub[1])
                    put(key, got, g)
                    env = re.search(r"getenv\(\s*[\"'](\w+)[\"']", got[2]) if got and got[0] is None else None
                    if env:
                        out[key + "_env"] = env.group(1)
            cont = _gradle_sub(lines, i + 1, end, "container")
            if cont:
                for j in range(cont[0], cont[1] + 1):
                    if lines[j].lstrip().startswith(("//", "*", "/*")):
                        continue
                    if re.search(r"\bports\b", lines[j]):
                        out["ports"] += re.findall(r"[\"']?(\d{2,5})[\"']?", re.sub(r"\bports\b|listOf|setOf|arrayOf", "", lines[j]))
                    m = re.search(r"mainClass\s*(?:=|\.set\()\s*[\"']([\w.$]+)[\"']", lines[j])
                    if m and not out["main_class"]:
                        out["main_class"] = m.group(1)
        for e in grep_files(r, [g], r"\bjib\.(?:from|to)\.image\s*=\s*[\"']([^\"'$]+)[\"']", 4):
            m = re.search(r"jib\.(from|to)\.image\s*=\s*[\"']([^\"'$]+)", e["snippet"])
            if m:
                key = "base_image" if m.group(1) == "from" else "target_image"
                if out[key] is None:
                    out[key] = m.group(2)
                out["ev"].append(e)
    props = [f for f in ctx.files if os.path.basename(f) in ("gradle.properties",) and not ctx._aux(f)]
    for e in grep_files(r, props + ctx.ci_files, r"jib\.(?:from|to)\.image[=\s]+[\"']?([^\s\"'$]+)", 4):
        m = re.search(r"jib\.(from|to)\.image[=\s]+[\"']?([^\s\"'$]+)", e["snippet"])
        if m:
            key = "base_image" if m.group(1) == "from" else "target_image"
            if out[key] is None:
                out[key] = m.group(2)
            out["ev"].append(e)
    out["ports"] = sorted(set(out["ports"]), key=int)
    return out


BUILD_IMAGE_CI = r".*\b(?:spring-boot:build-image|bootBuildImage)\b"
QUARKUS_EXT = re.compile(r"quarkus-container-image-(jib|docker|buildpack|openshift|s2i)\b")


def _assign(lines, lo, hi, key):
    """('value', line, text) for `key = "literal"` / `key.set("literal")` in lines[lo..hi]; (None, line, text) when the right-hand side
    is a variable, expression or ${placeholder} (never reported as a value); None when the key is absent. Comments are skipped."""
    for i in range(lo, hi + 1):
        t = lines[i]
        if t.lstrip().startswith(("//", "*", "/*")):
            continue
        m = re.search(r"\b%s\s*(?:\.set\(|=)\s*(.*)$" % re.escape(key), t)
        if m:
            q = re.match(r"([\"'])([^\"']*)\1", m.group(1).strip())
            if q and q.group(2) and not re.search(r"[$<{]", q.group(2)):
                return (q.group(2), i + 1, t)
            return (None, i + 1, t)
    return None


def _env_name(text):
    m = re.search(r"getenv\(\s*[\"'](\w+)[\"']", text or "")
    return m.group(1) if m else None


def read_spring_boot_image(ctx):
    """Spring Boot's own image build (spring-boot:build-image, bootBuildImage): name, builder, run image, publish, publish registry,
    from Maven <image> / Gradle bootBuildImage {} and the pipeline command. The spring-boot-maven-plugin alone is not an image build."""
    import bisect
    r = ctx.repo
    out = {"configured": False, "bound_to_build": False, "image_name": None, "image_name_variable": False, "image_name_env": None, "builder": None,
           "builder_variable": False, "run_image": None, "publish": None, "registry": None, "run_by": None, "ev": []}

    def take(key, got, path):
        if not got:
            return
        v, ln, text = got
        out["ev"].append(file_ev(path, ln, text))
        out["configured"] = True
        if v is None:
            out[key + "_variable"] = True if key + "_variable" in out else None
            if key == "image_name":
                out["image_name_env"] = _env_name(text)
        elif out[key] is None:
            out[key] = v
    for pom in ctx.poms:
        lines = read_lines(r, pom) or []
        text = _strip_comments("\n".join(lines))
        if "spring-boot-maven-plugin" not in text:
            continue
        nl = [m.start() for m in re.finditer("\n", text)]
        for _, i0, i1, _ in _elements(text, "plugin"):
            blk = text[i0:i1]
            if "spring-boot-maven-plugin" not in blk:
                continue
            ln_of = lambda off: bisect.bisect_left(nl, i0 + off) + 1
            g = re.search(r"<goal>\s*build-image\s*</goal>", blk)
            if g:
                out["bound_to_build"] = out["configured"] = True
                out["ev"].append(file_ev(pom, ln_of(g.start()), lines[ln_of(g.start()) - 1]))
            for _, j0, j1, _ in _elements(blk, "image")[:1]:
                inner = blk[j0:j1]
                out["configured"] = True
                for tag, key in (("name", "image_name"), ("builder", "builder"), ("runImage", "run_image")):
                    m = re.search(r"<%s>\s*([^<]+?)\s*</%s>" % (tag, tag), inner)
                    if m:
                        ln = ln_of(j0 + m.start())
                        v = m.group(1)
                        take(key, (None if re.search(r"[$<{]", v) else v, ln, lines[ln - 1]), pom)
                m = re.search(r"<publish>\s*(true|false)\s*</publish>", inner)
                if m:
                    out["publish"] = m.group(1) == "true"
                    out["ev"].append(file_ev(pom, ln_of(j0 + m.start()), lines[ln_of(j0 + m.start()) - 1]))
            for _, j0, j1, _ in _elements(blk, "publishRegistry")[:1]:
                m = re.search(r"<url>\s*([^<$\s]+)\s*</url>", blk[j0:j1])
                if m:
                    out["registry"] = m.group(1)
                    out["ev"].append(file_ev(pom, ln_of(j0 + m.start()), lines[ln_of(j0 + m.start()) - 1]))
    hdr = re.compile(r"^(?!\s*(?://|\*|/\*)).*\b(?:bootBuildImage|BootBuildImage)\b.*\{\s*$")
    for g in ctx.gradle:
        lines = read_lines(r, g) or []
        for i, ln in enumerate(lines):
            if not hdr.match(ln):
                continue
            end = _brace_end(lines, i)
            end = len(lines) - 1 if end is None else end
            out["configured"] = True
            out["ev"].append(file_ev(g, i + 1, ln))
            take("image_name", _assign(lines, i + 1, end, "imageName"), g)
            take("builder", _assign(lines, i + 1, end, "builder"), g)
            take("run_image", _assign(lines, i + 1, end, "runImage"), g)
            for j in range(i + 1, end + 1):
                m = re.search(r"\bpublish\s*(?:\.set\(|=)\s*(true|false)", lines[j])
                if m and not lines[j].lstrip().startswith(("//", "*", "/*")):
                    out["publish"] = m.group(1) == "true"
            sub = _gradle_sub(lines, i + 1, end, "docker")
            if sub:
                pr = _gradle_sub(lines, sub[0] + 1, sub[1], "publishRegistry")
                u = _assign(lines, pr[0], pr[1], "url") if pr else None
                if u and u[0]:
                    out["registry"] = u[0]
                    out["ev"].append(file_ev(g, u[1], u[2]))
    cands = []
    for f in ctx.ci_files:
        for e in find_lines(r, f, r"spring-boot:build-image|bootBuildImage", 10, continuation=True, flags=0):
            if at_command_position(e["snippet"], BUILD_IMAGE_CI):
                cands.append(e)
    via = "the pipeline" if cands else None
    if not cands:
        for f in ctx.ci_scripts():
            for e in find_lines(r, f, r"spring-boot:build-image|bootBuildImage", 5, continuation=True, flags=0):
                if at_command_position(e["snippet"], BUILD_IMAGE_CI):
                    cands.append(e)
                    via = "a script the pipeline calls"
                    break
    if cands:
        out["configured"] = True
        out["run_by"] = via
        out["ev"].append(cands[0])
        m = re.search(r"--imageName[= ]\s*[\"']?([^\s\"']+)", cands[0]["snippet"])
        if m and out["image_name"] is None and "$" not in m.group(1):
            out["image_name"] = m.group(1)
        elif m and "$" in m.group(1):
            out["image_name_variable"] = True
    return out


def read_quarkus_image(ctx):
    """Quarkus container-image extension and its configuration (quarkus.container-image.*, quarkus.jib.*, quarkus.docker.*), from
    application.properties / application.yml (unprefixed and %prod only: %dev and %test never build the production image) and
    -Dquarkus.container-image.* flags in pipeline files. The extension alone does not build an image: quarkus.container-image.build
    defaults to false."""
    r = ctx.repo
    ext = grep_files(r, ctx.build_files, r"quarkus-container-image-(?:jib|docker|buildpack|openshift|s2i)\b", 4)
    if not ext:
        return None
    builders = sorted({QUARKUS_EXT.search(e["snippet"]).group(1) for e in ext if QUARKUS_EXT.search(e["snippet"])})
    out = {"builder": "+".join(builders) or None, "enabled": None, "enabled_by": None, "push": None, "image": None, "registry": None, "group": None, "name": None,
           "tag": None, "base_image": None, "ports": [], "dockerfile": None, "set_by_variable": [], "run_by": None, "ev": list(ext[:1])}
    want = {"quarkus.container-image.build": "build", "quarkus.container-image.push": "push", "quarkus.container-image.image": "image",
            "quarkus.container-image.registry": "registry", "quarkus.container-image.group": "group", "quarkus.container-image.name": "name",
            "quarkus.container-image.tag": "tag", "quarkus.jib.base-jvm-image": "base_image", "quarkus.jib.ports": "ports",
            "quarkus.docker.dockerfile-jvm-path": "dockerfile"}
    cfg = {}
    for f in ctx.props:
        lines = read_lines(r, f) or []
        for key, val, i in flatten(lines, "yaml" if f.endswith((".yml", ".yaml")) else "props"):
            m = re.match(r"%([\w-]+)\.(.*)", key)
            prof, k = (m.group(1), m.group(2)) if m else (None, key)
            if k not in want or prof not in (None, "prod"):
                continue
            slot = want[k]
            if prof is None and slot in cfg and cfg[slot][3] == "prod":
                continue  # a %prod value wins over the unprefixed one
            cfg[slot] = (val, f, i, prof, lines[i - 1])
    for slot, (val, f, i, prof, text) in cfg.items():
        out["ev"].append(file_ev(f, i, text))
        if not val or re.search(r"[$<{]", val):
            out["set_by_variable"].append(slot)
            continue
        if slot == "build":
            out["enabled"] = val.lower() == "true"
            out["enabled_by"] = "configuration"
        elif slot == "push":
            out["push"] = val.lower() == "true"
        elif slot == "ports":
            out["ports"] = re.findall(r"\d{2,5}", val)
        else:
            out[slot] = val
    for e in grep_files(r, ctx.ci_files + [x for x in ctx.files if x in (".mvn/maven.config", ".mvn/jvm.config")], r"quarkus\.container-image\.(?:build|push)=(?:true|false)", 6, flags=0):
        out["ev"].append(e)
        for m in re.finditer(r"quarkus\.container-image\.(build|push)=(true|false)", e["snippet"]):
            if m.group(1) == "build":
                out["enabled"] = m.group(2) == "true"
                out["enabled_by"] = "pipeline flag"
                out["run_by"] = "the pipeline" if e["path"] in ctx.ci_files else None
            else:
                out["push"] = m.group(2) == "true"
    return out


def detect_container(ctx):
    """(fact, registry references): how an image is built (Dockerfile, Jib, Spring Boot build-image, Quarkus container-image)."""
    from detectors.resilience import dockerfiles
    r = ctx.repo
    dfs = dockerfiles(ctx)
    bases, ev = [], []
    for f in dfs[:10]:
        stages = set()
        for i, ln in enumerate(read_lines(r, f) or [], 1):
            m = re.match(r"^\s*FROM\s+(?:--platform=\S+\s+)?(\S+)(?:\s+AS\s+(\S+))?", ln, re.I)
            if not m:
                continue
            img = m.group(1)
            if m.group(2):
                stages.add(m.group(2).lower())
            if img.lower() in stages or img.lower() == "scratch" or "$" in img:
                continue
            if img not in bases:
                bases.append(img)
            if len(ev) < 6:
                ev.append(file_ev(f, i, ln))
    compose = [f for f in ctx.deploy_files if re.match(r"(?i)(?:docker-)?compose[^/]*\.ya?ml$", os.path.basename(f))]
    jib_plugin = grep_files(r, ctx.build_files, r"jib-maven-plugin|com\.google\.cloud\.tools\.jib", 3)
    for f in dfs[:3]:
        if not any(e["path"] == f for e in ev):
            ev.append(file_ev(f, 1, (read_lines(r, f) or [""])[0]))
    jib = read_jib(ctx) if jib_plugin else None
    sb = read_spring_boot_image(ctx)
    qk = read_quarkus_image(ctx)
    refs, plugins = [], []
    if jib:
        plugins.append("jib")
        if jib["base_image"] and jib["base_image"] not in bases:
            bases.insert(0, jib["base_image"])
        ev = jib["ev"][:4] + ev
        refs += [(jib["target_image"], e) for e in jib["ev"][:1] if jib["target_image"]]
    if sb["configured"]:
        plugins.append("spring-boot build-image")
        if sb["run_image"] and sb["run_image"] not in bases:
            bases.insert(0, sb["run_image"])
        ev = sb["ev"][:4] + ev
        refs += [(t, sb["ev"][0]) for t in (sb["image_name"], sb["registry"]) if t and sb["ev"]]
    if qk:
        plugins.append("quarkus-container-image-" + (qk["builder"] or ""))
        if qk["enabled"] and qk["base_image"] and qk["base_image"] not in bases:
            bases.insert(0, qk["base_image"])
        ev = (qk["ev"][:4] if qk["enabled"] is not None or qk["set_by_variable"] else qk["ev"][:1]) + ev
        refs += [(t, qk["ev"][-1]) for t in (qk["image"], qk["registry"]) if t]
    ev += jib_plugin
    for f in compose[:2]:
        ev.append(file_ev(f, 1, (read_lines(r, f) or [""])[0]))  # last: compose says how it runs locally, not that an image is built
    built = bool(dfs or jib_plugin or sb["configured"] or (qk and qk["enabled"]))
    jval = None
    if jib:
        run = [e for e in grep_files(r, ctx.ci_files, JIB_CI.pattern, 2) if re.search(r"jib", e["snippet"])]
        via = "the pipeline" if run else ("a script the pipeline calls" if grep_files(r, ctx.ci_scripts(), JIB_CI.pattern, 1) else None)
        if run:
            ev += run[:1]
        jval = {"base_image": jib["base_image"], "base_image_set_by_variable": jib["base_image_variable"], "target_image": jib["target_image"],
                "target_image_set_by_variable": jib["target_image_variable"], "base_image_env": jib["base_image_env"], "target_image_env": jib["target_image_env"], "ports": jib["ports"], "main_class": jib["main_class"], "run_by": via}
    sval = None
    if sb["configured"]:
        sval = {k: sb[k] for k in ("image_name", "image_name_variable", "image_name_env", "builder", "builder_variable", "run_image", "publish", "registry", "bound_to_build", "run_by")}
    qval = None
    if qk:
        qval = {k: qk[k] for k in ("builder", "enabled", "enabled_by", "push", "image", "registry", "group", "name", "tag", "base_image", "ports", "dockerfile", "set_by_variable", "run_by")}
    seen, uev = set(), []
    for e in ev:
        if (e["path"], e["line_start"]) not in seen:
            seen.add((e["path"], e["line_start"]))
            uev.append(e)
    return (fact({"image_build": built, "dockerfiles": dfs[:10], "base_images": bases[:10], "compose_files": compose[:5],
                  "build_plugins": plugins, "jib": jval, "spring_boot": sval, "quarkus": qval},
                 "CONFIRMED" if (built or compose or qk) else "NOT_FOUND", uev,
                 None if (built or compose or qk) else "no Dockerfile, image-build plugin or compose file found"), refs)


# Where the application is deployed. Only a file that describes a deployment, or a pipeline command that performs one, counts:
# a cloud SDK dependency says the application USES that cloud's services, not that it runs there.
HOST_FILES = [  # (path regex on the repo-relative file, content regex or None, target)
    (r"(?:^|/)Chart\.ya?ml$", None, "Helm chart"),
    (r"(?:^|/)kustomization\.ya?ml$", None, "Kustomize (Kubernetes)"),
    (r"(?:^|/)serverless\.ya?ml$", r"^\s*name:\s*aws\b", "AWS Lambda (Serverless Framework)"),
    (r"(?:^|/)(?:template|sam)\.ya?ml$", r"AWS::Serverless", "AWS Lambda (SAM)"),
    (r"(?:^|/)Dockerrun\.aws\.json$", None, "AWS Elastic Beanstalk"),
    (r"(?:^|/)\.ebextensions/[^/]+\.config$", None, "AWS Elastic Beanstalk"),
    (r"(?:^|/)(?:[\w.-]*task-?def(?:inition)?[\w.-]*)\.json$", r"containerDefinitions", "AWS ECS"),
    (r"(?:^|/)appspec\.ya?ml$", r"^\s*(?:version|os|Resources):", "AWS CodeDeploy"),
    (r"(?:^|/)app\.ya?ml$", r"^\s*(?:runtime|entrypoint|service):", "Google App Engine"),
    (r"(?:^|/)(?:service|knative)[\w.-]*\.ya?ml$", r"serving\.knative\.dev", "Google Cloud Run / Knative"),
    (r"(?:^|/)Procfile$", None, "Heroku (Procfile)"),
    (r"(?:^|/)heroku\.yml$", None, "Heroku"),
    (r"(?:^|/)fly\.toml$", None, "Fly.io"),
    (r"(?:^|/)manifest\.ya?ml$", r"^\s*applications:", "Cloud Foundry"),
    (r"(?:^|/)[\w.-]+\.nomad(?:\.hcl)?$", r"^\s*job\s+\"", "Nomad"),
    (r"(?:^|/)[\w.-]+\.hcl$", r"^\s*job\s+\"", "Nomad"),
]
K8S_KIND = r"^\s*kind:\s*(Deployment|StatefulSet|DaemonSet|CronJob|Rollout|Job|Pod)\s*$"
HOST_CI = [  # command in a pipeline file that performs a deployment; it must be the command, not text inside another command
    (r"kubectl\s+(?:apply|rollout|set\s+image|create|replace|patch)\b", "Kubernetes", "kubectl"),
    (r"helm\s+(?:upgrade|install)\b", "Kubernetes", "Helm"),
    (r"nomad\s+(?:job\s+run|run)\b", "Nomad", "nomad"),
    (r"aws\s+ecs\s+(?:update-service|run-task|register-task-definition)\b|ecs-deploy\b|uses:\s*[\w./-]*amazon-ecs-deploy-task-definition", "AWS ECS", "aws ecs"),
    (r"aws\s+lambda\s+update-function-code\b|sam\s+deploy\b|(?:serverless|sls)\s+deploy\b", "AWS Lambda", "deploy command"),
    (r"eb\s+deploy\b|aws\s+elasticbeanstalk\s+update-environment", "AWS Elastic Beanstalk", "eb"),
    (r"gcloud\s+run\s+deploy\b", "Google Cloud Run", "gcloud"),
    (r"gcloud\s+app\s+deploy\b", "Google App Engine", "gcloud"),
    (r"az\s+(?:webapp|functionapp|containerapp)\s+(?:deploy|up|update|create)\b|task:\s*Azure(?:WebApp|FunctionApp|ContainerApps)@", "Azure (App Service / Functions / Container Apps)", "az"),
    (r"cf\s+push\b", "Cloud Foundry", "cf"),
    (r"git\s+push\s+heroku\b|heroku\s+container:release\b", "Heroku", "heroku"),
    (r"(?:flyctl|fly)\s+deploy\b", "Fly.io", "flyctl"),
]
_PREFIX = re.compile(r"^\s*(?:-\s+)?(?:(?:run|script|command|entrypoint|cmd):\s*)?(?:[|>][+-]?\s*)?(?:(?:sh|bat|pwsh|powershell)\s*\(?\s*(?:script\s*:\s*)?[\"']{1,3})?")
_WRAP = re.compile(r"^(?:sudo|exec|time|then|do|else|if|!|\$)\s+")
_NOT_A_COMMAND = re.compile(r"(?:echo|printf|cat|grep|sed|awk|curl|wget|man|which|type)\b")


def at_command_position(text, rx):
    """True when `rx` is the command a pipeline line runs: at the start of the line's command, or after && ; | ( . A mention inside
    echo/printf/grep, a quoted string or a comment is not a deployment."""
    t = _PREFIX.sub("", text, count=1).strip().strip("'\"")
    for seg in re.split(r"&&|\|\||;|\||\(|`|\$\(", t):
        seg = _WRAP.sub("", seg.strip())
        if _NOT_A_COMMAND.match(seg):
            continue
        if re.match(rx, seg):
            return True
    return False


REGISTRIES = [
    (r"\b\d{12}\.dkr\.ecr\.[\w-]+\.amazonaws\.com", "AWS ECR"),
    (r"\b(?:[\w-]+\.)?gcr\.io/|\b[\w-]+-docker\.pkg\.dev/", "Google Container / Artifact Registry"),
    (r"\b[\w-]+\.azurecr\.io/", "Azure Container Registry"),
]


K8S_FAMILY = {"Helm chart": "Helm", "Kustomize (Kubernetes)": "Kustomize"}


def detect_hosting(ctx, refs=()):
    """[{target, role, via[], basis[], at[]}] and evidence. role is `deployment target` (a descriptor or a pipeline deploy command)
    or `image registry` (only says where images are stored, not where they run). Helm, Kustomize, manifests and kubectl all say
    Kubernetes; they are one target, shown with what names it."""
    r = ctx.repo
    found, ev = {}, []

    def add(target, role, basis, e, via):
        it = found.setdefault((target, role), {"target": target, "role": role, "basis": set(), "via": set(), "ev": []})
        it["basis"].add(basis)
        it["via"].add(via)
        if len(it["ev"]) < 3:
            it["ev"].append(e)
    cand = [f for f in ctx.files if not ctx._aux(f) and not ctx._test_module(f)]
    for f in cand:
        for prx, crx, target in HOST_FILES:
            if re.search(prx, f):
                plat = "Kubernetes" if target in K8S_FAMILY else target
                via = K8S_FAMILY.get(target, os.path.basename(f))
                if crx is None:
                    add(plat, "deployment target", "deployment file", file_ev(f, 1, (read_lines(r, f) or [""])[0]), via)
                else:
                    hit = grep_files(r, [f], crx, 1)
                    if hit:
                        add(plat, "deployment target", "deployment file", hit[0], via)
                break
    for f in ctx.deploy_files:
        if f.endswith((".yml", ".yaml")) and not re.match(r"(?i)(?:docker-)?compose", os.path.basename(f)):
            hit = grep_files(r, [f], K8S_KIND, 1)
            if hit:
                kind = re.search(K8S_KIND, hit[0]["snippet"]).group(1)
                add("Kubernetes", "deployment target", "manifest", hit[0], "%s manifest" % kind)
    for rx, target, via in HOST_CI:
        n = 0
        for f in ctx.ci_files:
            for e in find_lines(r, f, rx, 20, continuation=True, flags=0):
                if at_command_position(e["snippet"], rx) and n < 2:
                    add(target, "deployment target", "pipeline command", e, via + " (pipeline)")
                    n += 1
    reg_files = [f for f in ctx.files if not ctx._aux(f) and (os.path.basename(f).lower().startswith("dockerfile") or f in ctx.ci_files or f in ctx.deploy_files
                                                              or f in ctx.build_files)]
    for rx, target in REGISTRIES:
        for e in grep_files(r, reg_files, rx, 1, flags=re.I):
            add(target, "image registry", "image reference", e, "image reference")
    for text, e in refs:  # an image name or registry named by the image build (Jib to, Spring publishRegistry, quarkus.container-image.registry)
        for rx, target in REGISTRIES:
            if re.search(rx, text if text.endswith("/") else text + "/", re.I):
                add(target, "image registry", "image reference", e, "image reference")
    out = []
    for (t, role), it in sorted(found.items(), key=lambda kv: (kv[0][1] != "deployment target", kv[0][0])):
        out.append({"target": t, "role": role, "via": sorted(it["via"]), "basis": sorted(it["basis"]),
                    "at": ["%s:%d" % (e["path"], e["line_start"]) for e in it["ev"]]})
        ev.extend(it["ev"])
    seen, uniq = set(), []
    for e in ev:
        if (e["path"], e["line_start"]) not in seen:
            seen.add((e["path"], e["line_start"]))
            uniq.append(e)
    return out, uniq


def detect(ctx) -> dict:
    out = {}
    (items, ev), (libs, lev), counts = detect_dependencies(ctx)
    out["http_client_libraries"] = fact([{"technology": x["technology"], "where": x["where"]} for x in libs], "CONFIRMED" if libs else "NOT_FOUND", lev,
                                        "how the application calls other services; a client library says nothing about WHICH services" if libs else
                                        "no known HTTP client library declared")
    scanned = "searched %d build file(s), %d configuration file(s), %d deployment file(s) and %d source file(s)" % (
        counts["build_files"], counts["configuration_files"], counts["deployment_files"], counts["source_files"])
    more = "; %d further configured endpoint(s) are not listed" % counts["endpoints_not_listed"] if counts["endpoints_not_listed"] else ""
    out["external_dependencies"] = fact(items, "CONFIRMED" if items else "NOT_FOUND", ev,
                                        ("each item is read from the cited files; evidence_strength 'declared' means a dependency exists but no connection setting was found, "
                                         "'Endpoint:' items are addresses named in configuration (what runs there is not known); hosts are not resolved; " + scanned + more) if items else
                                        "none found: " + scanned)
    mods, mev = detect_modules(ctx)
    out["module_list"] = fact(mods, "CONFIRMED" if mods else "NOT_FOUND", mev,
                              "directories holding a build file or included by settings.gradle; role is read from the build file (evidence cites the first %d)" % 60 if mods else
                              "no pom.xml or build.gradle(.kts) found")
    out["container"], refs = detect_container(ctx)
    hosts, hev = detect_hosting(ctx, refs)
    remote = ctx.unresolved_ci_includes()
    server_side = [f for f in ctx.ci_files if re.search(r"(?i)jenkins|teamcity", f)]
    if hosts:
        out["hosting"] = fact(hosts, "CONFIRMED", hev, "where it is deployed, read only from deployment descriptors and pipeline deploy commands; an image registry says where "
                              "images are stored, not where they run; a descriptor in a repository with several modules may not belong to this module; a cloud SDK dependency is never "
                              "taken as a deployment target")
    elif remote or server_side:
        why = ("pipeline templates held elsewhere (%d include(s)) may deploy it" % len(remote)) if remote else "Jenkins / TeamCity job definitions held on the server may deploy it"
        cite = remote[:1] or [file_ev(server_side[0], 1, (read_lines(ctx.repo, server_side[0]) or [""])[0])]
        out["hosting"] = fact([], "UNKNOWN", cite, "no deployment descriptor or deploy command in the files read, but " + why + ": not visible offline")
    else:
        out["hosting"] = fact([], "NOT_FOUND", [], "no deployment descriptor or pipeline deploy command for a known platform in this repository; it may be defined elsewhere")
    return out
