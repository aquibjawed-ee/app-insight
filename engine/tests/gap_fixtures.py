"""Stub repositories, one per gap found by reading spring-service-graph. Each is deliberately tiny."""
from graph_fixtures import pom, dep

BOOT = lambda name, extra=(): pom(name, "3.2.4", "17", [dep("spring-boot-starter-web")] + list(extra))

# A. Spring 6 declarative client
HTTP_EXCHANGE = {
    "pom.xml": BOOT("gap-exchange"),
    "src/main/resources/application.yml": "spring:\n  application:\n    name: gap-exchange\n",
    "src/main/java/g/StockApi.java": """package g;
@HttpExchange("/api/stock")
public interface StockApi {
    @GetExchange("/{sku}") Stock one(@PathVariable String sku);
    @PostExchange("/reserve") Reservation reserve(@RequestBody Reserve r);
}
""",
    "src/main/java/g/Config.java": """package g;
@Configuration class Config {
  @Bean StockApi stockApi(WebClient.Builder b) {
    WebClient c = b.baseUrl("https://stock.acme-corp.io").build();
    return HttpServiceProxyFactory.builderFor(WebClientAdapter.create(c)).build().createClient(StockApi.class);
  }
}
@Service class UsesIt { private final StockApi api; }
""",
}
# B. gateway routes
GATEWAY = {
    "pom.xml": BOOT("gap-gateway"),
    "src/main/resources/application.yml": """spring:
  application:
    name: gap-gateway
  cloud:
    gateway:
      routes:
        - id: orders
          uri: lb://gap-iface
          predicates:
            - Path=/v1/orders/**
        - id: pay
          uri: https://api.acme-pay.io
          predicates:
            - Path=/pay/**
""",
    "src/main/java/g/App.java": "package g;\n@SpringBootApplication class App {}\n",
}
# C. endpoints declared on an implemented interface
IFACE = {
    "pom.xml": BOOT("gap-iface"),
    "src/main/java/g/OrdersApi.java": """package g;
@RequestMapping("/v1")
public interface OrdersApi {
    @GetMapping("/orders/{id}") Order get(@PathVariable Long id);
    @PostMapping("/orders") Order create(@RequestBody Order o);
}
""",
    "src/main/java/g/OrdersApiController.java": "package g;\n@RestController\npublic class OrdersApiController implements OrdersApi {\n  public Order get(Long id) { return null; }\n  public Order create(Order o) { return null; }\n}\n",
}
# D. WebFlux router functions
ROUTER = {
    "pom.xml": pom("gap-router", "3.2.4", "17", [dep("spring-boot-starter-webflux")]),
    "src/main/java/g/Routes.java": """package g;
import static org.springframework.web.reactive.function.server.RequestPredicates.*;
@Configuration class Routes {
  @Bean RouterFunction<ServerResponse> a(Handler h) {
    return RouterFunctions.route(GET("/ping"), h::ping).andRoute(POST("/echo"), h::echo);
  }
  @Bean RouterFunction<ServerResponse> b(Handler h) {
    return route().GET("/status/{id}", h::status).DELETE("/status/{id}", h::clear).build();
  }
}
""",
}
# E. alias: a host that is really another analysed application
BILLING = {"pom.xml": BOOT("billing-service"), "src/main/resources/application.yml": "spring:\n  application:\n    name: billing-service\n",
           "src/main/java/g/B.java": "package g;\n@RestController\nclass B {\n  @PostMapping(\"/invoices\")\n  void inv() {}\n}\n"}
ALIAS = {
    "pom.xml": BOOT("gap-alias", [dep("spring-cloud-starter-openfeign", "org.springframework.cloud")]),
    "src/main/java/g/BillingClient.java": """package g;
@FeignClient(name = "billing", url = "https://billing.internal.acme-corp.io")
public interface BillingClient { @PostMapping("/invoices") void invoice(@RequestBody Inv i); }
""",
    "src/main/java/g/U.java": "package g;\n@Service class U { private final BillingClient c; private final RestTemplate rt;\n  void n() { rt.postForObject(\"http://billing-service.shop.svc.cluster.local/invoices\", null, String.class); } }\n",
}
ALIASES = "billing.internal.acme-corp.io: billing-service\napi.stripe.com: stripe\n"
# F. profiles and an external config directory
PROFILES = {
    "pom.xml": BOOT("gap-profiles", [dep("spring-cloud-starter-openfeign", "org.springframework.cloud")]),
    "src/main/resources/application.yml": "payments:\n  url: https://pay-test.acme-corp.io\n",
    "src/main/resources/application-prod.yml": "payments:\n  url: https://pay.acme-corp.io\n",
    "src/main/java/g/Pay.java": """package g;
@FeignClient(name = "pay", url = "${payments.url}")
public interface Pay { @PostMapping("/charge") void charge(); }
@FeignClient(name = "ledger", url = "${LEDGER_URL}")
interface Ledger { @GetMapping("/entries") void entries(); }
@FeignClient(name = "audit", url = "${audit.url}")
interface Audit { @PostMapping("/events") void post(); }
@Service class U { private final Pay p; private final Ledger l; private final Audit a; }
""",
    "deploy/k8s/app.yaml": """apiVersion: apps/v1
kind: Deployment
metadata:
  name: gap-profiles
spec:
  template:
    spec:
      containers:
        - name: app
          image: registry.example.org/gap-profiles:1.0.0
          env:
            - name: LEDGER_URL
              value: https://ledger.acme-corp.io
""",
}
CONFIG_DIR_FILES = {"gap-profiles.yml": "audit:\n  url: https://audit.acme-corp.io\n"}
# G. tables
DATA = {
    "pom.xml": BOOT("gap-data", [dep("spring-boot-starter-data-jpa"), dep("postgresql", "org.postgresql"), dep("flyway-core", "org.flywaydb"), dep("spring-boot-starter-jdbc")]),
    "src/main/resources/application.yml": "spring:\n  datasource:\n    url: jdbc:postgresql://db.acme-corp.io:5432/shop\n",
    "src/main/resources/db/migration/V1__init.sql": "create table orders (id bigint primary key);\ncreate table order_lines (id bigint);\n",
    "src/main/java/g/Order.java": "package g;\n@Entity\n@Table(name = \"orders\")\nclass Order {}\n",
    "src/main/java/g/Customer.java": "package g;\n@Entity\nclass Customer {}\n",
    "src/main/java/g/Repo.java": """package g;
interface OrderRepo extends JpaRepository<Order, Long> {
  @Query(value = "select o.* from orders o join customers c on c.id = o.customer_id", nativeQuery = true) List<Order> withCustomers();
  @Query("select o from Order o where o.id = 1") Order jpql();
}
interface CustomerRepo extends JpaRepository<Customer, Long> {}
""",
    "src/main/java/g/Audit.java": """package g;
@Component class Audit {
  private final JdbcTemplate jdbc;
  void log(String m) { jdbc.update("insert into audit_log (msg) values (?)", m); }
  int n() { return jdbc.queryForObject("select count(*) from audit_log", Integer.class); }
  // select * from commented_out
}
""",
}
DATA2 = {   # a second application on the same database and one of the same tables
    "pom.xml": BOOT("gap-data2", [dep("spring-boot-starter-data-jpa"), dep("postgresql", "org.postgresql")]),
    "src/main/resources/application.yml": "spring:\n  datasource:\n    url: jdbc:postgresql://db.acme-corp.io:5432/shop\n",
    "src/main/java/g/Report.java": "package g;\n@Entity\n@Table(name = \"orders\")\nclass Report {}\ninterface ReportRepo extends JpaRepository<Report, Long> {}\n",
}
NOT_A_ROUTER = {   # GET(...) strings that are not routes: no router types in the file
    "pom.xml": BOOT("gap-not-router"),
    "src/main/java/g/N.java": "package g;\nclass N { String a = GET(\"/not-a-route\"); static String GET(String s) { return s; } }\n",
}
# H. values that reach the code through binding: @ConfigurationProperties classes and @Value-injected constructor parameters (Kotlin, as in the estate)
PROPS = {
    "build.gradle.kts": 'plugins { id("org.springframework.boot") version "3.2.4"; kotlin("jvm") version "1.9.23" }\ndependencies { implementation("org.springframework.kafka:spring-kafka") }\n',
    "src/main/resources/application.yml": "kafka:\n  notification-topic: notifications\n  publisher:\n    topics:\n      payment-event-topic: payments\napp:\n  audit-topic: audit\n",
    "src/main/kotlin/g/KafkaConfig.kt": """package g
@ConfigurationProperties(prefix = "kafka")
data class KafkaConfig(var notificationTopic: String = "", var publisher: Publisher = Publisher()) {
    class Publisher(var topics: Topics = Topics())
    class Topics(var paymentEventTopic: String = "")
}
""",
    "src/main/kotlin/g/Pub.kt": """package g
@Component
class Pub(private val kafkaTemplate: KafkaTemplate<String, String>, private val kafkaConfig: KafkaConfig,
          @Value("\\${app.audit-topic}") private val auditTopic: String) {
    fun a() { kafkaTemplate.send(kafkaConfig.notificationTopic, "k", "v") }
    fun b() { kafkaTemplate.send(kafkaConfig.publisher.topics.paymentEventTopic, "k", "v") }
    fun c() { kafkaTemplate.send(auditTopic, "k", "v") }
    fun d() { kafkaTemplate.send(kafkaConfig.unknownTopic, "k", "v") }
}
""",
}
# I. discovery without prior knowledge: the callee declares its own host
OWNER_A = {
    "pom.xml": BOOT("gap-owner-a"),
    "src/main/java/g/O.java": "package g;\n@RestController\nclass O {\n  @GetMapping(\"/orders\")\n  String o() { return \"\"; }\n}\n",
    "openapi.yaml": "openapi: 3.0.0\ninfo: {title: orders, version: 1}\nservers:\n  - url: https://orders.api.acme-corp.io/v1\npaths:\n  /orders:\n    get: {responses: {'200': {description: ok}}}\n",
    "deploy/k8s/ingress.yaml": "apiVersion: networking.k8s.io/v1\nkind: Ingress\nmetadata:\n  name: orders\nspec:\n  rules:\n    - host: orders-ingress.acme-corp.io\n      http: {paths: []}\n",
    ".gitlab-ci.yml": "variables:\n  BASE_URL: https://orders-smoke.acme-corp.io\n  UPSTREAM_URL: https://not-mine.acme-corp.io\ntest:\n  script: [echo]\n",
}
OWNER_B = {   # declares the same host as owner C: that host must be ambiguous
    "pom.xml": BOOT("gap-owner-b"),
    "openapi.yaml": "openapi: 3.0.0\nservers:\n  - url: https://shared.api.acme-corp.io\npaths: {}\n",
}
OWNER_C = {
    "pom.xml": BOOT("gap-owner-c"),
    "openapi.yaml": "openapi: 3.0.0\nservers:\n  - url: https://shared.api.acme-corp.io\npaths: {}\n",
    "endpoints/overrides/integration.yml": "info:\n  title: pay\nhost: pay.endpoints.acme-corp.cloud.goog\nx-google-endpoints:\n  - name: pay.endpoints.acme-corp.cloud.goog\nsecurityDefinitions:\n  smoke:\n    type: oauth2\n    x-google-audiences: http://pay.flex.acme-corp.io\n",
}
HOST_CALLER = {
    "pom.xml": BOOT("gap-hostcaller", [dep("spring-cloud-starter-openfeign", "org.springframework.cloud")]),
    "src/main/java/g/C.java": """package g;
@FeignClient(name = "a", url = "https://orders.api.acme-corp.io")
interface A { @GetMapping("/orders") String a(); }
@FeignClient(name = "b", url = "https://orders-ingress.acme-corp.io")
interface B { @GetMapping("/orders") String b(); }
@FeignClient(name = "c", url = "https://orders-smoke.acme-corp.io")
interface C { @GetMapping("/orders") String c(); }
@FeignClient(name = "d", url = "https://shared.api.acme-corp.io")
interface D { @GetMapping("/x") String d(); }
@FeignClient(name = "e", url = "http://pay.flex.acme-corp.io")
interface E { @PostMapping("/pay") String e(); }
@FeignClient(name = "f", url = "https://repeated-by-callers.acme-corp.io")
interface F { @GetMapping("/f") String f(); }
@FeignClient(name = "g", url = "https://not-mine.acme-corp.io")
interface G { @GetMapping("/g") String g(); }
@Service class U { private final A a; private final B b; private final C c; private final D d; private final E e; private final F f; private final G g; }
""",
}
OTHER_CALLER = {   # repeats a host in its configuration: that is a caller, not a declaration
    "pom.xml": BOOT("gap-othercaller"),
    "src/main/resources/application.properties": "upstream.url=https://repeated-by-callers.acme-corp.io\n",
}
GAPS = {"gap-exchange": HTTP_EXCHANGE, "gap-gateway": GATEWAY, "gap-iface": IFACE, "gap-router": ROUTER, "billing-service": BILLING, "gap-alias": ALIAS, "gap-profiles": PROFILES, "gap-data": DATA, "gap-data2": DATA2, "gap-not-router": NOT_A_ROUTER, "gap-props": PROPS, "gap-owner-a": OWNER_A, "gap-owner-b": OWNER_B, "gap-owner-c": OWNER_C, "gap-hostcaller": HOST_CALLER, "gap-othercaller": OTHER_CALLER}
