# Report experience

## ADDED Requirements

### Requirement: An internal report and a separate client file
The scan SHALL write an internal report whose header and file name say "internal" until the client-use gate passes.
`app-insight review` SHALL write a separate client file containing exactly what design 8.6 lists: the review statement;
per application in scope, verdicts only when every must-review item is resolved (else "Not yet reviewed"), "Not
available" labels, each result's outcome, never an unreviewed tool verdict; remedies only on reviewed gaps, labelled
"suggested, not reviewed" unless confirmed with the result; AS-IS facts labelled "read by the tool, not reviewed"
(D-7a, DECIDED); aspect cells by the rule of design 8.6 (Not checked, High gaps, Gaps, Reviewed x of y, Not applicable, Reviewed
nothing confirmed, Partly confirmed, In place (stated), In place); a scope summary of what was not looked at and the reference-data review
status on results resting on it; possible issues only when reviewed individually; derived views recomputed from
review outcomes or omitted; the summary row "n of m applications in scope shown; k not yet reviewed; j not available";
out-of-scope applications listed once. A verify rule SHALL check every count and derived number against a recomputation.
Status: PLANNED (decisions D-0, D-4; D-7 DECIDED 2026-11-02; design 8.6).

#### Scenario: an application with an unresolved must-review item
- WHEN one of an application's gaps has no outcome
- THEN its row reads "Not yet reviewed", it is left out of the counts and the sort, and the summary row counts it in k

#### Scenario: a known gap beside unreviewed passes
- WHEN an aspect holds a confirmed high-severity gap and two unreviewed bulk-confirmable passes
- THEN the aspect cell reads "High gaps", not "Reviewed 1 of 3"

#### Scenario: an aspect with unreviewed passes only
- WHEN all must-review results are resolved and two of four Observability results are unreviewed passes
- THEN Observability reads "Reviewed 2 of 4" in a neutral colour

#### Scenario: an aspect of passes nobody could confirm
- WHEN an aspect has one confirmed pass and three "Cannot confirm"
- THEN the cell reads "Partly confirmed", never "In place"

#### Scenario: an aspect where nothing could be confirmed
- WHEN every result of an aspect is "Cannot confirm"
- THEN the cell reads "Reviewed, nothing confirmed", in a neutral colour

#### Scenario: an aspect with a team-stated pass
- WHEN an aspect's results are confirmed passes and one "Stated by the team" pass
- THEN the cell reads "In place (stated)"

#### Scenario: AS-IS facts
- WHEN the client file shows "Spring Boot 1.5.10"
- THEN it is labelled "read by the tool, not reviewed"

#### Scenario: an application not available
- WHEN one application of 20 failed per-application verify
- THEN the summary row reads "19 of 20 applications in scope shown; 0 not yet reviewed; 1 not available"

#### Scenario: disputed-only application in the ranking
- WHEN an application's only gaps are disputed
- THEN it sorts after applications with confirmed results, with "disputes: 2" shown

#### Scenario: confirmation mode shown
- WHEN a result was confirmed with its aspect
- THEN the client file shows "confirmed with its aspect" beside it

#### Scenario: an unconfirmed remedy
- WHEN a gap was confirmed but its remedy was not
- THEN the remedy shows "suggested, not reviewed"

### Requirement: Home is the Applications table
The report SHALL open on the Applications table: a summary row that recomputes for the filtered set, a filter bar
(language, framework, build, CI, platform, support status, team, criticality), one row per application, one cell per
aspect, sortable by any column, and rows that expand to show the top 3 gaps and links to the application's tabs.
There SHALL be no separate dashboard page.
Status: PLANNED (mock v2 in the scratchpad; mock v3 to be built and agreed first).

#### Scenario: filtering by Jenkins
- WHEN the user filters CI system = Jenkins
- THEN the summary row counts only Jenkins applications

### Requirement: No score anywhere
No screen SHALL show a combined percentage, a maturity percentage or a band. The default order SHALL be: confirmed
ISSUE count, then high gaps, then aspects with high gaps; a grey column SHALL show "checked x of y" (R-06).
Status: PLANNED. Today the per-application "Maturity N%" tile is shown (`ui/core.js:64`).

#### Scenario: an application where little was checked
- WHEN an application has 20 controls undecided
- THEN it is not ranked better for it, and "checked 18 of 38" shows beside it

### Requirement: One vocabulary
State labels SHALL be: In place, Partly in place, Not found, Not seen here, Problem found, Possible issue, Undecided,
Not applicable, Not checked; in the client file also the exact strings listed in design section 11 (outcomes, the
aspect status "Reviewed x of y", the confirmation modes and "read by the tool, not reviewed"); aspect statuses: High gaps, Gaps, In place, In place where checked, Not checked, Not
applicable; nouns: aspect, check, gap, finding, remedy. All SHALL come from one table, and a browser test SHALL fail
when a raw value or another label appears in visible text. No page SHALL carry a "how to read" section (R-15).
Status: PARTIAL (label tables exist; drift remains, UI review A7; "Not found" replaces "missing", red-team F16).

#### Scenario: a raw value
- WHEN a page renders `not_applicable`
- THEN the browser test fails

### Requirement: Colour carries meaning without a guide
Colours SHALL follow the scheme decided on mock v3 (decision D-11). Recommended: red only for a confirmed ISSUE; amber
for gaps, solid for high severity and hollow otherwise; grey hatched for undecided; green for in place. Both schemes
are mocked before the decision.
Status: PLANNED.

#### Scenario: no authentication on a service
- WHEN a high-severity control is "Not found"
- THEN its cell is solid amber, distinct from a red confirmed ISSUE and from a hollow low-severity gap

### Requirement: Findings appear in four places only
Findings SHALL appear in the Assessment tab, the application's Findings tab, the global Findings page and the finding
detail page, and SHALL NOT appear in the AS-IS tab or the Architecture panel. Finding detail SHALL keep the
application in its breadcrumb. Remedy commands SHALL be shown as code and manual steps as text.
Status: PARTIAL (removed from some places, commit c19fc9a).

#### Scenario: from an application's Findings tab to a finding
- WHEN the user opens a finding from an application's tab
- THEN the breadcrumb reads Applications › <app> › Findings › <finding>

### Requirement: No empty or duplicated screens
Timeline, Change impact without an impact run, duplicated Configuration and Components tabs, repeated "facts
confirmed" rings, empty widgets and the sidebar promotion SHALL be removed; an empty panel SHALL collapse to one line.
Status: PLANNED.

#### Scenario: no impact run
- WHEN no change-impact run exists
- THEN Change impact is not in the navigation

### Requirement: Works for 300 applications
Every page SHALL stay usable with 300 applications: counts with a filtered link instead of name lists; the portfolio
architecture as a filterable table with a diagram for one application and its neighbours; paginated rows; a searchable
switcher; report size measured and acceptable to open.
Status: PARTIAL (200-application render test, `tests/test_report_scale.py`; size at 300 not measured: 6 applications
give 962 KB).

#### Scenario: a finding shared by 120 applications
- WHEN a finding occurs in 120 applications
- THEN it shows "120 applications" with a link to the filtered home table, not 120 chips

### Requirement: A Scope page states what was and was not looked at
The report SHALL have one Scope page: files read per area, file roles excluded, blind spots per application, controls
with no detector, tool runs not done, coverage-matrix items not covered, controls always consultant-confirmed,
and reference data with its review status.
Status: PARTIAL (blind spots on the Assessment tab, commit 9479a59; the page is PLANNED).

#### Scenario: a client asks about N+1 queries
- WHEN the client asks whether N+1 queries were checked
- THEN the Scope page says "N+1 query candidates: not covered in this version"

### Requirement: The report is one offline file and is tested in a browser
The report SHALL be one self-contained HTML file with no network resources, and a headless-browser test SHALL render
every view without script errors or visible "undefined", "NaN" or "null". The release check SHALL run on a machine with
Chrome; a skipped browser test SHALL NOT count as passing.
Status: PARTIAL. BUILT: `tests/test_report.py::ReportTest.test_report_renders_every_view_in_a_browser_without_errors` (it caught the missing "in place where checked" colour fixed in commit
9479a59). PLANNED: the test skips silently without Chrome (`tests/test_report.py:45`).

#### Scenario: no Chrome on the machine
- WHEN the browser test is skipped
- THEN the release check reports it as not run, not passed

### Requirement: Designs are mocked with real data and agreed first
A structural change to the report SHALL first be built as a mock on a verified run's data, reviewed and agreed (R-15).
Status: followed as practice (mock v1, v2); a working practice, not code, so it has no test.

#### Scenario: mock v3
- WHEN the home redesign starts
- THEN mock v3 is built on the latest verified run, in both colour schemes, and shown before any change under
  `app_insight/ui/`
