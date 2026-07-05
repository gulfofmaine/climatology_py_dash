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
