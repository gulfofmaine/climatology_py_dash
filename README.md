# Climatology Py Dash

Generate climatologies for NERACOOS data on the fly, based on what is available
on the Mariner's Dashboard.

This is built with [Marimo](https://marimo.io/) which is a hybrid notebook and
app framework to allow rapid iteration and then a Streamlit-like experience.

## Commands

- `pixi run edit` - Opens Marimo notebooks in the browser for editing.
- `pixi run app` - Runs the app in the browser in a non-editable mode.

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
opts in to the one test that loads the real Sentry SDK from its CDN (skipped
by default, so CI stays off the network).

## Monitoring

Errors, traces, and the user-feedback widget are provided by
[Sentry](https://sentry.io) (`monitoring.py`). Everything is a no-op unless
`SENTRY_DSN` is set -- local runs, the devcontainer, and CI all leave it unset,
so none of them talk to Sentry or load any third-party script.

| Env var | Effect |
| --- | --- |
| `SENTRY_DSN` | Turns monitoring on. Also read by the browser widget -- a DSN is public by design, so this is the same value on both sides. |
| `SENTRY_ENVIRONMENT` | e.g. `production`, `staging`, a developer's name for local testing. |
| `SENTRY_RELEASE` | Baked into the production image from the commit SHA (see the `build` job in `.github/workflows/push.yml` and the `Dockerfile`); set by hand for local testing. |
| `SENTRY_TRACES_SAMPLE_RATE` | `0.0` (off) by default; `0.2` in production. |

In production, `SENTRY_DSN` is supplied by a `climatology-sentry` Kubernetes
Secret (see `k8s/deployment.yaml`), provisioned in the
[`neracoos-aws-cd`](https://github.com/gulfofmaine/neracoos-aws-cd) repository.

To point a local run at a personal Sentry project:

```
SENTRY_DSN=https://<key>@<org>.ingest.sentry.io/<project> \
SENTRY_ENVIRONMENT=local \
pixi run serve
```
