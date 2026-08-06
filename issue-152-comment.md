Spent some time reading `Hohonu_QARTOD`, `standard_knowledge`, `GenericThings`, and this app side by side. Two findings reshape the scope before any of the design questions matter.

## Two things that change the scope

**1. `regions/model.py` is dead code.** The Gulf of Maine suite — Hannah Baranes' help text verbatim, and `calculate_defaults(mllw, mhhw)` — is already upstream in `standard_knowledge` at `core/src/qartod/water_level.rs:78`, alongside a `long_island_sound` sibling that Hohonu_QARTOD never had. The CLI fixtures show the whole surface working end to end:

```
$ standard_knowledge qc config sea_surface_height_above_geopotential_datum gulf_of_maine mllw=0.2 mhhw=3
Generated configuration for Gulf of Maine:
qartod:
  gross_range_test:
    suspect_span: [-1.1716, 4.8288]
    fail_span: [-1.1716, 4.8288]
  rate_of_change_test:
    threshold: 0.2286
  spike_test:
    suspect_threshold: 0.2286
    fail_threshold: 0.4572
  flat_line_test:
    tolerance: 0.03048
    suspect_threshold: 7200
    fail_threshold: 10800
```

158 lines delete on contact, and the four hand-written test panels collapse into one metadata-driven factory.

**2. marimo forbids defining a variable in more than one cell.** The Streamlit app's central idiom —

```python
if data_source == HOHONU_DATA_SOURCE:
    data, config = load_hohonu_streamlit_data_and_config()
elif data_source == ERDDAP:
    data, config, column = load_erddap_data_and_config()
```

— cannot be transcribed as cells. Neither can `qartod.update(...)` called from inside each of four `st.expander` blocks. Both collapse into plain functions plus a single dispatch cell. This isn't stylistic; the notebook refuses to run otherwise, and we've been bitten once already (558c745).

Everything below follows from those two.

---

## Shape: two pages now, one as a sub-issue

Recommendation, rather than one mega-page mirroring the Streamlit layout:

| File | Route | Responsibility |
|---|---|---|
| `qc_water_level.py` | `/qc_water_level` | The Hohonu_QARTOD replacement. Sources: ERDDAP, Hohonu, Greenstream, Things. Datums → suite scaffold → four panels → a validated `index.md`. |
| `qc_general.py` | `/qc_general` | Standard-name picker → suite or blank slate → same panels → bare `qartod:` block. |
| `things_config.py` | `/things_config` | GenericThings JSONPath builder — its own sub-issue, since it's dataset-config generation rather than QC and already has a notebook upstream. |

Shared and marimo-free, following the `climatology_core.py` split: `qc_core.py` (config assembly, `run_qc`, the test-spec table), `qc_charts.py`, `qc_config.py` (per-source `index.md` emitters, pydantic-validated *before* download — see below), `standards.py` (cached `StandardsLibrary`), `sources.py` plus one `source_*.py` per API. Then `qc_ui.py`, which imports marimo and returns one `mo.ui.dictionary` composite per QARTOD test — one composite is one element assigned in one cell, which is what makes a panel shareable between two notebooks. Each panel takes a **seed dict**, so scaffolded defaults and imported configs (see below) feed it through the same argument rather than two code paths. `common.py` already returns marimo objects from a plain module (`sidebar_menu`, `admonition`, `neracoos_logo`), so there's precedent.

**Why not per-source pages:** the QC-tuning half — the actual value — would be duplicated four to six times, and marimo can't share cells between notebooks. Only plain modules cross that boundary.

**Why not one page with `mo.routes`:** independent `mo.stop` guards, per-page query-param namespaces, per-page kernels, and one free line each in `tests/e2e/test_pages.py:PAGES`.

Keep the modules flat rather than a `sources/` package — the Dockerfile does `COPY --link *.py style.css ./`, so a subdirectory costs a Dockerfile edit for no benefit.

Hidden-page mechanics are already solved: mount in `app.py`, omit from `common.sidebar_menu()` and `root.py`'s cards, still add to `PAGES`. Exactly what `calculate_datums.py` does — which is also the closest structural analogue we have (ERDDAP dropdown → `mo.stop` guard → load → external computation).

---

## What doesn't translate

Ranked by risk.

| Streamlit | marimo reality | Risk |
|---|---|---|
| Single-definition rule (above) | Hard error, not a style issue | **High** |
| ~14 `st.stop()` / `st.warning()` pairs in the loaders | `mo.stop()` halts only its own cell and descendants. It works from a called function, but couples the client module to marimo and makes it un-unit-testable. | **High** |
| `st.number_input(value=test_defaults.…)` | The panel cell depends on the datum inputs, so **every MHHW/MLLW keystroke recreates the elements**, discarding manual edits. | **High** |
| `st.secrets` / password inputs | See below | **High** |
| `st.cache_data` | `mo.cache` is content-addressed and per-kernel, but kernels are threads of one shared server process | **Medium** |
| `st.data_editor` column renaming | Exists as `mo.ui.data_editor`, but it's overkill for its two jobs | **Medium** |
| `st.sidebar` for source/station/date controls | Sidebar is already `common.sidebar_menu()` on every page | **Medium (UX)** |
| `st.expander` / `popover` / `columns` / `toggle` | `mo.accordion` / nested accordion (no popover) / `mo.hstack(widths=[1,3])` / `mo.ui.switch` | Low |
| `st.date_input` returning a 1-or-2-tuple | `mo.ui.date_range` always returns a 2-tuple — this actually fixes the intermittent `date_range[1]` IndexError | Low |
| `print()` debugging in `things_api.py` / `greenstream_api.py` | Goes to the container log the e2e job greps | Low |

Mitigations for the top three:

- **`st.stop()`:** loaders raise `SourceNotReady("Enter a station ID")` / `SourceLoadError`; the dispatch cell catches and converts to `mo.stop(True, common.admonition(...))`. This is precisely the existing `common.ErddapLoadError` pattern, `sentry_event_id` and all.
- **Widget recreation:** given the overwrite-and-highlight decision below, recreation is actually the behaviour we want — but it still needs an `mo.ui.form` / `run_button` around the datum inputs so it fires on submit rather than on every keystroke.
- **Caching:** cache only unauthenticated fetches (mirroring `common._load_ts_cached`), never key a cache on an API key, and copy `common.load_ts`'s `.copy()` discipline since `run_qc` does `pd.concat(..., axis=1)` and callers mutate.

On `st.data_editor`: I'd **delete it** rather than port it. Its only jobs are stripping `" (m)"` suffixes and dodging existing `*_qartod_*` columns. A regex plus one `mo.ui.dropdown` of columns — what `calculate_datums.py:64` already does — covers both.

One genuine win: with one composite per test, editing spike thresholds re-runs spike QC → spike chart → merged dict → aggregate. The other three charts are untouched. Streamlit re-runs the entire script on any change.

Not from Streamlit, but worth budgeting for: `ioos_qc` 2.3.0 against pandas 3.0.3 / numpy 2.5.0 is **unverified**, and unit tests run with `filterwarnings = ["error"]`.

---

## Charts: keeping bokeh is fine, and cheap

You're right that these don't need branding, and migrating the bokeh plots is genuinely low-cost:

- marimo ships a first-class bokeh formatter (`marimo/_output/formatters/bokeh_formatters.py`), so figures render natively with no glue.
- bokeh 3.9.2 is on conda-forge. The source's `bokeh <= 2.4.3` pin can't be honoured on py3.13 anyway.
- The only code change is `p1.circle(…, size=…)` → `p1.scatter(…, size=…)` in ~8 places. In 3.9.2 `circle(size=)` still forwards to `scatter()`, but emits a deprecation added in 3.4.0 — and `filterwarnings = ["error"]` would turn that into a test failure.

Cost to be honest about: a second charting stack beside Altair/vegafusion (image size, two idioms in one repo). Worth revisiting only if the image gets uncomfortable.

One constraint either way: **QC results must never go through `common.resample_to_budget`** — averaging flags is meaningless. Cap the date range instead, and put per-test charts behind `mo.accordion` / `mo.lazy` so five 10k-point figures aren't all rendered at once.

---

## Input: pre-loading existing configs

Good news — `ioos_qc` already does most of this, so it's much cheaper than it sounds. `Config.__init__` accepts a dict, a **JSON *or* YAML string**, a `StringIO`, a file path, or an `xarray.Dataset`. `load_config_as_dict` just tries each in turn, so paste and upload are the same code path with no format picker and no parser to write.

**1 & 2 — paste or upload.** `mo.ui.text_area` and `mo.ui.file` both feed `Config(...)`. The only real work is telling the two kinds of document apart: a bare QARTOD config (`contexts:` / `streams:` / `{var: {qartod: {...}}}`) versus a full dataset `index.md`, where the QARTOD block is nested at `qc.qartod` and the rest of the frontmatter pre-fills title, summary, datums, lat/lon and station identifiers. Sniff for frontmatter delimiters, else try `Config()` directly. Both paths then populate the same widget state.

**3 — from an ERDDAP dataset.** This works because `ioos_qc` writes its own config back into the data. `PandasStore.to_ds()` — which is exactly what `tide_gauges.py:238` and `things.py:187` call — stamps each QC variable with `ioos_qc_module`, `ioos_qc_test`, `ioos_qc_target` and `ioos_qc_config` (the per-test config as a JSON string), falling back to one global `ioos_qc_config` attribute when there's more than one context. And `load_config_from_xarray()` reads exactly those back: global attribute if present, otherwise `filter_by_attrs` over the QC variables, reassembled into `{target: {module: {test: config}}}`.

The Hohonu ERDDAP template preserves them: `erddap.xml.jinja` declares every `*qartod*` variable with `sourceName == destinationName` and no `addAttributes` overriding it, so the source attributes pass straight through — and `ioos_qc_target` still points at `navd88_meters`, which also keeps its name. So the read path is close to:

```python
e.get_info_url(dataset_id, response="csv")   # attributes only, no data download
```

…reassembled into the same dict `load_config_from_xarray` builds. Prefer that over `Config(e.to_xarray())`, which is a one-liner but downloads the whole dataset to read six attributes.

**Two bonuses fall out of the same attributes**, both worth taking:

- `apply_datums()` writes `tidal_datum_offsets_meters` (a JSON dict of every datum) onto the station variable and `tidal_station_datum` globally (`common/config/tidal.py:120-123`). So importing an ERDDAP dataset can pre-fill **the datums as well as the QARTOD config** — which is most of the form.
- Note the datum variables *are* renamed on the way out (`mllw` → `mllw_meters` in the template), so read the offsets from the attribute, not by variable name.

**Two caveats to be honest about:**

- `load_config_from_xarray` returns the streams-less `{var: {qartod: {...}}}` shape, but `index.md` files use `qc.qartod.contexts[0].streams.<var>.qartod`. A small normaliser is needed in both directions — one function in `qc_core.py`, but it needs to exist and be tested, and round-tripping a *multi-context* config through the variable-level attributes is lossy by construction (that's why `to_ds` falls back to a global attribute).
- **I couldn't verify this against a live dataset** — `data.neracoos.org` isn't reachable from where I'm running. The mechanism is confirmed in `ioos_qc/stores.py` and the template, but someone should spend two minutes on `curl 'https://data.neracoos.org/erddap/info/Hohonu_tide_Saugus_MA/index.csv' | grep ioos_qc` before this gets sized as a sub-issue. If the attributes turn out not to survive, the fix is upstream in the jinja template, not here.

This also reshapes the pages slightly: import isn't a fourth source, it's a **pre-step available to every source** — "start from scratch / paste a config / upload an `index.md` / load from an ERDDAP dataset", feeding the same widget state. Worth building `qc_ui.py`'s panels to accept a seed dict from day one rather than retrofitting it.

### Re-scaffolding over an import: overwrite, but say so

When someone imports a config and then changes suite or edits MHHW/MLLW, the freshly scaffolded values win — and every field that moved is marked as changed. That's the right call for two reasons beyond the UX one:

- **It's what marimo does anyway.** The panel cell depends on the datum inputs, so changing them recreates the elements at the new defaults. Overwrite is the path of least resistance; making the import sticky would mean holding a shadow copy in `mo.state` and reconciling it on every re-run — the two-code-path outcome. What this *does* still need is the `mo.ui.form` / `run_button` around the datum inputs, so re-scaffolding fires once on submit rather than on every keystroke; otherwise the changed-markers flicker through intermediate values as someone types `3` → `3.` → `3.1`.
- **The changed-set is computed once and used twice.** Marking a field in the UI and recording provenance in the output are the same diff — `{param: (previous_value, scaffolded_value)}`, held alongside the seed dict. So this costs a dict comparison, not a feature.

Mechanically, marimo UI element labels are markdown, so a per-field marker goes straight into the label the panel factory already builds — no custom component needed. I'd pair that with one summary line above the tests ("re-scaffolding from `gulf_of_maine` changed 3 values: gross_range suspect_span, spike fail_threshold, …"), since a reviewer scanning a page of numbers will read one sentence before they notice six inline markers. Keeping the pre-scaffold dict for one step also makes an undo affordance nearly free, if that turns out to be wanted.

---

## Output: the schema exists, and the Streamlit app doesn't match it

Thanks for the `tidal.py` pointer — that closes the question, and it turns out to be a bigger deal than "there's a schema somewhere". Every water-level source already has a concrete pydantic model subclassing `TidalDatasetConfig`:

| Source | Class | Source-specific fields |
|---|---|---|
| Hohonu | `HohonuDatasetConfig` (`datasets/Hohonu/dataset_config.py`) | `job_name`, `short_name`, `station_id`, `hohonu_cleaned`, `start_dt`, `latitude`, `longitude`, `summary`, `cron_schedule`, `auto_materialize`, `aggregated_memory` |
| Greenstream | `GreenstreamDatasetConfig` | `slug`, `station_id`, `greenstream_id`, `start_date`, `latitude`, `longitude`, `summary`, `cron_schedule` |
| Things (Brown/URI) | `ThingsDatasetConfig` (`datasets/Brown/3CRS/`) | `device_id`, `slug`, `application_id`, `sensor_type`, `navd88_elevation_meters`, `start_date`, `mqtt_subscribe`, `disable_datum_conversion` |
| Generic Things | `GenericThingsDatasetConfig` | `field_mappings`, `substitutions.erddap.data`, … (not tidal) |

All inherit `TidalDatasetConfig.datums: Datums` and `DatasetConfig` (`title`, `services`, `qc: QCConfig`, `attributes`, `links`, `active`, `substitutions`).

**The Streamlit app's output does not validate against this.** Concretely:

- It emits `{"datums": {"manual_datums": {...}}}` (`src/app.py:398-401`). `manual_datums` appears **nowhere** in `NERACOOS_ERDDAP_K8S` — `Datums` is flat, with `mhhw`/`mhw`/`mtl`/`msl`/`mlw`/`mllw` and `date_calculated`/`calculation_start_date`/`calculation_end_date` as direct fields. Compare `Hohonu/Massachusetts/Saugus/index.md`, which has a bare `datums: {mhhw: 0.0, mllw: 0.0}`.
- Hohonu wants `start_dt` (datetime); the app emits `start_date`. It also requires `job_name` and `short_name`, which the app never emits.
- Greenstream wants `greenstream_id` + `slug`; the app emits `site_id`.
- `services`, `attributes.extends` and `title` are effectively required for a usable dataset and are either absent or optional in the app's output.
- Everything else the app emits (`station_id` on non-Hohonu sources, `navd88_meters`, bare `latitude`/`longitude` on Things) is silently dropped by pydantic's default `extra="ignore"`.

The one part that *is* right: `qc.qartod` is a plain `dict` on `QCConfig`, passed straight to `ioos_qc.config.Config` by `qartod_config()`, so the `contexts → streams → <var> → qartod` shape the app already produces is correct.

So the migration's real output target is **a complete `index.md`** — YAML frontmatter plus a markdown body — per source, matching Saugus and the URI Sailing Center examples, not a bare `config.yaml`. That's the same thing GenericThings does, and it means the emitter can be validated before download rather than after review.

Which raises the one genuinely new question: **how does this app get those models?** `common/config` isn't a published package. Options are (a) vendor a minimal mirror in `qc_config.py` plus a test that diffs against upstream, (b) publish `common/config` from `NERACOOS_ERDDAP_K8S` as a small package both repos depend on, or (c) emit YAML only and let the receiving repo's CI validate. (b) is the only one that can't drift; (a) is the cheap start. Worth deciding before `qc_config.py` gets written.

### Provenance

Taking scaffold-as-default-with-provenance: the emitted config should record which suite it started from and which values a human moved. There's no field for that today — `QCConfig` is `{compliance_checker, odp, ioos, qartod, throw_failures}` and extras are ignored, so provenance needs a home. Two places, and I'd do both:

- **`attributes.global.add`** — e.g. `qartod_test_suite: gulf_of_maine`, `qartod_test_suite_source: standard_knowledge 0.1.1`, `qartod_tuned_tests: gross_range_test,spike_test`. These land in the NetCDF and surface in ERDDAP, so a *data user* can see where the thresholds came from, not just a config reviewer.
- **A `provenance` field on `QCConfig` upstream** — structured, diffable in the config PR, and the thing a reviewer actually reads.

The changed-set from the re-scaffold diff above is the same data, so this is populated for free.

### Contributing back

Since a tuned config is exactly the artifact `standard_knowledge` wants, the general page should offer a second download: a ready-to-PR `core/standards/<standard_name>.yaml` `qartod:` block built from the tuned values. Small feature, and it turns `/qc_general` from "a form for the 383 standards with no suite" into the mechanism that shrinks that number. Called out as its own sub-issue below.

---

## Keys: server-side, with per-user override

Taking the server-side-key-plus-override answer: each of `HOHONU_API_KEY`, `GREENSTREAM_API_KEY` and `THINGS_API_KEY` is read from the environment, and each source renders an "use my own key instead" `mo.ui.text(kind="password")` that takes precedence when filled. TTN needs the override regardless, since the key is per-application and the Brown/URI and NERACOOS tenants are different accounts.

Two consequences worth naming rather than discovering:

- **With a server-side key present, an anonymous visitor can pull any station in that account's inventory.** That's the deliberate trade for a usable hosted tool — but it's an argument for keeping the k8s secret scoped to a read-only key per vendor where the vendor supports it, and for rate limiting if Hohonu's quota is per-account.
- The `k8s/deployment.yaml` env block grows three secrets, so the deploy needs them before the page is useful. Ship the page ERDDAP-first so it's not blocked on that.

The Sentry interaction is the real hazard, and a server-side key makes it *worse*, not better — the key is now in the process for every request rather than only when a user pastes one:

1. **Stack-frame locals.** `include_local_variables` defaults to `True`, and `send_default_pii=False` does **not** cover it — that governs IPs, cookies, headers and bodies. Any exception inside `HohonuApi.fetch_data` ships a frame whose locals include `self`, and pydantic's default `__repr__` prints `api_key='…'` in full. `monitoring.py` has a `before_send_log` but no `before_send`.
2. **`monitoring.report(**tags)`** takes arbitrary strings from call sites — one careless `key=api_key` away.
3. **The query string** is deliberately kept (`monitoring.py:193-197`, "the real reproduction payload"). Every existing page reflexively mirrors widgets into the URL. The override field must not, with a comment at the point a future reader would add it.

So these are prerequisites, not nice-to-haves — shippable as a standalone first PR that improves the app we already have:

- A `before_send` that redacts `event["exception"][…]["stacktrace"]["frames"][…]["vars"]` and `event["tags"]` against a `key|token|secret|passw|authorization` denylist. Testable with the existing in-process `sentry_events` fixture — no network.
- `pydantic.SecretStr` on every key field, with a test asserting the key doesn't appear in `repr()`.
- **`tests/unit/conftest.py:23` filters `["authorization", "cookie", "user-agent"]` but not `x-api-key`** — which is what Greenstream uses. Fix this *before* anyone records a Greenstream cassette, or a live key lands in the repo.

One knock-on for the section below: the generated notebook must emit `getpass.getpass(...)`, never the server-side key — otherwise the download button quietly becomes a credential exfiltration endpoint.

WASM is the one option this rules out for the keyed sources, and independently so: Pyodide uses `fetch`, and Hohonu / Greenstream / TTN won't send `Access-Control-Allow-Origin` for a browser origin. ERDDAP does, so an ERDDAP-only WASM notebook stays viable.

---

## Downloading state to iterate on

The bad news first: **the built-in ipynb export is unreachable from this deployment.** `/export/html` requires the `read` scope, but `/export/ipynb`, `/export/script` and `/export/markdown` require `edit`, and `create_asgi_app` runs `SessionMode.RUN`, which grants only `["read"]`. Those routes 403. `include_code` also defaults to `False`, so the source isn't served either.

So: **`mo.download` of a generated PEP 723 marimo `.py`**, run with `uvx marimo edit --sandbox`. `GenericThings/notebooks/json_path_things.py` is already exactly this shape, right down to `getpass` for the API key. Use the lazy-callable form for both `data` and `filename`, so nothing renders until the click and the file always matches current state:

```python
mo.download(
    data=lambda: build_script(...).encode(),
    filename=lambda: f"qc_{station}_{today}.py",
    mimetype="text/x-python",
)
```

Two cheap tests: `ast.parse()` the output, and `tomllib.loads()` the PEP 723 block. Since you've said `.ipynb` isn't required — `marimo export ipynb` over this output would produce one for free if it ever is.

This would be the repo's first `mo.download`. Ship the plain `index.md` download with the first page regardless; it's the floor.

WASM stays a later, ERDDAP-only experiment. Worth noting `standard_knowledge` already publishes a `cp314-pyodide_wasm32` wheel, which doesn't look accidental — but it's pinned to one Pyodide ABI with no CI signal for skew, and `ioos_qc` drags shapely / h5netcdf / scipy / rpds-py behind it.

---

## Query params

| Round-trip | Never |
|---|---|
| `source`, `server`, `station`, `app` | API keys |
| `start`, `end`, `column` | station title / summary (free text, can run to paragraphs) |
| `standard`, `suite` | JSONPath field mappings (~20 paths × ~60 chars ≈ 1.2 kB) |
| datum floats (`mhhw`, `mllw`, …) | pasted / uploaded config documents |
| four enable toggles | |
| per-test thresholds, keyed `{suite}_{test}_{param}` | |

The suite-keyed threshold names are the `climatology.py:246` trick (`f"threshold_{period}"`) applied here, so changing suite or re-scaffolding wins over a stale number from another station — which is also what makes the overwrite behaviour above fall out naturally.

One new helper: `common.query_param_float`, a direct sibling of `query_param_int` (`common.py:162-179`) with the same clamp-and-fallback shape — ~15 lines, plus tests copied from `tests/unit/test_common.py:111-173`.

Individual named params over one base64/JSON blob: readable and hand-editable (these URLs will get pasted into issues for review), per-key validation instead of one bad field poisoning everything, greppable in Sentry, and consistent with every existing page. Worst case ≈600 characters.

**Validate the ERDDAP server URL.** A free-text URL in a query param that the server then fetches is an SSRF vector — allowlist, or at minimum require `https://` and a known host suffix. The same check covers the import-from-ERDDAP path, which takes a server and dataset ID too.

Import adds one param worth having: `import_from=<dataset_id>` for the ERDDAP read-back, so "open this station's existing config for editing" is a shareable link. Pasted and uploaded configs stay out of the URL — too big, and the pasted document is the artifact, not the link.

For the JSONPath mappings, an `mo.ui.text_area` holding YAML round-tripped by paste is the right channel — and happens to be exactly the format the GenericThings `index.md` frontmatter wants.

---

## Sizing

~1,550 Streamlit lines in. Roughly 500 is glue that evaporates, ~400 ports nearly 1:1, 158 delete outright, and ~127 survive at about half. Against that: the general-variable page, the JSONPath flow, four per-source `index.md` emitters (plus a mirror of the upstream models, if we go that way), the import paths, the notebook export, and the query-param plumbing.

**Estimate ~2,400–2,800 lines of app code plus ~1,100 of tests** — roughly doubling the repo (4,139 lines today, including tests).

Dependencies:

| Package | Channel | Notes |
|---|---|---|
| `ioos_qc` 2.3.0 | conda-forge ✅ | pulls geographiclib, geojson, h5netcdf, jsonschema, pyparsing, ruamel.yaml, **shapely** (and geos) — ~8 new lock entries |
| `bokeh` 3.9.2 | conda-forge ✅ | `python >=3.10` |
| `standard-knowledge` 0.1.1 | PyPI only | `[project].dependencies` beside `tadc`; cp313/314 wheels cover both pixi platforms. Pin exactly — it's pre-1.0 and the `qc` surface is visibly in flux |
| `python-jsonpath` 2.2.1 | conda-forge ✅ | Things sub-issue only |
| `pyyaml` 6.0.3 | conda-forge ✅ | already in the lock transitively — promote it to an explicit dep so a relock can't silently drop it |

Relocking is a separate workflow, so a dependency change is a two-step PR. Watch the `build` job's timeout as shapely/geos and bokeh land.

CI: adding routes to `PAGES` buys three parametrised tests per page for free. Add one deeper test driving the **ERDDAP** source end to end (mirroring `test_climatology.py` + `helpers.assert_chart_rendered`) and one clicking the `index.md` download via `page.expect_download()`. Deliberately **no API keys in CI** — the keyed sources get cassette-backed unit coverage and "page renders and offers the key override" in e2e, nothing more.

---

## Proposed sub-issues

Each independently shippable, in dependency order:

1. **Sentry secret hygiene** — `before_send` frame-var/tag scrubber, `x-api-key` added to `vcr_config`. Improves today's app; blocks 9. *(~0.5 d)*
2. **Dependency spike** — `ioos_qc` + `standard-knowledge` + bokeh 3.9 against pandas 3.0.3 / numpy 2.5.0 under `filterwarnings = ["error"]`. *(~0.5 d)*
3. **Decide how the app gets the `common/config` models** — vendored mirror with a drift test, or publish `common/config` as a package. Blocks 6. *(~0.5 d, mostly a decision)*
4. **`qc_core.py` + tests** — config assembly, `run_qc`, and the contexts ↔ streams-less normaliser, no marimo. *(~1 d)*
5. **Config import** — paste / upload via `Config()`, `index.md` frontmatter sniffing, ERDDAP attribute read-back including datums from `tidal_datum_offsets_meters`, and the re-scaffold changed-set diff. Verify the attributes survive on a live dataset first. *(~2 d)*
6. **`qc_config.py` + tests** — per-source `index.md` emitters (frontmatter + body) validated against `HohonuDatasetConfig` / `GreenstreamDatasetConfig` / `ThingsDatasetConfig` before download, flat `datums:`, provenance in `attributes.global.add`. *(~1.5 d)*
7. **`qc_charts.py`** — bokeh plotters ported, `circle` → `scatter`, unbranded. *(~0.5 d)*
8. **`/qc_water_level`, ERDDAP source only** — first hidden page, anonymous, full e2e, including the changed-field markers. *(~3 d)*
9. **Keyed sources** — Hohonu / Greenstream / Things clients, `SecretStr`, server-side keys + override UI, k8s secrets, cassettes. Feature parity reached; archive the Streamlit app. *(~3 d)*
10. **`common.query_param_float` + deep-link round-trip.** *(~0.5 d)*
11. **`/qc_general`** — standard picker over `filter().has_qartod_tests()`, blank-slate form for the rest. *(~2–3 d)*
12. **Contribute-back download** — emit a ready-to-PR `core/standards/<name>.yaml` `qartod:` block from tuned values. *(~1 d)*
13. **`/things_config`** — JSONPath mapping builder + GenericThings frontmatter, pydantic-validated before download. *(~3–4 d)*
14. **PEP 723 script export** — `notebook_export.py` + tests; slots in anywhere after 8. *(~1 d)*
15. **Upstream: `qc.provenance` field on `QCConfig`** in `NERACOOS_ERDDAP_K8S`. *(~0.5 d)*
16. **Upstream: expose `arguments`/`test_types` in `standard_knowledge`'s Python bindings** — see open question 1. *(~0.5 d)*
17. *(Stretch)* ERDDAP-only WASM build.

Roughly 3–4 weeks of focused work. Only 8 shouldn't be rushed — it sets every seam the rest hang off.

---

## Open questions

1. **`standard_knowledge`'s Python bindings drop the argument metadata.** `py/src/test_suite.rs:33` has `// TODO: Add arguments and test_types if needed`, so from Python you can list suites and `scaffold(**args)` them, but you can't *discover* that `gulf_of_maine` requires `mllw` and `mhhw` as required floats — the Rust `TestSuiteInfo` has it, the CLI prints it, the binding drops it. (`Standard.qc` is also a `#[getter]`, not a method.) Upstream ~30 lines of Rust to expose `arguments` and `test_types`, or hardcode the two water-level suites' args in `standards.py`? I'd argue for upstreaming: a generic argument-form builder is exactly what the "any variable" half of this issue rests on.

2. **How does this app get the `common/config` models?** Vendored mirror plus a drift test, or `common/config` published as a package both repos depend on? Only the second can't drift, but it's a bigger change to `NERACOOS_ERDDAP_K8S`. This blocks `qc_config.py`.

3. **Where does provenance live?** I've suggested both `attributes.global.add` (visible to data users through ERDDAP) and a new `qc.provenance` field on `QCConfig` (structured, diffable in the config PR). If only one, which?

4. **What's the data budget?** The Streamlit app caps at 30 days for Hohonu / Greenstream / TTN but leaves ERDDAP unbounded. Flags can't be resampled, `common.MAX_ROWS` is 10,000, and there are five charts on the page. Worth picking a cap before the first page lands, since it determines how the charts get built.

5. **Does the datum calculator belong in this loop?** `/calculate_datums` already computes MHHW/MLLW from an ERDDAP dataset via TADC, and the water-level page needs exactly those two numbers to scaffold `gulf_of_maine`. Handing them over — even just as a deep link that carries the computed datums into `/qc_water_level`'s query params — looks like a lot of value for very little code. Out of scope for this issue, but worth knowing whether you want it before the query-param names get fixed.

---
_Generated by [Claude Code](https://claude.ai/code)_
