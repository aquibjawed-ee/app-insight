# Relationship platform (relationships.v1 and friends)

Extends app-discovery from "what is this application" to "how do the applications fit together, how well are they protected,
and what would a change touch". Same rules as the rest of the skill: no model, no network, target repositories are only read,
every claim cites `file:line`, and what cannot be known is said to be unknown.

`discover.py` and `discovery.v1` are unchanged. Everything below is additive and lives in `scripts/graph/`, `scripts/relate.py` and the report
(`scripts/build_graph_ui.py`, `assets/graph_ui_template.html`).

## Data flow

```
repository ──► discover.build (existing detectors) ──► discovery.json            [discovery.v1, unchanged]
     │                          │
     │   normalised facts: modules, hosting, dependencies, tests, versions
     ▼                          ▼
 adapters (graph/adapters/*) ─► relationships.json   per application            [relationships.v1, scope=application]
  http · messaging · data · platform         │
                                             ├─► safetynet.json  (graph + tests)  [safetynet.v1]
                                             ▼
     deployment files ─► resilience.py ─► resilience.json (HA configuration)     [resilience.v1]
                      resolve.py (cross-repository) ─► portfolio/relationships.json [relationships.v1, scope=portfolio]
                                             │
          ┌──────────────────────────────────┼───────────────────────────────┐
          ▼                                  ▼                               ▼
   c4.py  views (SVG, Mermaid)      impact.py + rules/*.json          dimensions.py
                                    [impact.v1]                       [dimensions.v1]
                                             │
                                             ▼
                              build_graph_ui.py  ─► report.html   (presentation only)
```

The graph never imports the UI. `graph/*` takes and returns plain JSON, so reporting, migration planning or other automation can use
`relationships.json` directly. `build_graph_ui.py` reads files; it does not analyse.

## Run it

```bash
python3 {skill_path}/scripts/relate.py analyse REPO [REPO ...] --out OUT [--criticality FILE] [--profile P] [--config-dir DIR ...] [--aliases FILE]
python3 {skill_path}/scripts/relate.py impact  --out OUT --scenario java_runtime --to 17 [--app NAME ...]
python3 {skill_path}/scripts/relate.py impact  --out OUT --scenario spring_boot --to 3.2 --app NAME
python3 {skill_path}/scripts/relate.py impact  --out OUT --scenario messaging_schema --topic orders.created [--old-schema a.avsc --new-schema b.avsc]
python3 {skill_path}/scripts/relate.py impact  --out OUT --scenario api_contract --endpoint "POST /x" --app NAME [--old-spec a.json --new-spec b.json]
python3 {skill_path}/scripts/relate.py impact  --out OUT --scenario db_migration --from-tech PostgreSQL --to-tech Oracle
python3 {skill_path}/scripts/relate.py impact  --out OUT --scenario infrastructure --platform Kubernetes --to 1.25
python3 {skill_path}/scripts/relate.py impact  --out OUT --scenario dependency_major --coordinate group:artifact --to 3
python3 {skill_path}/scripts/relate.py c4      --out OUT --view context|container|component [--app NAME] [--format svg|mermaid] [--file F]
python3 {skill_path}/scripts/relate.py diff    --base OUT_BASE --head OUT_HEAD [--format md|json] [--file F] [--fail-on-breaking]
python3 {skill_path}/scripts/relate.py report  --out OUT --html OUT/report.html
python3 {skill_path}/scripts/relate.py validate --out OUT        # schema, graph references, evidence re-read, staleness
```

Output layout: `OUT/<app>/{discovery,relationships,safetynet,resilience,dimensions}.json`, `OUT/portfolio/relationships.json`,
`OUT/manifest.json`, `OUT/impact/*.json`. Exit codes: 0 ok, 1 produced but integrity/evidence/staleness failed, 2 could not run.
Identical input and configuration give byte-identical output (the manifest and `DISCOVERY_FIXED_TIME` aside).

`analyse` options that change what can be resolved (all optional; without them nothing is guessed):
* `--profile P`: apply Spring profile `P` over the base configuration. Without it every profile's values are kept and a key whose values differ is
  reported as such (`property differs between profiles`), never silently picked.
* `--config-dir DIR` (repeatable): a Spring Cloud Config style directory (`application*.yml`, `<app>.yml`, `<app>-<profile>.yml`) that overrides the repository's
  own files. Its values are cited as `[config-dir] <file>`. Symlinked directories and files, non-regular files, files over the size cap and paths resolving outside the directory are refused. Each file's sha256 is recorded in `manifest.json` (`external_sources`) and `relate.py validate` re-reads the cited lines from it, so a changed file fails validation.
* `--aliases FILE`: a flat `host: target` file. A target that is an analysed application attaches the call to it; any other target names an external system.

## The relationship model (`schemas/relationships.v1.schema.json`)

Nodes: Application, Module, Service (a name not yet matched), ApiEndpoint, Database, MessageBroker, Topic, ExternalSystem,
InfrastructureResource. Edges: CONTAINS, EXPOSES_API, CALLS_API, PUBLISHES_TO, CONSUMES_FROM, READS_FROM, WRITES_TO, DEPENDS_ON, DEPLOYED_ON.

Every edge carries: a stable id (digest of type, ends, mechanism and first citation), source, target, **mechanism** (source_annotation,
source_call, configuration, dependency_declaration, build_metadata, deployment_descriptor, runtime_observation, cross_repo_resolution),
**basis**, **confidence**, `status` (CONFIRMED / INFERRED / UNKNOWN), **resolution** and `evidence[]`.

| basis | meaning |
|---|---|
| `observed_runtime` | seen at run time (reserved: no importer yet) |
| `static_configured` | named in source, configuration or a deployment descriptor |
| `declared` | a dependency or module declaration says it is there (never promoted to a caller/publisher/consumer) |
| `inferred` | derived from a type or pattern (e.g. a Spring Data repository base interface implies read/write) |
| `unresolved` | something is used but its target is not known; the target is an explicit placeholder node |

Resolution state is `resolved`, `unresolved`, `ambiguous` (with `candidates`, none chosen) or `not_applicable`. `meta.resolution_log`
records every cross-repository decision with its reasoning. `not_relationships` lists things looked at and deliberately not turned
into relationships (test-only databases, local URLs, schema-migration tools, non-literal paths) so a reviewer can audit the rule.

`model.validate_integrity` checks: edge ends exist, ids unique, every edge has evidence (or reasoning), ambiguity lists candidates, and with
repositories supplied every file citation still matches the file.

## Adapters (what is read, what is not)

| adapter | reads | notes |
|---|---|---|
| `adapters/http.py` | Spring MVC/WebFlux, JAX-RS, Micronaut controllers (including mappings declared on an interface the controller implements); WebFlux `RouterFunction` routes; Ktor routes (top level); Feign / MicroProfile / Micronaut / Spring 6 `@HttpExchange` clients; RestTemplate, WebClient, RestClient, java.net.http, OkHttp calls with literal, `@Value` or `@ConfigurationProperties`-bound URLs | class + method paths are combined; non-literal paths are `not_relationships`; a Feign interface nothing references is low confidence; an `@HttpExchange` client takes its base URL from its own `url` or the single literal base URL in code, otherwise it is an explicit unresolved target; nested `path(...)`/`nest(...)` prefixes in router functions are flagged `path_may_be_prefixed` |
| `adapters/gateway.py` | Spring Cloud Gateway `routes` (YAML or properties): `uri: lb://name` or an absolute URL with `Path=` predicates | each route is a call from the gateway; a route to an analysed application is checked as a prefix against that application's endpoints |
| `adapters/messaging.py` | `@KafkaListener`, `@RabbitListener`, `@JmsListener`, `@SqsListener`; send calls on variables **declared** as a messaging template; `ProducerRecord`; Spring Cloud Stream bindings | topic = literal, resolvable `${property}`, or unique constant; otherwise unresolved. Broker dependency alone is never a publisher |
| `adapters/data.py` | existing `integrations.detect_dependencies` (reused); literal JDBC/Mongo/Redis connection identity; Spring Data repositories, JdbcTemplate; **tables**: `@Entity`/`@Table` (Spring's default snake_case naming), native `@Query` SQL and SQL literals passed to JdbcTemplate (tables after FROM / JOIN / INTO / UPDATE), and tables created by Flyway / plain SQL / Liquibase migrations | test-only and stub findings are skipped; read/write capability is `inferred`, but tables from a SQL literal are `static_configured`; JPQL, comments and string-built SQL are not read; migrations mark the tables an application creates (`tables_owned`) only when it has exactly one database |
| `adapters/platform.py` | identity keys, modules and inter-module dependencies, deployment (existing hosting facts + literal Kubernetes manifests) | Helm templates are not rendered |

## How values reach the code (configuration layering)

Names that are not literals (URLs, topics, queues) are resolved through `adapters/common.Config`, in this precedence, highest first: environment values found in
deployment files (Kubernetes `env`, Compose, `.env`), an external `--config-dir`, the selected profile's files, the base files. Besides `${property}`
placeholders it understands two ways a value is bound: a `@ConfigurationProperties` class (`kafkaConfig.publisher.topics.paymentEventTopic` becomes
`<prefix>.publisher.topics.payment-event-topic`, the prefix being the one of the class the variable is declared with in the same file) and a `@Value`-injected
field or constructor parameter. When the value cannot be found the edge stays unresolved and its reason names the property key that was looked for.

## Cross-repository resolution (`graph/resolve.py`)

* **Service name → application**: exact, case-insensitive match on a declared identity key. *Strong*: `spring.application.name` (and Quarkus/Micronaut
  equivalents), Kubernetes `Service` name. *Medium*: Maven artifactId, Gradle `rootProject.name`, Helm chart name, Deployment name. *Weak*: repository
  name. Strong or medium matching exactly one application resolves; two applications sharing the key is `ambiguous`; a weak-only match stays
  `unresolved` and names the weak candidate. No similarity matching.
* **Call → endpoint**: the callee's exposed endpoints are searched by verb and path shape (context path applied). No match is reported as a possible
  contract mismatch, never hidden.
* **Topics**: identity is broker family + name. Applications whose broker addresses are all different do not share the topic (separate nodes);
  where an address is missing the topic is shared on name only and says so (`cluster_verified: false`).
* **Databases**: identity is the literal host/port/database of the connection setting; placeholder-only settings stay application-local. For each shared database
  the tables are aggregated (`owned_by`, `used_by`); a table used or created by more than one application is written to the resolution log.
* **Hosts that are applications**: a call to an external host is attached to an analysed application when the user's alias file maps that host to it, or when the host is
  a Kubernetes service DNS name (`name.namespace.svc[.cluster.local]`) whose first label is an application's strong or medium identity. An alias to a name no
  application has names an external system; several candidates stay ambiguous.
* **Declared hosts** (`adapters/platform.py declared_hosts`): a host the application announces about itself, read without being told: OpenAPI/Swagger `servers[].url`/`host`, `x-google-audience` (API gateway config), Ingress/Istio/Gateway API/Traefik hosts, and the application's own pipeline variable naming its own base URL. A call to that host is attached to the application (strong: OpenAPI/gateway/ingress; medium: pipeline variable); two applications declaring the same host stay `ambiguous`. On 88 real repositories this attached 5 of 33 external-host calls with no alias file.
* **Gateway routes** are matched as prefixes: `/api/orders/**` is checked against the callee's endpoints under `/api/orders`.

## Safety net (`graph/safetynet.py`, `safetynet.v1`)

Per discovered component (endpoint, consumer, publisher, database path, downstream call) and for the repository: *a test exists*, *is mapped to the
component*, *runs automatically*, *passes*, *coverage measured*, *threshold enforced*, *behaviour verified*. Mapping is by static reference: a route literal
in MockMvc/WebTestClient/RestAssured/TestRestTemplate, a `@WebMvcTest(Controller.class)`, a listener class or topic name in a messaging test, a repository in
a `@DataJpaTest`, a WireMock/MockRestServiceServer/Pact stub path. Classification: `mapped_with_assertions`, `mapped_no_assertion_seen`, `unverified`. Each mapped component also carries a `strength`: `route` (a route/topic/stub literal), `class` (the test names the controller or listener class) or `reference` (weaker mention). The summary reports `direct` (route-level) and `class_level` separately and the report headline counts only route-level mappings, because a class mention does not show that a specific endpoint is exercised.
**`unverified` never means untested.** `passes` is always `unknown` (nothing is executed) and per-component coverage is unavailable.

## Resilience and HA configuration (`graph/resilience.py`, `resilience.v1`)

Reads the deployment files that are in the repository and, per workload and per check, says `present`, `absent` (a descriptor of that workload was
read and the setting is not in it), `unknown` (templated, defined elsewhere, or not readable), `default` (the platform default applies) or `not_applicable`.
Platforms: **Kubernetes** (plain manifests, Helm charts with `values.yaml`; EKS signals only from EKS-specific evidence: `eks.amazonaws.com` annotations, eksctl, `aws_eks` Terraform, ALB / Karpenter / EBS CSI annotations; an ECR image alone is not an EKS signal),
**HashiCorp Nomad** jobs, **Docker Compose**.

| group | checks |
|---|---|
| Redundancy | more than one instance; pod anti-affinity (or topology spread); spread across availability zones; PodDisruptionBudget; autoscaling with a floor of two |
| Health | readiness, liveness and startup probes (Nomad: service check) |
| Rollout | rolling update with a stated surge/unavailable limit (Nomad: `update` block); graceful shutdown (grace period or preStop; Nomad: kill_timeout) |
| Capacity | resource requests and limits |
| Recovery | restart / reschedule / auto-revert |
| Supply | image pinned to a version (no `:latest`) |

Kubernetes-only checks (PDB, probes by type, autoscaling) are `not_applicable` for Nomad and Compose. `absent` means *not in these files*, never *not in
production*: a platform or GitOps repository, cluster policy or a cloud setting may add it. With no Kubernetes, Nomad or Compose definition in the repository
the result is `not_assessed`, with the reason, not a failure. A PodDisruptionBudget or autoscaler is matched to the repository, not to a workload selector;
Helm charts are not rendered, so a value that comes from an unread template or values file is `unknown`.

## Change impact (`graph/impact.py`, `rules/compat.v1.json`, `impact.v1`)

Scenarios: `java_runtime`, `spring_boot`, `dependency_major`, `db_migration`, `messaging_schema`, `api_contract`, `infrastructure`.
Output keeps apart: `confirmed_incompatibilities` (a cited, versioned rule matched literal text in cited files, unless a replacement library is declared),
`potential_risks`, `affected_components`, `downstream_impact` (graph reachability with the edge path; paths through inferred links are marked `reduced`),
`required_verification` (with the safety-net classification), `unknowns` (unresolved/ambiguous neighbours, missing schemas, unseen repositories).
Reachability is potential impact, not proof of breakage. Rules are reference knowledge with sources; a maintainer must review additions.
OpenRewrite recipe names appear as informational pointers; the recipes are not run. Contract checks: OpenAPI (JSON, YAML if PyYAML is installed) and Avro records.

## Graph diff (`graph/diff.py`, `graphdiff.v1`)

`relate.py diff --base A --head B` compares two analyses by meaning (type, ends, method, path shape), never by file or line, so moved code is not a change.
**Breaking**: an endpoint removed while a call to it remains; an application removed while calls to it remain; a topic that lost its last publisher but still has
consumers. It also lists endpoints, calls and messaging added or removed, and calls that newly cannot be matched. Markdown (for a merge-request comment) or JSON;
`--fail-on-breaking` exits 3. It sees only what static analysis sees: a relationship that is not seen is not necessarily gone.

## Dimensions (`graph/dimensions.py`, `rules/lifecycle.v1.json`)

Nine separate dimensions, no combined score: engineering maturity, security exposure (needs `scan.py`; otherwise *not assessed*), technology lifecycle
(vendor support windows from reference data that carries a `review` block; until a maintainer sets it to `reviewed` the report says "reference data not reviewed"), operational resilience (from `resilience.v1`), safety net, architecture coupling (counts), change complexity (descriptive
counts), business criticality (**unknown** unless a verified `--criticality` file is supplied; never inferred), evidence completeness.
States: `assessed`, `partial`, `not_assessed`, `unknown`, `not_applicable`.

## The Atlas report (`relate.py report`)

A single self-contained HTML file (no network, no server). It is presentation only: every number is read from the JSON files above.

**Navigation model: summary, then filter, then application, then evidence.** Nothing needs a legend; each step is reached by clicking the number or sentence
that interested you.

| page | what it answers | how it leads on |
|---|---|---|
| Portfolio | five headline numbers; **What stands out** (plain-language sentences with counts, only when the count is above zero); technology distribution | every number, sentence and bar opens the Applications table already filtered |
| Applications | which applications need attention, worst first | dense table; click a row to open the application |
| Dependency map | how applications connect | full diagram up to 12 applications; above that a ranked "most connected" table, because a single diagram of hundreds of applications is unreadable |
| Gap explorer | which engineering practices have no evidence, grouped by capability | link to each application's Findings tab |
| Change impact | the result of `relate.py impact` runs | evidence and relationship paths in a side panel |
| Application | tiles for the six dimensions, then tabs: Overview, Architecture, Integrations, Resilience & HA, Tests & safety net, Checklist, Delivery, Findings & next steps, Evidence | every claim opens its evidence in the side panel |

**Built for hundreds of applications.** The Applications page is a table, not cards: one row per application, sticky header, 50 rows per page, sorted worst
first. Column headings sort; a "n flagged" chip under a heading filters to the flagged ones; chips combine (AND) with a text search. The filter lives in the
address (`#/apps?f=ended,tests&q=...`), so any view can be bookmarked or shared, and every KPI, insight and chart bar deep-links to one. Cells carry words
("Java 8 ended", "5/15 mapped", "8 unmatched"), not only colours or glyphs. Per-application diagrams are rendered on demand from the graph; the portfolio
diagram is skipped above 12 applications.

**What is deliberately not shown:** line numbers and class names (they change with every edit; the evidence panel shows the file path and the snippet),
and any combined score. Mermaid text is offered through **Copy Mermaid** and **Download .mmd** (rendering it needs a library fetched from the internet, which an
offline report cannot do); the diagram on the page is already drawn.

**Export.** *Export summary* downloads a small JSON file (per-application dimension states, unmatched calls, mapped-test counts) for use elsewhere.

## Glossary

| term | meaning |
|---|---|
| **Unmatched calls** | outgoing calls or messages whose target could not be attached to an analysed application: the name matched nothing (*unresolved*), matched several applications (*ambiguous*) or only a repository name (too weak to use). It measures how complete the dependency map is, not how healthy the application is. Analysing the owning repositories in the same run usually resolves them |
| Resolved / Unresolved / Ambiguous | resolved: attached on a declared identity of exactly one application; unresolved: no application answers to the name; ambiguous: several do, none is chosen |
| Configured / Declared / Inferred | configured: named in source, configuration or deployment files; declared: a library or module says it is there (never a caller, publisher or consumer); inferred: derived from a type or pattern |
| **Unverified** | no test could be tied to the component by static references. It never means no test exists |
| **Mapped** | a test references the component (a route, a listener, a repository, a stubbed downstream path); *assertion seen* means an assertion sits near the reference |
| **Not scanned** | no vulnerability scan was run, so exposure is unknown (scanner configuration found in files is a different thing: what is watched, not how safe it is) |
| **Not assessed** | nothing was looked at (for example no deployment files for HA); not a pass or a fail |
| **Unknown** | the scan looked and cannot tell (templated value, remote include, version not stated) |
| **Vendor support ended / extended only** | from `rules/lifecycle.v1.json`: the Java version or the Spring Boot line is past (or only under paid) vendor support; other JDK vendors publish their own windows |
| **HA checks (n/m)** | resilience checks in place out of those that apply to the platform found |
| **Maturity %** | engineering practice from the discovery scan; not a risk or business-value score |
| **Profile** | the Spring profile selected with `--profile`. Without one, a property whose value differs between profiles is reported as unresolved with that reason |
| **Alias** | a user-supplied host-to-application mapping (`--aliases`); the edge's resolution says it was matched by alias, not by a declared identity |
| **Tables used / created** | tables read or written (from entities, native SQL and JDBC SQL literals) and tables the application's own migrations create |
| **Flagged** | the cell meets its rule for "attention" or "concern"; the rule is in the dimension's *Basis* |

## Tools evaluated

| tool | decision | why |
|---|---|---|
| jdeps | not adopted | needs compiled classes/JARs, i.e. a build; the scan must stay static. Candidate optional enrichment when artifacts already exist |
| jQAssistant | not adopted | needs a build and an embedded graph database; the brief excludes graph databases |
| ArchUnit | not adopted | runs inside the target's tests (executes target code); useful in the target's own CI, not as a scanner |
| OpenRewrite | pointers only | runs through the target's Maven/Gradle (execution, dependency resolution, writes); recipe names are surfaced as next steps. A sandboxed dry-run adapter is a possible later addition |
| Maven/Gradle resolution | not adopted | resolution needs the network and execution; declared coordinates are read statically (existing behaviour) |
| Spring configuration metadata | not adopted | generated at build time; annotations and properties are read directly |
| OpenAPI parsing | adopted | contract diff; JSON in stdlib, YAML via optional PyYAML |
| Kubernetes manifests | adopted (literal) | names, namespace, images, removed API versions |
| Terraform | not implemented | known gap |
| OpenTelemetry | not implemented | `observed_runtime` basis is in the schema; no importer yet |
| spring-service-graph (`ssg`) | read, not run | a new (single-maintainer, unreleased at the time of review) Java-only static fleet-graph tool. Its design was compared with this engine and the gaps found were adopted here: `@HttpExchange` clients, gateway routes, mappings on implemented interfaces, WebFlux routers, host aliases, profile / config-repository layering, table-level data and graph diff. It does not scan Kotlin, which is much of the estate this engine is used on |
| Trivy | reused | existing opt-in `scan.py`; its result feeds the security dimension |

## Known limitations and unsupported patterns

* Static analysis only; no relationship is an observed runtime fact. Runtime observations (OpenTelemetry service graph) are not imported.
* Languages: Java and Kotlin. Groovy, Scala, Node, .NET are not read. Generated clients, reflection, clients built from computed values and
  destinations built at run time stay unresolved.
* Ktor `route(...)` prefixes, nested WebFlux `path(...)`/`nest(...)` prefixes and composed meta-annotations are not combined. Mappings on an interface are read when the interface is in the same repository (a generated interface that is not checked in is not seen).
* Helm templates are not rendered; Terraform and Compose-only topology are not turned into relationships (Compose is read by the existing detector for dependencies).
* Cross-repository matching needs the other repository to be analysed in the same run; a library dependency between repositories is not resolved.
* Safety-net mapping misses tests that reach a component indirectly; assertions are detected near the reference, not proven to check behaviour.
* The report is a single file: very large analyses (thousands of applications) make it large; the table paginates but all data is embedded.
* Lifecycle dates are the vendors' published roadmaps in `rules/lifecycle.v1.json`; they are reference data and need maintainer review: both rule packs (`lifecycle.v1.json`, `compat.v1.json`) ship with `review.status: unreviewed` and the UI and impact output say so until `reviewed_by`/`reviewed_at` are filled in.
* A bound `@ConfigurationProperties` value is resolved only when the class declaring its prefix is in the same repository and the variable's declared type is visible in the same file; topics held in local variables, computed expressions or properties that differ between profiles stay unresolved.
* Table names come from literals: SQL assembled at run time, stored procedures, JPQL and ORM-generated SQL are not read, and migrations in non-standard folders are not found.
* Resilience reads only deployment descriptors in the analysed repository; GitOps/platform repositories, Helm rendering, Terraform-managed clusters and cloud settings are not read.
* Commented-out lines (SQL `--` and `/* */`, Liquibase, YAML `#` routes) are not evidence. Secret-named environment variables are neither read nor cited.
* The relationship graph is exact on what it finds; it is not a complete inventory. `evidence_completeness` and `limitations` say how much was looked at.
