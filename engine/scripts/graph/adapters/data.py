"""Data and platform adapter. Reuses the existing integration detector (`detectors.integrations.detect_dependencies`) for what the
application is configured with, then adds connection identity (host/port/database when literal) and persistence usage
(JPA entities, Spring Data repositories, JdbcTemplate). Test-only, stub and tooling findings are not relationships."""
from __future__ import annotations

import re
from typing import Dict, List

import evidence
from detectors import integrations as I
from graph.model import Graph, sid
from graph.adapters.common import Config, annotation_text, ev, mask_comments, string_literals

JDBC = re.compile(r"jdbc:(postgresql|mysql|mariadb|oracle|sqlserver|db2|h2|hsqldb)(?::\w+)?:(?://|@)(?:[^/@\s]*@)?([^:/;?\s,]+)(?::(\d+))?[/:;]?([\w.-]*)", re.I)
JDBC_TECH = {"postgresql": "PostgreSQL", "mysql": "MySQL", "mariadb": "MariaDB", "oracle": "Oracle", "sqlserver": "SQL Server"}
MONGO = re.compile(r"mongodb(?:\+srv)?://(?:[^/@\s]*@)?([^:/,\s]+)(?::(\d+))?/?([\w.-]*)", re.I)
REDIS = re.compile(r"rediss?://(?:[^/@\s]*@)?([^:/\s]+)(?::(\d+))?", re.I)
DB_KINDS = (I.DB, I.CACHE, I.SEARCH, I.STORE)
BROKER_FAMILY = {"Kafka": "kafka", "RabbitMQ": "rabbitmq", "ActiveMQ / Artemis": "jms", "IBM MQ": "jms", "JMS broker (not identified)": "jms", "AWS SQS": "sqs"}


def _ev_from_at(ctx, at: str, app: str):
    path, _, ln = at.rpartition(":")
    lines = evidence.read_lines(ctx.repo, path) or []
    n = int(ln)
    return ev(path, n, lines, app) if 0 < n <= len(lines) else None


def connections(cfg: Config) -> Dict[str, List[dict]]:
    """tech -> [{host, port, database, evidence}] from literal connection strings in application configuration."""
    out: Dict[str, List[dict]] = {}
    seen = set()
    for key in sorted(cfg.values):
        for val, e in cfg.all_values(key):
            if "${" in val:
                continue
            m = JDBC.search(val)
            if m and m.group(1).lower() in JDBC_TECH:
                tech = JDBC_TECH[m.group(1).lower()]
                c = {"host": m.group(2).lower(), "port": m.group(3), "database": m.group(4) or None, "evidence": e}
            elif MONGO.search(val):
                m = MONGO.search(val)
                tech, c = "MongoDB", {"host": m.group(1).lower(), "port": m.group(2), "database": m.group(3) or None, "evidence": e}
            elif REDIS.search(val):
                m = REDIS.search(val)
                tech, c = "Redis", {"host": m.group(1).lower(), "port": m.group(2), "database": None, "evidence": e}
            else:
                continue
            k = (tech, c["host"], c["port"], c["database"])
            if k not in seen:
                seen.add(k)
                out.setdefault(tech, []).append(c)
    return out


def dependencies(ctx, g: Graph, app: str, app_node: str, cfg: Config):
    (items, _), (libs, _), _counts = I.detect_dependencies(ctx)
    conns = connections(cfg)
    for it in items:
        tech, kind, where, strength = it["technology"], it["kind"], it["where"], it["evidence_strength"]
        ats = [x for x in (_ev_from_at(ctx, a, app) for a in it["at"]) if x]
        if where != "application":
            g.skip("%s (%s)" % (tech, kind), "found in %s: not part of the application's runtime" % where, ats)
            continue
        if kind in (I.MIG, I.STUB):
            g.skip("%s (%s)" % (tech, kind), "schema-migration tools and stubs/emulators are not external dependencies", ats)
            continue
        if not ats:
            continue
        mech = {"configured": "configuration", "local setting": "configuration", "declared": "dependency_declaration", "named in source": "source_call"}[strength]
        basis = {"configured": "static_configured", "local setting": "inferred", "declared": "declared", "named in source": "inferred"}[strength]
        conf = {"configured": "high", "local setting": "low", "declared": "low", "named in source": "low"}[strength]
        note = "a dependency declaration shows the library is present, not that it is used" if strength == "declared" else \
            "only a local/dev profile setting was found" if strength == "local setting" else None
        if kind in DB_KINDS:
            role = {I.DB: "database", I.CACHE: "cache", I.SEARCH: "search index", I.STORE: "object store"}[kind]
            c = conns.get(tech, [])
            if len(c) == 1 and strength == "configured":
                x = c[0]
                nid = "db:%s:%s:%s:%s" % (tech, x["host"], x["port"] or "-", x["database"] or "-")
                attrs = {"technology": tech, "role": role, "embedded": it["embedded"],
                         "connection": {"host": x["host"], "port": x["port"], "database": x["database"]}, "identity": "connection"}
                ats = ats[:2] + ([x["evidence"]] if x["evidence"] not in ats else [])
            else:
                nid = "db:%s:%s" % (app, tech)
                attrs = {"technology": tech, "role": role, "embedded": it["embedded"], "identity": "application-local",
                         "identity_note": "no literal host/database found, so this is not matched with other applications' databases" if len(c) != 1 else None}
                if len(c) > 1:
                    attrs["identity_note"] = "%d different %s connection strings found: not attributed to one database" % (len(c), tech)
            g.node(nid, "Database", tech, attrs, ats[:2], app=None if attrs["identity"] == "connection" else app)
            g.edge("DEPENDS_ON", app_node, nid, mech, basis, conf, ats[:3], attrs={"role": role, "modules": it["modules"], "embedded": it["embedded"]}, note=note)
        elif kind == I.MQ:
            fam = BROKER_FAMILY.get(tech)
            nid = "broker:%s:%s" % (app, tech)
            g.node(nid, "MessageBroker", tech, {"family": fam, "technology": tech}, ats[:2], app=app)
            g.edge("DEPENDS_ON", app_node, nid, mech, basis, conf, ats[:3], attrs={"modules": it["modules"]}, note=note)
        elif kind == I.SVC:
            if tech.startswith("Endpoint:"):
                for h in it["hosts"][:3]:
                    nid = "ext:" + h
                    g.node(nid, "ExternalSystem", h, {"host": h, "named_by": tech}, ats[:1])
                    g.edge("DEPENDS_ON", app_node, nid, "configuration", "static_configured", "medium", ats[:1],
                           {"state": "not_applicable", "reason": "external host"},
                           {"role": "configured endpoint", "setting": tech[len("Endpoint: "):], "environments": it["host_envs"]},
                           "an address named in configuration: what runs there, and whether it is called, is not known")
            # "HTTP service: <name>" client declarations are modelled richer by the REST adapter (CALLS_API)
        elif kind in (I.IDP, I.PLAT, I.MON, I.MAIL):
            nid = "ext:%s:%s" % (kind, tech)
            g.node(nid, "ExternalSystem", tech, {"role": I.GROUP.get(kind), "technology": tech}, ats[:1])
            g.edge("DEPENDS_ON", app_node, nid, mech, basis, conf, ats[:3], {"state": "not_applicable", "reason": "third-party service"}, {"role": I.GROUP.get(kind)}, note=note)


SQL_TABLE = re.compile(r"\b(?:from|join|into|update)\s+(?:only\s+)?([A-Za-z_][\w.\"`]*)", re.I)
CREATE_TABLE = re.compile(r"\bcreate\s+table\s+(?:if\s+not\s+exists\s+)?([A-Za-z_][\w.\"`]*)", re.I)
NOT_TABLE = {"select", "set", "values", "dual", "lateral", "unnest", "generate_series", "only", "table", "information_schema"}


def _tname(x):
    return x.strip('"`').lower()


def sql_tables(sql):
    """Table names a SQL literal reads or writes (after FROM / JOIN / INTO / UPDATE), lower-cased, in first-seen order. CTE aliases, functions and
    keywords are not tables; text inside comments and string literals is not looked at."""
    sql = re.sub(r"--[^\n]*|/\*.*?\*/", " ", sql, flags=re.S)
    ctes = {m.group(1).lower() for m in re.finditer(r"\b(\w+)\s+as\s*\(", sql, re.I)}
    out = []
    for m in SQL_TABLE.finditer(sql):
        t = _tname(m.group(1))
        if t and t not in NOT_TABLE and t not in ctes and not t.startswith("(") and t not in out:
            out.append(t)
    return out


def snake(name):
    return re.sub(r"(?<=[a-z0-9])([A-Z])", r"_\1", name).lower()


def _sql_kind(sql):
    k = re.match(r"\s*(\w+)", sql)
    return "WRITES_TO" if k and k.group(1).lower() in ("insert", "update", "delete", "merge", "create", "alter", "drop", "truncate") else "READS_FROM"


def entity_tables(ctx):
    """entity class -> table name from @Table(name = "x") or Spring's default naming (snake_case of the class name)."""
    out = {}
    for f in ctx.src_main_java:
        lines = mask_comments(evidence.read_lines(ctx.repo, f) or [])
        for i, ln in enumerate(lines):
            m = re.search(r"\b(?:class|data class)\s+(\w+)", ln)
            if not m:
                continue
            head = "\n".join(lines[max(0, i - 6):i + 1])
            if "@Entity" in head:
                t = re.search(r"@Table\s*\([^)]*?name\s*=\s*\"([^\"]+)\"", head)
                out[m.group(1)] = _tname(t.group(1)) if t else snake(m.group(1))
    return out


def _strip_sql_comments(lines):
    """Same number of lines with `-- ...` and `/* ... */` blanked, so a commented-out statement is never evidence (evidence-rules 10)."""
    text = "\n".join(lines)
    text = re.sub(r"/\*.*?\*/", lambda m: "\n" * m.group(0).count("\n"), text, flags=re.S)
    return [re.sub(r"--.*$", "", x) for x in text.split("\n")]


def owned_tables(ctx, app):
    """Tables the application creates itself: Flyway/plain SQL migrations, schema.sql and Liquibase createTable changes. {table: evidence}."""
    out = {}
    for f in sorted(ctx.files):
        if ctx._aux(f) or ctx._test_module(f) or "/src/test/" in "/" + f:
            continue
        if re.search(r"(?:^|/)(?:db/migration|db/changelog|migrations?|flyway)/.+\.sql$|(?:^|/)schema[^/]*\.sql$|(?:^|/)V\d[\w.]*__[\w.-]+\.sql$", f):
            lines = evidence.read_lines(ctx.repo, f) or []
            for i, ln in enumerate(_strip_sql_comments(lines), 1):
                for m in CREATE_TABLE.finditer(ln):
                    out.setdefault(_tname(m.group(1)), ev(f, i, lines, app))
        elif re.search(r"(?:^|/)(?:db/changelog|liquibase)/.+\.(?:xml|ya?ml)$", f):
            lines = evidence.read_lines(ctx.repo, f) or []
            live = evidence._xml_live_mask(lines) if f.endswith(".xml") else [not x.lstrip().startswith("#") for x in lines]
            for i, ln in enumerate(lines, 1):
                if not live[i - 1]:
                    continue
                m = re.search(r"<createTable[^>]*tableName=\"([^\"]+)\"", ln)
                if m:
                    out.setdefault(_tname(m.group(1)), ev(f, i, lines, app))
    return out


REPO_BASES = [(re.compile(r"\b(?:Jpa|Crud|PagingAndSorting|ListCrud|ListPagingAndSorting|Reactive\w*Crud|R2dbc|Mongo|ReactiveMongo|Reactive\w*)Repository\b"), True),
              (re.compile(r"\bJpaSpecificationExecutor\b"), False)]
FAMILY_OF_BASE = [(re.compile(r"Mongo"), "MongoDB"), (re.compile(r"Redis|KeyValue"), "Redis"), (re.compile(r"Elasticsearch"), "Elasticsearch / OpenSearch"),
                  (re.compile(r"Jpa|R2dbc|Crud|PagingAndSorting"), "sql")]


def persistence(ctx, g: Graph, app: str, app_node: str):
    """READS_FROM / WRITES_TO from Spring Data repositories and JdbcTemplate use. Capabilities inherited from the repository base
    interface are INFERRED (the base type offers save/find; a call was not traced). The target is the application's one database
    of the right kind; with none or several the target stays unresolved and says why."""
    r = ctx.repo
    dbs = [n for n in g.nodes.values() if n["type"] == "Database" and n["attrs"].get("role") == "database" and (n["app"] in (app, None))
           and any(e["source"] == app_node and e["target"] == n["id"] for e in g.edges.values())]

    def target(family: str, e: dict):
        if family == "sql":
            cand = [d for d in dbs if d["attrs"]["technology"] not in ("MongoDB", "Redis", "Elasticsearch / OpenSearch", "Cassandra") and not d["attrs"].get("embedded")] or \
                   [d for d in dbs if d["attrs"]["technology"] not in ("MongoDB", "Redis", "Elasticsearch / OpenSearch", "Cassandra")]
        else:
            cand = [d for d in g.nodes.values() if d["type"] == "Database" and d["attrs"].get("technology") == family
                    and any(x["source"] == app_node and x["target"] == d["id"] for x in g.edges.values())]
        if len(cand) == 1:
            return cand[0]["id"], {"state": "resolved"}
        nid = "unresolved:db:%s:%s" % (app, family)
        reason = ("the application has no %s database dependency to attach this to" % family) if not cand else \
                 "the application has %d candidate databases: %s" % (len(cand), ", ".join(sorted(c["attrs"]["technology"] for c in cand)))
        g.node(nid, "Database", "database not identified (%s access)" % family, {"unresolved": True, "reason": reason, "technology": family}, app=app)
        state = "ambiguous" if cand else "unresolved"
        res = {"state": state, "reason": reason}
        if cand:
            res["candidates"] = sorted(c["id"] for c in cand)
        return nid, res

    ent = entity_tables(ctx)
    for f in ctx.src_main_java:
        lines = evidence.read_lines(r, f) or []
        masked = mask_comments(lines)
        text = "\n".join(masked)
        module = ctx.module_of(f)
        # Spring Data repositories
        for i, ln in enumerate(masked):
            m = re.search(r"\binterface\s+(\w+)\s*(?:<[^>]*>)?\s*(?::|extends)\s*([^{]*)", ln)
            if m and re.search(r"Repository\b", m.group(2)):
                base = m.group(2)
                fam = next((t for rx, t in FAMILY_OF_BASE if rx.search(base)), None)
                if fam is None:
                    g.skip("repository %s in %s" % (m.group(1), f), "base interface does not identify a data store", [ev(f, i + 1, lines, app)])
                    continue
                e = ev(f, i + 1, lines, app)
                tn, res = target(fam, e)
                full = re.search(r"\b(?:Jpa|Crud|PagingAndSorting|ListCrud|ListPagingAndSorting|Mongo|ReactiveMongo|R2dbc|Reactive\w*Crud|ElasticsearchRepository|Elasticsearch)\w*\b", base) is not None
                wr = full or any(re.search(r"\b(?:save|delete|insert|update|remove)\w*\s*\(", x) for x in masked[i:i + 40])
                basis = "inferred" if res["state"] == "resolved" else "unresolved"
                em = re.search(r"<\s*([\w.]+)\s*,", base)
                etable = [ent.get(em.group(1).split(".")[-1]) or snake(em.group(1).split(".")[-1])] if em and fam == "sql" else []
                for etype in ("READS_FROM",) + (("WRITES_TO",) if wr else ()):
                    g.edge(etype, app_node, tn, "source_annotation", basis, "medium" if res["state"] == "resolved" else "low", [e], res,
                           dict({"repository": m.group(1), "module": module, "store": fam, "capability_source": "inherited from %s" % base.strip()[:60]}, **({"tables": etable} if etable else {})),
                           "capability inherited from the repository base type; individual calls were not traced")
                # native queries on the repository: the SQL names the tables it touches (JPQL names entities, so it is skipped)
                end = next((j for j in range(i + 1, len(masked)) if re.search(r"\binterface\b", masked[j])), len(masked))
                for j in range(i + 1, end):
                    if "@Query" in masked[j]:
                        at = annotation_text(masked, j)
                        if re.search(r"nativeQuery\s*=\s*true", at):
                            lits = [x for x in string_literals(at)]
                            sql = max(lits, key=len) if lits else ""
                            tb = sql_tables(sql)
                            if tb:
                                e2 = ev(f, j + 1, lines, app)
                                tn2, res2 = target(fam, e2)
                                g.edge(_sql_kind(sql), app_node, tn2, "source_annotation", "static_configured" if res2["state"] == "resolved" else "unresolved", "high" if res2["state"] == "resolved" else "low",
                                       [e2], res2, {"module": module, "store": fam, "tables": tb, "via": "native query"})
        # JdbcTemplate use: only on variables DECLARED with a JDBC template type (Java `JdbcTemplate t`, Kotlin `t: JdbcTemplate`)
        ty = r"(?:Named ParameterJdbcTemplate|JdbcTemplate|NamedParameterJdbcTemplate|JdbcClient)".replace(" ", "")
        names = set(re.findall(r"%s\s*(?:<[^;(){}=]*?>)?\s+(\w+)\s*[;,)=]" % ty, text)) | set(re.findall(r"(\w+)\s*:\s*%s\b" % ty, text))
        for n in sorted(names):
            for i, ln in enumerate(masked):
                m = re.search(r"\b%s\s*\.\s*(query\w*|update|batchUpdate)\s*\(" % re.escape(n), ln)
                if m:
                    e = ev(f, i + 1, lines, app)
                    tn, res = target("sql", e)
                    etype = "READS_FROM" if m.group(1).lower().startswith("query") else "WRITES_TO"
                    lits = string_literals(ln[m.end():])
                    sql = lits[0] if lits else ""
                    tb = sql_tables(sql) if sql else []
                    if tb:
                        etype = _sql_kind(sql)
                    g.edge(etype, app_node, tn, "source_call", ("static_configured" if tb else "inferred") if res["state"] == "resolved" else "unresolved", ("high" if tb else "medium") if res["state"] == "resolved" else "low",
                           [e], res, dict({"module": module, "via": "JdbcTemplate"}, **({"tables": tb} if tb else {})), None if tb else "a JDBC call was found; the SQL text is not a literal")


def ownership(ctx, g: Graph, app: str, app_node: str):
    """Tables created by this application's own migrations are attached to its one database relationship (`tables_owned`); with several candidate
    databases the ownership cannot be placed and is recorded as not a relationship."""
    own = owned_tables(ctx, app)
    if not own:
        return
    dbe = [e for e in g.edges.values() if e["source"] == app_node and e["type"] == "DEPENDS_ON" and g.nodes[e["target"]]["type"] == "Database"
           and g.nodes[e["target"]]["attrs"].get("role") == "database" and not g.nodes[e["target"]]["attrs"].get("embedded")]
    if len(dbe) == 1:
        dbe[0]["attrs"]["tables_owned"] = sorted(own)
        for t in sorted(own)[:3]:
            if own[t] not in dbe[0]["evidence"]:
                dbe[0]["evidence"].append(own[t])
    else:
        g.skip("tables created by migrations (%s)" % ", ".join(sorted(own)[:4]), "the application has %d candidate databases, so ownership is not attached to one" % len(dbe), list(own.values())[:2])
