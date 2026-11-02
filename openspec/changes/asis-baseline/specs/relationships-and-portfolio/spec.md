# Relationships and portfolio

## ADDED Requirements

### Requirement: One relationship model, labelled counts
Relationships SHALL be read once into the portfolio graph, and every count shown SHALL say what it counts (endpoints
exposed, outbound calls, messages, data stores, calls to other analysed applications); no screen SHALL sum different
kinds under "relationships".
Status: PARTIAL (one graph BUILT, commit 73f83ba; labelled counts PLANNED, UI review A5).

#### Scenario: office-integration-master
- WHEN the header, the Dependencies tab and the Architecture panel show counts for the same application
- THEN each count is labelled with its kind and they agree with `relationships.json`

### Requirement: Untraced calls are visible
When configuration names a service whose calls are not traced in code, or an HTTP client is used with no traced
target, the dependency map SHALL be marked incomplete, and the coupling summary SHALL report the same count.
Status: PARTIAL (calls_matched BUILT; coupling dimension still says "0 unresolved" for babylon, audit 6 item 5).

#### Scenario: an HTTP client with no traced target
- WHEN babylon uses an HTTP client and no call target is traced
- THEN calls matched is UNKNOWN and the coupling summary does not say "0 unresolved"

### Requirement: Targets are matched to analysed applications, never guessed
A call SHALL be matched to an analysed application only on a resolved host, name or path; otherwise it SHALL stay
unresolved or ambiguous with the reason.
Status: BUILT (`graph/resolve.py`).

#### Scenario: a URL that differs between profiles
- WHEN a client URL differs between the dev and prod profiles
- THEN the relationship is unresolved: "differs between profiles", citing both lines

### Requirement: Change impact is shown only when run
Change impact (for example, moving to Java 17) SHALL appear only when an impact run exists for the portfolio, and
SHALL separate confirmed incompatibilities, potential risks and unknowns.
Status: PARTIAL (impact runs BUILT, `graph/impact.py`; page hiding PLANNED).

#### Scenario: no impact run
- WHEN the consultant has not run an impact scenario
- THEN no Change impact page is shown

### Requirement: Each data store has one type everywhere
A store used as a cache or data grid (Hazelcast, Redis as cache, Ignite) SHALL be typed as a cache in the graph and
the AS-IS view, and SHALL NOT make database controls apply.
Status: PLANNED. Office's Hazelcast is a `Database` node with role cache in `relationships.json`, while data controls
say "no database found" (review-02 #14, review-03 B14).

#### Scenario: Hazelcast
- WHEN an application uses Hazelcast as a cache
- THEN the AS-IS view lists it under caches, and no screen calls it a database
