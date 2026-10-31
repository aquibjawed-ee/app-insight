from __future__ import annotations

import re

from evidence import find_lines, fact, grep_files, file_ev, read_lines


VERSION = "0.2.0"


def detect(ctx) -> dict:
    r = ctx.repo
    out = {}
    lib = grep_files(r, ctx.build_files, r"springdoc-openapi|springfox|swagger-core|swagger-annotations|smallrye-openapi|swagger-jaxrs|resteasy-openapi", 3)
    # @Tag / @Operation are also JUnit 5 and other libraries' annotations: a file counts only when it imports an OpenAPI library
    ann = [e for e in grep_files(r, ctx.src_main_java, r"@OpenAPIDefinition|@Operation\b|@Tag\(|@Api\b|@ApiOperation", 60)
           if find_lines(r, e["path"], r"import\s+(?:io\.swagger|org\.eclipse\.microprofile\.openapi|io\.micronaut\.openapi|springfox)", 1)][:3]
    spec_files = [f for f in ctx.files if (re.search(r"(^|/)(openapi|swagger)[^/]*\.(ya?ml|json)$", f)
                                           or re.search(r"(^|/)(openapi|swagger)/.+\.(ya?ml|json)$", f))
                  and "/node_modules/" not in f and not ctx._aux(f)]
    spec_ev = [file_ev(f, 1, (read_lines(r, f) or [""])[0]) for f in spec_files[:5]]
    ctrl = grep_files(r, ctx.src_main_java, r"@RestController|@Controller\b|@Path\(", 5)
    n_ctrl = len({e["path"] for e in grep_files(r, ctx.src_main_java, r"@RestController|@Controller\b|@Path\(", 10_000)})
    off = grep_files(r, ctx.props, r"springdoc\.api-docs\.enabled\s*[:=]\s*false|springdoc\.swagger-ui\.enabled\s*[:=]\s*false", 3)
    # servers that do not use Spring/JAX-RS controllers: http4k, Ktor, Vert.x, Javalin, Micronaut, Quarkus
    fw = grep_files(r, ctx.build_files, r"org\.http4k[:\"' ]|io\.ktor[:\"']?\s*[:,]?\s*[\"']?ktor-server|io\.vertx[:\"']\s*vertx-web|io\.javalin|io\.micronaut[:\"']\s*micronaut-http-server|io\.quarkus[:\"']\s*quarkus-(?:resteasy|rest)\b", 3)
    if n_ctrl:
        out["http_endpoints_present"] = fact({"controller_files": n_ctrl}, "CONFIRMED", ctrl)
    elif fw:
        out["http_endpoints_present"] = fact({"controller_files": 0, "server_frameworks": sorted({m.group(0) for e in fw for m in [re.search(r"http4k|ktor-server|vertx-web|javalin|micronaut-http-server|quarkus-\w+", e["snippet"])] if m})},
                                             "INFERRED", fw, "an HTTP server framework is a declared dependency; no controller annotations were looked for in its style")
    else:
        out["http_endpoints_present"] = fact({"controller_files": 0}, "NOT_FOUND", [])
    out["openapi_library"] = fact([e["snippet"] for e in lib], "CONFIRMED" if lib else "NOT_FOUND", lib)
    out["openapi_annotations"] = fact(bool(ann), "CONFIRMED" if ann else "NOT_FOUND", ann)
    out["openapi_spec_files"] = fact(spec_files, "CONFIRMED" if spec_files else "NOT_FOUND", spec_ev)
    out["openapi_disabled_by_config"] = fact(bool(off), "CONFIRMED" if off else "NOT_FOUND", off)
    if not n_ctrl and not fw:
        state, st, ev = "no_http_endpoints", "NOT_FOUND", []
    elif off:
        state, st, ev = "library_present_but_disabled" if lib else "disabled", "CONFIRMED", off
    elif lib:
        state, st, ev = "exposed_via_library", "INFERRED", lib
    elif spec_files:
        state, st, ev = "static_spec_only", "CONFIRMED", spec_ev
    else:
        state, st, ev = "not_exposed", "NOT_FOUND", (ctrl or fw)[:1]
    out["openapi_exposure"] = fact(state, st, ev, "exposed_via_library is INFERRED: the dependency is "
                                   "present and not disabled, but no running app was queried")
    return out
