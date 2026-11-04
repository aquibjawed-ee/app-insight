// Synthetic illustrative data, reused from the earlier design mock. No real repository data.
const ICONS={grid:'<rect x="3" y="3" width="7" height="7" rx="1"/><rect x="14" y="3" width="7" height="7" rx="1"/><rect x="3" y="14" width="7" height="7" rx="1"/><rect x="14" y="14" width="7" height="7" rx="1"/>',layers:'<rect x="4" y="4" width="16" height="6" rx="1"/><rect x="4" y="14" width="16" height="6" rx="1"/>',box:'<rect x="4" y="4" width="16" height="16" rx="2"/><path d="M4 10h16M10 4v16"/>',shield:'<path d="m12 2 8 4v6c0 5-3.6 8-8 10-4.4-2-8-5-8-10V6l8-4z"/><path d="m9 12 2 2 4-4"/>',network:'<circle cx="5" cy="12" r="2"/><circle cx="18" cy="5" r="2"/><circle cx="18" cy="19" r="2"/><path d="m7 11 9-5M7 13l9 5"/>',spark:'<path d="M12 3v18M3 12h18M5.5 5.5l13 13M18.5 5.5l-13 13"/>',search:'<circle cx="10" cy="10" r="7"/><path d="m15 15 6 6"/>',arrow:'<path d="M4 12h16m-6-6 6 6-6 6"/>',code:'<path d="m8 8-4 4 4 4M16 8l4 4-4 4M14 4l-4 16"/>',check:'<path d="m5 12 4 4L19 6"/>',clock:'<circle cx="12" cy="12" r="9"/><path d="M12 7v5l4 2"/>',file:'<path d="M5 3h9l5 5v13H5z"/><path d="M14 3v6h5"/>',settings:'<path d="M12 3v3m0 12v3M3 12h3m12 0h3M5.6 5.6l2.1 2.1m8.6 8.6 2.1 2.1m0-12.8-2.1 2.1m-8.6 8.6-2.1 2.1"/><circle cx="12" cy="12" r="4"/>',database:'<ellipse cx="12" cy="5" rx="8" ry="3"/><path d="M4 5v13c0 4 16 4 16 0V5M4 11c0 4 16 4 16 0"/>',route:'<circle cx="5" cy="6" r="2"/><circle cx="19" cy="18" r="2"/><path d="M5 8v7a3 3 0 0 0 3 3h9M12 6h7v7"/>',list:'<path d="M8 6h13M8 12h13M8 18h13"/><circle cx="4" cy="6" r="1"/><circle cx="4" cy="12" r="1"/><circle cx="4" cy="18" r="1"/>',light:'<path d="M9 18h6m-5 3h4M12 2a7 7 0 0 0-4 12.7V17h8v-2.3A7 7 0 0 0 12 2z"/>',external:'<path d="M12 5h7v7M19 5l-9 9"/><path d="M18 14v5H5V6h5"/>'};
const icon=(n,size=18)=>`<svg width="${size}" height="${size}" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.7" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true">${ICONS[n]||ICONS.box}</svg>`;
const esc=x=>String(x??'').replace(/[&<>\"']/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
const capDefs=[{id:'change',title:'Change safety',icon:'code',brief:'Build, testing, CI and change verification'},{id:'platform',title:'Platform & protection',icon:'shield',brief:'Security, support and configuration'},{id:'runtime',title:'Runtime reliability',icon:'route',brief:'Resilience, deployment and integrations'},{id:'operate',title:'Operability & recovery',icon:'settings',brief:'Observability, diagnostics and recovery'}];
const aspectDefs=[
{id:'build',title:'Build & delivery',cap:'change',question:'What build and delivery mechanisms are declared?'},
{id:'tests',title:'Testing',cap:'change',question:'Which automated tests and their CI execution are evidenced?'},
{id:'quality',title:'Quality gates',cap:'change',question:'Are automated quality gates defined?'},
{id:'contracts',title:'Contract verification',cap:'change',question:'Are integration contracts verified?'},
{id:'security',title:'Security',cap:'platform',question:'Which protective checks and configurations are evidenced?'},
{id:'support',title:'Platform & dependencies',cap:'platform',question:'What language and framework versions are declared?'},
{id:'config',title:'Configuration',cap:'platform',question:'Where are environment-dependent settings configured?'},
{id:'resilience',title:'Runtime resilience',cap:'runtime',question:'What downstream failure-handling settings are evidenced?'},
{id:'integrations',title:'Integration safeguards',cap:'runtime',question:'Which processing guarantees are visible?'},
{id:'deployment',title:'Deployment & availability',cap:'runtime',question:'What health and deployment configuration exists?'},
{id:'observability',title:'Observability',cap:'operate',question:'What telemetry instrumentation is present?'},
{id:'diagnostics',title:'Diagnostics',cap:'operate',question:'Are trace and diagnostic mechanisms configured?'},
{id:'recovery',title:'Recovery',cap:'operate',question:'Which recovery and rollback declarations exist?'}
];
const ctrlDefs=[
{id:'build.wrapper',title:'Reproducible build wrapper',aspect:'build',sev:'MEDIUM',path:'gradle/wrapper/gradle-wrapper.properties',line:1},
{id:'build.ci',title:'CI workflow declared',aspect:'build',sev:'HIGH',path:'.github/workflows/ci.yml',line:3},
{id:'testing.unit',title:'Unit tests present',aspect:'tests',sev:'MEDIUM',path:'src/test/java/example/CheckoutServiceTest.java',line:14},
{id:'testing.ci',title:'Tests executed in CI',aspect:'tests',sev:'HIGH',path:'.github/workflows/ci.yml',line:28},
{id:'quality.gate',title:'Static analysis gate configured',aspect:'quality',sev:'MEDIUM',path:'build.gradle.kts',line:87},
{id:'contracts.tests',title:'Consumer contract tests present',aspect:'contracts',sev:'MEDIUM',path:'src/test/contract/CheckoutContractTest.java',line:19},
{id:'security.secrets',title:'External secrets reference',aspect:'security',sev:'HIGH',path:'deploy/values.yaml',line:43},
{id:'security.scan',title:'Dependency scan in CI',aspect:'security',sev:'HIGH',path:'.github/workflows/ci.yml',line:51},
{id:'platform.java_support',title:'Declared runtime support',aspect:'support',sev:'HIGH',path:'build.gradle.kts',line:16,reference:true},
{id:'platform.framework_support',title:'Declared framework support',aspect:'support',sev:'HIGH',path:'build.gradle.kts',line:21,reference:true},
{id:'config.external',title:'Environment configuration externalized',aspect:'config',sev:'MEDIUM',path:'src/main/resources/application.yaml',line:4},
{id:'resilience.timeout',title:'Outbound timeout settings',aspect:'resilience',sev:'HIGH',path:'src/main/kotlin/client/OrderClient.kt',line:36},
{id:'resilience.retry',title:'Retry policy for remote calls',aspect:'resilience',sev:'HIGH',path:'src/main/kotlin/client/OrderClient.kt',line:45},
{id:'integrations.idempotency',title:'Consumer idempotency mechanism',aspect:'integrations',sev:'HIGH',path:'src/main/kotlin/consumer/OrderConsumer.kt',line:52},
{id:'deployment.health',title:'Liveness/readiness configuration',aspect:'deployment',sev:'HIGH',path:'deploy/values.yaml',line:68},
{id:'deployment.rollout',title:'Rollout strategy configured',aspect:'deployment',sev:'MEDIUM',path:'deploy/values.yaml',line:89},
{id:'observability.logs',title:'Structured application logging',aspect:'observability',sev:'MEDIUM',path:'src/main/resources/logback-spring.xml',line:13},
{id:'observability.metrics',title:'Application metrics exposure',aspect:'observability',sev:'HIGH',path:'src/main/resources/application.yaml',line:45},
{id:'diagnostics.traces',title:'Distributed tracing configuration',aspect:'diagnostics',sev:'MEDIUM',path:'src/main/resources/application.yaml',line:52},
{id:'recovery.rollback',title:'Deployment rollback definition',aspect:'recovery',sev:'MEDIUM',path:'deploy/rollback.yaml',line:7}
];
const baseApps=[
['checkout','Checkout Gateway','Java 21','Spring Boot','Gradle','HTTP API','Commerce'],
['orders','Order Capture','Java 17','Spring Boot','Maven','HTTP + Messaging','Commerce'],
['catalog','Product Catalogue','Kotlin 1.9','Spring Boot','Gradle','HTTP API','Commerce'],
['payments','Payments Adapter','Java 17','Quarkus','Maven','HTTP API','Commerce'],
['stock','Stock Worker','Kotlin 1.9','http4k','Gradle','Message Consumer','Fulfilment'],
['profile','Customer Profile','Java 11','Spring','Maven','HTTP API','Customer'],
['notifications','Notification Hub','Java 8','Spring','Maven','Message Consumer','Platform'],
['pricing','Pricing Engine','Java 21','Micronaut','Gradle','HTTP API','Commerce'],
['search','Search API','Node.js 20','NestJS','npm','HTTP API','Experience'],
['reporting','Reporting Batch','Python 3.11','Python','Poetry','Scheduled Job','Analytics'],
['identity','Identity Bridge','Java 17','Spring Boot','Maven','HTTP + Messaging','Platform'],
['returns','Returns API','Java 11','Spring Boot','Gradle','HTTP API','Fulfilment']
];
const STATE=['PRESENT','PARTIAL','ABSENT','ISSUE','UNKNOWN','NOT_ASSESSED','NOT_APPLICABLE'];
const bad=new Set(['PARTIAL','ABSENT','ISSUE']);const nonJudge=new Set(['UNKNOWN','NOT_ASSESSED','NOT_APPLICABLE']);
function makeStates(i){const profiles=[[2,1,3,1],[2,1,3,1],[0,1,2,0],[1,2,2,1],[0,0,2,2],[2,1,0,1],[3,3,3,2],[1,0,0,0],[1,1,0,0],[2,0,1,2],[0,2,1,1],[1,1,2,0]];const seen={change:0,platform:0,runtime:0,operate:0};return ctrlDefs.map((c,j)=>{const cap=aspectDefs.find(d=>d.id===c.aspect).cap,pos=seen[cap]++,gaps=profiles[i][['change','platform','runtime','operate'].indexOf(cap)];let s=pos<gaps?['PARTIAL','ABSENT','ISSUE'][(i+pos)%3]:(i+pos)%5===0?'UNKNOWN':(i+pos)%7===0?'NOT_ASSESSED':'PRESENT';if(i===0){const checkout=['PRESENT','PRESENT','PRESENT','PARTIAL','ABSENT','UNKNOWN','PRESENT','ABSENT','PRESENT','UNKNOWN','PRESENT','PARTIAL','ABSENT','NOT_APPLICABLE','PRESENT','PARTIAL','PRESENT','ABSENT','UNKNOWN','NOT_ASSESSED'];s=checkout[j]};if((i===8||i===9)&&c.id.startsWith('platform.java'))s='NOT_APPLICABLE';if(i===9&&c.id.startsWith('integrations.'))s='NOT_APPLICABLE';return { ...c,state:s,severity:bad.has(s)?c.sev:null,evidence:(s==='PRESENT'||s==='PARTIAL'||s==='ISSUE')?[{path:c.path,line_start:c.line,snippet:`// Demonstration excerpt for ${c.id}\n// Illustrative fixture — not extracted from a repository`}]:[],searched:(s==='ABSENT'||s==='UNKNOWN'||s==='NOT_ASSESSED')?[c.path.split('/')[0]+'/**']:[],summary:s==='PRESENT'?'Configuration observed in the illustrative fixture.':s==='PARTIAL'?'Some evidence was found; the check is not fully established in this illustrative fixture.':s==='ABSENT'?'No matching declaration found within the illustrative search scope.':s==='ISSUE'?'Illustrative declaration triggers this control finding.':s==='UNKNOWN'?'Repository evidence was insufficient to determine this check.':s==='NOT_ASSESSED'?'This check was not assessed in the illustrative fixture.':'Check does not apply to the declared example configuration.'};})}
const apps=baseApps.map((v,i)=>({id:v[0],name:v[1],language:v[2],framework:v[3],build:v[4],kind:v[5],domain:v[6],controls:makeStates(i),idIndex:i,team:null,criticality:null}));
const edges=[
['checkout','orders','HTTP call','src/main/kotlin/client/OrderClient.kt:36'],['checkout','catalog','HTTP call','src/main/kotlin/client/CatalogClient.kt:18'],['checkout','payments','HTTP call','src/main/kotlin/client/PaymentClient.kt:28'],['checkout','PostgreSQL','Data store','src/main/resources/application.yaml:22'],['checkout','Redis','Cache','src/main/resources/application.yaml:33'],['checkout','Events / order-created','Kafka topic','src/main/kotlin/events/OrderPublisher.kt:17'],
['orders','stock','Messaging','src/main/java/messaging/StockPublisher.java:27'],['orders','notifications','Messaging','src/main/java/messaging/NotificationPublisher.java:41'],['orders','PostgreSQL','Data store','src/main/resources/application.yaml:21'],['catalog','Search API','HTTP call','src/main/kotlin/SearchClient.kt:22'],['catalog','MongoDB','Data store','src/main/resources/application.yaml:29'],['payments','Partner endpoint (unresolved)','HTTP call','src/main/java/client/PartnerClient.java:28'],['stock','Events / stock-updated','Kafka topic','src/main/kotlin/StockPublisher.kt:26'],['profile','PostgreSQL','Data store','src/main/resources/application.yaml:39'],['notifications','SMTP gateway','External system','src/main/resources/application.yaml:16'],['pricing','Redis','Cache','src/main/resources/application.yaml:28'],['search','Elasticsearch','Search datastore','src/config/search.ts:13'],['reporting','Object storage','External system','config/settings.py:13'],['identity','Identity provider (unresolved)','External system','src/main/resources/application.yaml:40'],['returns','orders','HTTP call','src/main/java/client/OrderClient.java:22'],['returns','Events / return-requested','Kafka topic','src/main/java/events/ReturnPublisher.java:20']
].map((e,i)=>({id:i,source:e[0],target:e[1],type:e[2],evidence:e[3],resolved:!e[1].includes('(unresolved)')}));
const pendingControls=[{id:'runtime.backpressure',title:'Backpressure detection',reason:'Detector not implemented in this prototype'}];

