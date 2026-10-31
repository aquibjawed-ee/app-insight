"""Sample portfolio built on disk per test run (git-initialised temp repositories). Each application is chosen to exercise
positive, negative, ambiguous and missing-evidence cases; the comments say which."""
import os
import subprocess
import tempfile

POM = """<project>
  <parent><groupId>org.springframework.boot</groupId><artifactId>spring-boot-starter-parent</artifactId><version>%(boot)s</version></parent>
  <groupId>com.shop</groupId><artifactId>%(artifact)s</artifactId>
  <properties><java.version>%(java)s</java.version></properties>
  <dependencies>
%(deps)s
  </dependencies>
  <build><plugins><plugin><artifactId>jacoco-maven-plugin</artifactId></plugin></plugins></build>
</project>
"""


def dep(art, group="org.springframework.boot", scope=None):
    return "    <dependency><groupId>%s</groupId><artifactId>%s</artifactId>%s</dependency>" % (
        group, art, "<scope>%s</scope>" % scope if scope else "")


def pom(artifact, boot, java, deps):
    return POM % {"artifact": artifact, "boot": boot, "java": java, "deps": "\n".join(deps)}


ORDERS = {
    "pom.xml": pom("orders-service", "2.7.18", "11", [
        dep("spring-boot-starter-web"), dep("spring-boot-starter-data-jpa"), dep("postgresql", "org.postgresql"),
        dep("spring-kafka", "org.springframework.kafka"), dep("spring-cloud-starter-openfeign", "org.springframework.cloud"),
        dep("flyway-core", "org.flywaydb"),
        dep("h2", "com.h2database", "test"),  # NEGATIVE: a test-only database is not a dependency of the application
        dep("spring-boot-starter-test", scope="test")]),
    "src/main/resources/application.yml": """spring:
  application:
    name: orders-service
  datasource:
    url: jdbc:postgresql://orders-db.internal:5432/orders
  kafka:
    bootstrap-servers: kafka-1.internal:9092
payments:
  base-url: https://api.acme-pay.io/v2
orders:
  topic: orders.created
""",
    "src/main/java/com/shop/orders/OrderController.java": """package com.shop.orders;
import org.springframework.web.bind.annotation.*;
@RestController
@RequestMapping("/api/orders")
public class OrderController {
    @GetMapping("/{id}")
    public Order get(@PathVariable Long id) { return null; }
    @PostMapping
    public Order create(@RequestBody Order o) { return null; }
    @DeleteMapping("/{id}")
    public void delete(@PathVariable Long id) {}
    // @GetMapping("/secret")      NEGATIVE: commented out, not an endpoint
    @GetMapping(Paths.EXPORT)   // NEGATIVE-ish: path is a constant that cannot be found: stays out, listed as not-a-relationship
    public String export() { return ""; }
}
""",
    "src/main/java/com/shop/orders/InventoryClient.java": """package com.shop.orders;
import org.springframework.cloud.openfeign.FeignClient;
import org.springframework.web.bind.annotation.*;
@FeignClient(name = "inventory-service")
public interface InventoryClient {
    @GetMapping("/api/stock/{sku}")
    Stock stock(@PathVariable String sku);
    @PostMapping("/api/stock/reserve")
    Reservation reserve(@RequestBody Reserve r);
    @GetMapping("/api/stock/legacy")   // MISMATCH: inventory-service does not expose this
    Stock legacy();
}
""",
    "src/main/java/com/shop/orders/LoyaltyClient.java": """package com.shop.orders;
@FeignClient("loyalty-service")   // UNRESOLVED: no application in the portfolio answers to this name
public interface LoyaltyClient {
    @PostMapping("/points")
    void award(@RequestBody Points p);
}
""",
    "src/main/java/com/shop/orders/NotifierClient.java": """package com.shop.orders;
@FeignClient(name = "notifier")   // AMBIGUOUS: two applications are called `notifier`
public interface NotifierClient {
    @PostMapping("/send")
    void send(@RequestBody Msg m);
}
""",
    "src/main/java/com/shop/orders/ReportingClient.java": """package com.shop.orders;
@FeignClient(name = "reporting")  // WEAK: only a repository named `reporting` exists; a repository name is not an identity
public interface ReportingClient {
    @GetMapping("/daily")
    Report daily();
}
""",
    "src/main/java/com/shop/orders/GhostClient.java": """package com.shop.orders;
@FeignClient(name = "ghost")   // declared but never referenced anywhere: low confidence
public interface GhostClient {
    @GetMapping("/boo")
    String boo();
}
""",
    "src/main/java/com/shop/orders/OrderService.java": """package com.shop.orders;
import org.springframework.beans.factory.annotation.Value;
import org.springframework.kafka.core.KafkaTemplate;
import org.springframework.web.client.RestTemplate;
@Service
public class OrderService {
    private static final String TOPIC_AUDIT = "orders.audit";
    @Value("${payments.base-url}") private String paymentsUrl;
    private final InventoryClient inventory; private final LoyaltyClient loyalty; private final NotifierClient notifier;
    private final ReportingClient reporting; private final KafkaTemplate<String, String> kafkaTemplate;
    private final RestTemplate restTemplate; private final OrderRepository repo; private final Mailer mailer;
    void place(Order o) {
        inventory.reserve(null);
        kafkaTemplate.send("orders.created", o.id());          // literal topic
        kafkaTemplate.send(TOPIC_AUDIT, o.id());               // constant topic
        kafkaTemplate.send(topicFor(o), o.id());               // computed: unresolved
        restTemplate.postForObject(paymentsUrl + "/charges", o, String.class);   // @Value property resolved from configuration
        restTemplate.getForObject("http://localhost:8080/health", String.class);  // NEGATIVE: local address
        log.info("see http://wiki.internal/orders for details");                // NEGATIVE: log text
        log.debug("http://audit.internal/v1/events", RestTemplate.class);        // NEGATIVE: a URL printed by a log call that mentions a client type
        mailer.send("welcome@shop.example");                                    // NEGATIVE: send() on something that is not a messaging template
        repo.save(o);
    }
    /**
     * @KafkaListener(topics = "ghost.topic")   NEGATIVE: javadoc
     */
    void doc() {}
}
""",
    "src/main/java/com/shop/orders/OrderRepository.java": """package com.shop.orders;
public interface OrderRepository extends JpaRepository<Order, Long> {}
""",
    "src/main/java/com/shop/orders/Order.java": "package com.shop.orders;\nimport javax.persistence.Entity;\nimport javax.persistence.Table;\n@Entity\n@Table(name = \"orders\")\npublic class Order { Long id; Long id() { return id; } }\n",
    "src/main/java/com/shop/orders/Customers.java": """package com.shop.orders;
@Service class Customers { private final LoyaltyClient l; private final NotifierClient n; private final ReportingClient r; private final GhostClientHolder h; }
""",
    "deploy/k8s/orders.yaml": """apiVersion: apps/v1
kind: Deployment
metadata:
  name: orders-service
  namespace: shop
spec:
  template:
    spec:
      containers:
        - name: app
          image: registry.example.org/shop/orders-service:1.0.0
---
apiVersion: v1
kind: Service
metadata:
  name: orders-service
  namespace: shop
spec:
  ports:
    - port: 80
""",
    "src/test/java/com/shop/orders/OrderControllerTest.java": """package com.shop.orders;
@WebMvcTest(OrderController.class)
class OrderControllerTest {
    @Test void getsOrder() throws Exception {
        mockMvc.perform(get("/api/orders/1")).andExpect(status().isOk());
    }
    @Test void createsOrder() throws Exception {
        mockMvc.perform(post("/api/orders")).andReturn();
    }
}
""",
    "src/test/java/com/shop/orders/OrderRepositoryTest.java": """package com.shop.orders;
@DataJpaTest
class OrderRepositoryTest {
    @Autowired OrderRepository repo;
    @Test void saves() { assertThat(repo.save(new Order())).isNotNull(); }
}
""",
    ".gitlab-ci.yml": "test:\n  stage: test\n  script:\n    - mvn verify\n",
}

INVENTORY = {
    "build.gradle.kts": """plugins { id("org.springframework.boot") version "3.2.4"; kotlin("jvm") version "1.9.23"; jacoco }
java { toolchain { languageVersion.set(JavaLanguageVersion.of(17)) } }
dependencies {
    implementation("org.springframework.boot:spring-boot-starter-web")
    implementation("org.springframework.kafka:spring-kafka")
    implementation("org.springframework.boot:spring-boot-starter-data-redis")
    implementation("org.springframework.boot:spring-boot-starter-jdbc")
    implementation("org.postgresql:postgresql")
}
""",
    "settings.gradle.kts": 'rootProject.name = "inventory"\n',
    "src/main/resources/application.yml": """spring:
  application:
    name: inventory-service
  datasource:
    url: jdbc:postgresql://inventory-db.internal:5432/inventory
  kafka:
    bootstrap-servers: kafka-1.internal:9092
  data:
    redis:
      host: cache.internal
""",
    "src/main/kotlin/com/shop/inventory/StockController.kt": """package com.shop.inventory
@RestController
@RequestMapping("/api/stock")
class StockController(private val svc: StockService) {
    @GetMapping("/{sku}")
    fun stock(@PathVariable sku: String): Stock = svc.find(sku)
    @PostMapping("/reserve")
    fun reserve(@RequestBody r: Reserve): Reservation = svc.reserve(r)
}
""",
    "src/main/kotlin/com/shop/inventory/OrderEvents.kt": """package com.shop.inventory
@Component
class OrderEvents(private val template: KafkaTemplate<String, String>, private val jdbc: JdbcTemplate) {
    @KafkaListener(topics = ["orders.created"], groupId = "inventory")
    fun onOrder(msg: String) { jdbc.update("update stock set qty = qty - 1"); template.send("stock.reserved", msg) }
    fun report() = jdbc.queryForList("select * from stock")
}
""",
    "deploy/k8s/inventory.yaml": """apiVersion: v1
kind: Service
metadata:
  name: inventory-service
  namespace: shop
---
apiVersion: apps/v1
kind: Deployment
metadata:
  name: inventory-service
  namespace: shop
spec:
  replicas: 2
""",
    "src/test/kotlin/com/shop/inventory/StockControllerTest.kt": """package com.shop.inventory
@WebMvcTest(StockController::class)
class StockControllerTest { @Test fun stock() { mockMvc.perform(get("/api/stock/abc")).andExpect(status().isOk) } }
""",
}

BILLING = {
    "pom.xml": pom("billing-service", "2.3.12.RELEASE", "8", [
        dep("spring-boot-starter-web"), dep("spring-kafka", "org.springframework.kafka"), dep("postgresql", "org.postgresql"),
        dep("spring-boot-starter-jdbc"),
        dep("kafka-clients", "org.apache.kafka")]),  # declared only: nothing is published or consumed through it directly
    "src/main/resources/application.properties": """spring.application.name=billing-service
spring.datasource.url=jdbc:postgresql://orders-db.internal:5432/orders
spring.kafka.bootstrap-servers=kafka-1.internal:9092
billing.topic=orders.created
""",
    "src/main/java/com/shop/billing/OrderConsumer.java": """package com.shop.billing;
import javax.xml.bind.JAXBContext;
@Component
public class OrderConsumer {
    @KafkaListener(topics = "${billing.topic}")
    public void on(String m) { jdbcTemplate.update("insert into invoices values (?)", m); }
}
""",
}

NOTIFIER_A = {
    "pom.xml": pom("notifier-a", "3.1.5", "17", [dep("spring-boot-starter-web")]),
    "src/main/resources/application.yml": "spring:\n  application:\n    name: notifier\n",
    "src/main/java/n/N.java": "package n;\n@RestController\nclass N { @PostMapping(\"/send\") void send() {} }\n",
}
NOTIFIER_B = {
    "pom.xml": pom("notifier-b", "3.1.5", "17", [dep("spring-boot-starter-web")]),
    "src/main/resources/application.yml": "spring:\n  application:\n    name: notifier\n",
    "src/main/java/n/N.java": "package n;\n@RestController\nclass N { @PostMapping(\"/send\") void send() {} }\n",
}
REPORTING = {   # directory name `reporting`, no strong identity key: only a weak name match is possible
    "pom.xml": pom("legacy-reports", "2.7.18", "11", [dep("spring-boot-starter-web"), dep("spring-kafka", "org.springframework.kafka")]),
    "src/main/resources/application.yml": "spring:\n  kafka:\n    bootstrap-servers: kafka-legacy.internal:9092\n  redis:\n    host: cache2.internal\n",
    "src/main/java/r/R.java": """package r;
@RestController
class R { @GetMapping("/daily") String daily() { return ""; } 
  @KafkaListener(topics = "orders.created") void on(String m) {} }
""",
}

PORTFOLIO = {"orders-service": ORDERS, "inventory-service": INVENTORY, "billing-service": BILLING, "notifier-a": NOTIFIER_A,
             "notifier-b": NOTIFIER_B, "reporting": REPORTING}


def make_repo(root, name, files):
    d = os.path.join(root, name)
    os.makedirs(d, exist_ok=True)
    subprocess.run(["git", "init", "-q"], cwd=d, check=True)
    for rel, text in files.items():
        p = os.path.join(d, rel)
        os.makedirs(os.path.dirname(p), exist_ok=True)
        with open(p, "w") as fh:
            fh.write(text)
    return d


def make_portfolio(root=None, names=None):
    root = root or tempfile.mkdtemp(prefix="portfolio-")
    return root, {n: make_repo(root, n, f) for n, f in PORTFOLIO.items() if names is None or n in names}

# Kotlin client declared with an escaped placeholder, URL held in configuration
KOTLIN_CLIENT = {
    "build.gradle.kts": 'plugins { id("org.springframework.boot") version "3.2.4"; kotlin("jvm") version "1.9.23" }\ndependencies { implementation("org.springframework.cloud:spring-cloud-starter-openfeign") }\n',
    "src/main/resources/application.yml": "spring:\n  application:\n    name: kclient\nloyalty:\n  api:\n    url: https://loyalty.partner.io/v1\n",
    "src/main/kotlin/k/Loyalty.kt": '''package k
@FeignClient(name = "loyalty", url = "\\${loyalty.api.url}")
interface LoyaltyApi {
    @GetMapping("/points/{id}") fun points(@PathVariable id: String): Points
}
@FeignClient(name = "other", url = "\\${missing.api.url}")
interface OtherApi { @GetMapping("/x") fun x(): String }
@Service class U(private val l: LoyaltyApi, private val o: OtherApi)
''',
}

# ---- resilience fixtures -------------------------------------------------------------------------------------------------
HA_K8S = {   # everything in place, on EKS
    "pom.xml": pom("ha-service", "3.2.4", "17", [dep("spring-boot-starter-web")]),
    "deploy/k8s/app.yaml": """apiVersion: apps/v1
kind: Deployment
metadata:
  name: ha-service
  annotations:
    eks.amazonaws.com/nodegroup: ha-nodes
spec:
  replicas: 3
  strategy:
    type: RollingUpdate
    rollingUpdate:
      maxUnavailable: 0
      maxSurge: 1
  template:
    spec:
      terminationGracePeriodSeconds: 60
      affinity:
        podAntiAffinity:
          preferredDuringSchedulingIgnoredDuringExecution:
            - weight: 100
              podAffinityTerm:
                topologyKey: kubernetes.io/hostname
      topologySpreadConstraints:
        - maxSkew: 1
          topologyKey: topology.kubernetes.io/zone
          whenUnsatisfiable: DoNotSchedule
      containers:
        - name: app
          image: 123456789012.dkr.ecr.eu-west-1.amazonaws.com/ha-service:1.4.2
          readinessProbe:
            httpGet: {path: /actuator/health/readiness, port: 8080}
          livenessProbe:
            httpGet: {path: /actuator/health/liveness, port: 8080}
          startupProbe:
            httpGet: {path: /actuator/health, port: 8080}
          lifecycle:
            preStop:
              exec: {command: ["sleep", "10"]}
          resources:
            requests: {cpu: 250m, memory: 512Mi}
            limits: {memory: 768Mi}
---
apiVersion: policy/v1
kind: PodDisruptionBudget
metadata:
  name: ha-service
spec:
  minAvailable: 2
---
apiVersion: autoscaling/v2
kind: HorizontalPodAutoscaler
metadata:
  name: ha-service
spec:
  minReplicas: 3
  maxReplicas: 9
""",
}
WEAK_K8S = {   # one replica, :latest, no probes, no PDB
    "pom.xml": pom("weak-service", "3.2.4", "17", [dep("spring-boot-starter-web")]),
    "deploy/k8s/app.yaml": """apiVersion: apps/v1
kind: Deployment
metadata:
  name: weak-service
spec:
  replicas: 1
  strategy:
    type: Recreate
  template:
    spec:
      containers:
        - name: app
          image: registry.example.org/weak-service:latest
""",
}
HELM_APP = {   # templated: values decide
    "pom.xml": pom("helm-service", "3.2.4", "17", [dep("spring-boot-starter-web")]),
    "helm/chart/Chart.yaml": "apiVersion: v2\nname: helm-service\nversion: 0.1.0\n",
    "helm/chart/values.yaml": "replicaCount: 2\nimage:\n  tag: 1.0.0\nautoscaling:\n  enabled: false\npodDisruptionBudget:\n  enabled: true\n  minAvailable: 1\n",
    "helm/chart/templates/deployment.yaml": """apiVersion: apps/v1
kind: Deployment
metadata:
  name: {{ include "chart.fullname" . }}
spec:
  replicas: {{ .Values.replicaCount }}
  template:
    spec:
      {{- with .Values.affinity }}
      affinity:
        {{- toYaml . | nindent 8 }}
      {{- end }}
      containers:
        - name: app
          image: "{{ .Values.image.repository }}:{{ .Values.image.tag }}"
          readinessProbe:
            httpGet: {path: /ready, port: 8080}
""",
}
NOMAD_APP = {
    "pom.xml": pom("nomad-service", "3.2.4", "17", [dep("spring-boot-starter-web")]),
    "deploy/job.nomad": """job "nomad-service" {
  datacenters = ["dc1", "dc2"]
  spread {
    attribute = "${node.datacenter}"
  }
  group "app" {
    count = 3
    update {
      max_parallel     = 1
      health_check     = "checks"
      min_healthy_time = "10s"
      auto_revert      = true
    }
    restart {
      attempts = 3
    }
    task "app" {
      driver = "docker"
      config {
        image = "registry.example.org/nomad-service:2.1.0"
      }
      kill_timeout = "30s"
      resources {
        cpu    = 500
        memory = 512
      }
      service {
        check {
          type = "http"
          path = "/health"
        }
      }
    }
  }
}
""",
}
