# Application-first report mock (real run)

UI mock only; the product report is unchanged. Base layout, table, tabs, drawer and compare view come from the
owner's application-first mock (`app.js`, `styles.css`, `build.py`, `data-demo.js` with its synthetic icons and helpers).

| File | Role |
|---|---|
| `real_data.py` | reads one run (`analysis/`, `run.json`, `verify.json`) and writes `data-real.js` |
| `real.js` | overrides for the AS-IS, Architecture, Assessment and Findings tabs, drawer, architecture SVG |
| `estate.js` | Estate page: built with · shared · most missed; every count opens the filtered table |
| `extra.css` | styles for the above |
| `build_real.py` | patches `app.js`, joins everything into `mock.html` |
| `check.py` | counts per application and edges, recomputed from the run; secret and network checks |
| `llm-fill.json` | optional model layer (not committed): fields, gaps, summary; validated by `real_data.py` |

Build and check (`<run>` = a run folder, e.g. `…/runs/20261102-195900`):

```
python3 -I build_real.py <run>
python3 -I check.py <run>
```

`mock.html`, `data-real.js` and `llm-fill.json` hold client data and are gitignored.
