# Climatology Py Dash

Generate climatologies for NERACOOS data on the fly, based on what is available
on the Mariner's Dashboard.

This is built with [Marimo](https://marimo.io/) which is a hybrid notebook and
app framework to allow rapid iteration and then a Streamlit-like experience.

## Commands

- `pixi run edit` - Opens Marimo notebooks in the browser for editing.
- `pixi run app` - Runs the app in the browser in a non-editable mode.

## Display units

By Buoy, By Data Type and Climatology show English units by default, with a
Metric toggle at the foot of the sidebar. The conversion table lives in
`units.py`, keyed on CF standard name and driven by the unit string Buoy Barn
reports for each reading. A standard name it does not know about is passed
through in whatever unit it arrived in. Barometric pressure is mb in both
systems.

The choice is stored in the `?units=` query-param, so a shared link keeps the
units its sender saw, and is remembered in `localStorage` between pages and
sessions (`units.head_script()`, injected into every page's `<head>` by
`app.py`). An explicit `?units=` in the URL wins over the remembered one.

## End-to-end tests

- `pixi run -e test e2e-install` - Downloads the Chromium browser for Playwright
  (one-time setup).
- `pixi run -e test e2e` - Runs the Playwright end-to-end tests, starting the
  app server automatically.

Set the `E2E_BASE_URL` environment variable (e.g.
`E2E_BASE_URL=http://localhost:8080 pixi run -e test e2e`) to point the tests at
an already-running server or container instead of spawning one.

Similarly, `E2E_SENTRY_BASE_URL` points the Sentry-specific tests
(`tests/e2e/test_sentry.py`) at an already-running, Sentry-configured server
instead of spawning one with a dummy DSN. `E2E_SENTRY_WIDGET=1` additionally
opts in to the one test that loads the real Sentry SDK from its CDN (skipped by
default, so CI stays off the network).

## Monitoring

Errors, traces, and the user-feedback widget are provided by
[Sentry](https://sentry.io) (`monitoring.py`). Backend monitoring is a no-op
unless `SENTRY_DSN` is set; the browser widget additionally needs
`SENTRY_LOADER_URL`. Local runs, the devcontainer, and CI leave both unset, so
none of them talk to Sentry or load any third-party script.

| Env var                     | Effect                                                                                                                                                                                                                                                                                                              |
| --------------------------- | ------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| `SENTRY_DSN`                | Turns backend monitoring on and gates the browser snippet (both are required for it to be injected).                                                                                                                                                                                                                |
| `SENTRY_LOADER_URL`         | The URL from Sentry's Settings -> Loader Script page, e.g. `https://js.sentry-cdn.com/<key>.min.js`. That page shows it wrapped in a `<script src="...">` tag; either the bare URL or the whole tag works here. Has its own DSN baked in server-side, so it does not have to name the same project as `SENTRY_DSN`. |
| `SENTRY_ENVIRONMENT`        | e.g. `production`, `staging`, a developer's name for local testing.                                                                                                                                                                                                                                                 |
| `SENTRY_RELEASE`            | Baked into the production image from the commit SHA (see the `build` job in `.github/workflows/push.yml` and the `Dockerfile`); set by hand for local testing.                                                                                                                                                      |
| `SENTRY_TRACES_SAMPLE_RATE` | `0.0` (off) by default; `0.2` in production.                                                                                                                                                                                                                                                                        |

Because `SENTRY_LOADER_URL`'s DSN is baked in server-side rather than read from
`SENTRY_DSN`, pointing `SENTRY_DSN` at a different (e.g. personal) project for
local testing sends backend events there, while browser events still go to
whichever project the loader is configured for -- set `SENTRY_LOADER_URL` to a
personal project's loader too if you want both sides to match.

In production, `SENTRY_DSN` and `SENTRY_LOADER_URL` are supplied by a
`climatology-sentry` Kubernetes Secret (see `k8s/deployment.yaml`), provisioned
in the [`neracoos-aws-cd`](https://github.com/gulfofmaine/neracoos-aws-cd)
repository.

To point a local run's backend at a personal Sentry project:

```
SENTRY_DSN=https://<key>@<org>.ingest.sentry.io/<project> \
SENTRY_ENVIRONMENT=local \
pixi run serve
```
