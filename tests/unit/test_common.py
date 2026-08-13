"""Unit tests for the shared helpers.

The tests that reach ERDDAP or Buoy Barn are recorded with pytest-recording, see
conftest.py.
"""

import altair as alt
import pandas as pd
import pytest
import sentry_sdk

import common

TIME_INDEX = "time (UTC)"

# A real climatology timeseries, as Buoy Barn describes it, narrowed to a couple
# of days so the recorded response stays small.
NDBC_SST = {
    "depth": None,
    "data_type": {
        "long_name": "Sea Surface Temperature",
        "standard_name": "sea_surface_temperature",
        "units": "degree_C",
    },
    "server": "http://erddap.sensors.ioos.us/erddap",
    "dataset": "gov-ndbc-44027",
    "variable": "sea_surface_temperature",
    "constraints": {"time>=": "2024-07-01T00:00:00Z", "time<=": "2024-07-03T00:00:00Z"},
}


def reading(long_name: str, depth=None) -> dict:
    """A Buoy Barn reading, trimmed to the keys the app touches."""
    return {
        "depth": depth,
        "data_type": {
            "long_name": long_name,
            "standard_name": "air_temperature",
            "units": "degree_C",
        },
        "server": "https://data.neracoos.org/erddap",
        "dataset": "A01_met_all",
        "variable": "air_temperature",
        "constraints": None,
    }


def erddap_frame(periods: int, *, freq: str = "1h") -> pd.DataFrame:
    """A frame shaped like erddapy's, indexed by the ERDDAP time column."""
    index = pd.DatetimeIndex(
        pd.date_range("2024-01-01", periods=periods, freq=freq),
        name=TIME_INDEX,
    )
    return pd.DataFrame({"value (degree_C)": 1.0}, index=index)


class FakeQueryParams:
    """Stands in for ``mo.query_params()``, which needs a running kernel."""

    def __init__(self, **params):
        self._params = params

    def get(self, key, default=None):
        return self._params.get(key, default)


def test_name_for_ts_includes_the_depth_when_there_is_one():
    assert common.name_for_ts(reading("Water Temperature", depth=1.0)) == (
        "Water Temperature @ 1.0m"
    )


def test_name_for_ts_omits_the_depth_when_there_is_none():
    assert common.name_for_ts(reading("Air Temperature")) == "Air Temperature"


def test_platforms_by_name_prefers_the_station_name_and_sorts():
    platform_json = {
        "features": [
            {"id": "44005", "properties": {"station_name": "Western Maine Shelf"}},
            {"id": "44007", "properties": {"station_name": None}},
        ],
    }

    platforms = common.platforms_by_name(platform_json)

    assert list(platforms) == ["44005 - Western Maine Shelf", "44007"]
    assert platforms["44007"]["id"] == "44007"
    assert platforms["44005 - Western Maine Shelf"]["id"] == "44005"


def test_platform_display_name_concatenates_id_and_station_name():
    feature = {"id": "A01", "properties": {"station_name": "Mass Bay"}}
    assert common.platform_display_name(feature) == "A01 - Mass Bay"


def test_platforms_with_readings_keeps_a_platform_that_has_readings():
    platforms = {
        "44005 - Western Maine Shelf": {
            "id": "44005",
            "properties": {"readings": [reading("Air Temperature")]},
        },
    }

    result = common.platforms_with_readings(platforms)

    assert list(result) == ["44005 - Western Maine Shelf"]


def test_platforms_with_readings_drops_a_platform_with_no_readings():
    platforms = {
        "44007": {"id": "44007", "properties": {"readings": []}},
    }

    result = common.platforms_with_readings(platforms)

    assert result == {}


def test_platforms_with_readings_preserves_order_of_survivors():
    platforms = {
        "44005 - Western Maine Shelf": {
            "id": "44005",
            "properties": {"readings": [reading("Air Temperature")]},
        },
        "44007": {"id": "44007", "properties": {"readings": []}},
        "A01 - Mass Bay": {
            "id": "A01",
            "properties": {"readings": [reading("Water Temperature", depth=1.0)]},
        },
    }

    result = common.platforms_with_readings(platforms)

    assert list(result) == ["44005 - Western Maine Shelf", "A01 - Mass Bay"]


def test_platform_display_name_falls_back_to_id_only():
    feature = {"id": "44007", "properties": {"station_name": None}}
    assert common.platform_display_name(feature) == "44007"


def test_timeseries_by_name_sorts_and_records_the_app_name():
    platform = {
        "properties": {
            "readings": [
                reading("Water Temperature", depth=1.0),
                reading("Air Temperature"),
            ],
        },
    }

    timeseries = common.timeseries_by_name(platform)

    assert list(timeseries) == ["Air Temperature", "Water Temperature @ 1.0m"]
    assert timeseries["Air Temperature"]["app_name"] == "Air Temperature"


def test_timeseries_by_name_of_no_platform_is_empty():
    assert common.timeseries_by_name(None) == {}


def test_query_param_default_accepts_a_value_that_is_an_option():
    params = FakeQueryParams(platform="A01")

    assert common.query_param_default(params, "platform", ["A01", "B01"]) == "A01"


def test_query_param_default_rejects_a_value_left_over_from_another_platform():
    params = FakeQueryParams(ts="Water Temperature @ 50.0m")

    assert (
        common.query_param_default(params, "ts", ["Air Temperature"], fallback="fell")
        == "fell"
    )


def test_query_param_default_falls_back_when_unset():
    assert common.query_param_default(FakeQueryParams(), "year", ["2024"]) is None


def test_query_param_list_default_accepts_comma_separated_values_that_are_options():
    params = FakeQueryParams(ts="Air Temperature,Water Temperature")

    assert common.query_param_list_default(
        params,
        "ts",
        ["Air Temperature", "Water Temperature", "Wind Speed"],
        fallback=[],
    ) == ["Air Temperature", "Water Temperature"]


def test_query_param_list_default_drops_entries_left_over_from_another_platform():
    params = FakeQueryParams(ts="Air Temperature,Water Temperature @ 50.0m")

    assert common.query_param_list_default(
        params,
        "ts",
        ["Air Temperature"],
        fallback=[],
    ) == ["Air Temperature"]


def test_query_param_list_default_falls_back_when_unset():
    assert common.query_param_list_default(
        FakeQueryParams(),
        "ts",
        ["Air Temperature"],
        fallback=["fell"],
    ) == ["fell"]


def test_query_param_list_default_falls_back_when_empty_string():
    params = FakeQueryParams(ts="")

    assert common.query_param_list_default(
        params,
        "ts",
        ["Air Temperature"],
        fallback=["fell"],
    ) == ["fell"]


def test_query_param_list_default_falls_back_when_every_entry_is_invalid():
    params = FakeQueryParams(ts="Water Temperature @ 50.0m")

    assert common.query_param_list_default(
        params,
        "ts",
        ["Air Temperature"],
        fallback=["fell"],
    ) == ["fell"]


def test_query_param_int_accepts_a_valid_stored_value():
    params = FakeQueryParams(threshold_daily="5")

    assert common.query_param_int(params, "threshold_daily", fallback=18) == 5


def test_query_param_int_falls_back_when_missing():
    assert (
        common.query_param_int(FakeQueryParams(), "threshold_daily", fallback=18) == 18
    )


def test_query_param_int_falls_back_when_not_numeric():
    params = FakeQueryParams(threshold_daily="not-a-number")

    assert common.query_param_int(params, "threshold_daily", fallback=18) == 18


def test_query_param_int_clamps_a_stored_value_above_maximum():
    params = FakeQueryParams(threshold_daily="100")

    assert (
        common.query_param_int(params, "threshold_daily", fallback=18, maximum=20) == 20
    )


def test_query_param_int_clamps_a_stored_value_below_minimum():
    params = FakeQueryParams(threshold_daily="-5")

    assert (
        common.query_param_int(params, "threshold_daily", fallback=18, minimum=0) == 0
    )


def test_query_param_int_clamps_a_fallback_above_maximum():
    assert (
        common.query_param_int(
            FakeQueryParams(),
            "threshold_daily",
            fallback=18,
            maximum=10,
        )
        == 10
    )


def test_resample_to_budget_passes_small_frames_through_untouched():
    df = erddap_frame(10)

    resampled, label = common.resample_to_budget(df, max_rows=100)

    assert label is None
    assert resampled is df
    assert isinstance(resampled.index, pd.DatetimeIndex)


def test_resample_to_budget_resamples_a_wide_frame_until_it_fits():
    df = erddap_frame(24 * 40)

    resampled, label = common.resample_to_budget(df, max_rows=100)

    assert label == "daily"
    assert len(resampled) == 40
    assert isinstance(resampled.index, pd.DatetimeIndex)


def test_resample_to_budget_falls_through_to_the_coarsest_period():
    df = erddap_frame(24 * 400)

    resampled, label = common.resample_to_budget(df, max_rows=20)

    assert label == "monthly"
    assert len(resampled) < len(df)


def test_resample_to_budget_keeps_a_flat_index_for_a_long_frame():
    """The caller reads ``.index.max()``, which broke on whichever of the two
    paths the hand-rolled version it replaces was not written for."""
    long_df = erddap_frame(24 * 40).assign(Timeseries="A01")

    resampled, label = common.resample_to_budget(long_df, max_rows=100, by="Timeseries")

    assert label == "daily"
    assert isinstance(resampled.index, pd.DatetimeIndex)
    assert resampled.index.name == TIME_INDEX
    assert resampled.index.max() == pd.Timestamp("2024-02-09")


def test_resample_to_budget_averages_each_series_separately():
    times = pd.DatetimeIndex(
        pd.date_range("2024-01-01", periods=48, freq="1h"),
        name=TIME_INDEX,
    )
    long_df = pd.concat(
        [
            pd.DataFrame({"Timeseries": "A01", "value": 1.0}, index=times),
            pd.DataFrame({"Timeseries": "B01", "value": 3.0}, index=times),
        ],
    )

    resampled, _ = common.resample_to_budget(long_df, max_rows=10, by="Timeseries")

    by_series = resampled.groupby("Timeseries")["value"].mean()
    assert by_series["A01"] == 1.0
    assert by_series["B01"] == 3.0


def test_erddap_client_sets_a_timeout():
    client = common.erddap_client(reading("Air Temperature"))

    assert client.requests_kwargs["timeout"] == common.ERDDAP_TIMEOUT


def test_erddap_download_url_carries_the_dataset_and_variable():
    url = common.erddap_download_url(NDBC_SST)

    assert "gov-ndbc-44027" in url
    assert "sea_surface_temperature" in url


def test_logo_data_uri_is_an_encoded_png():
    assert common._logo_data_uri().startswith("data:image/png;base64,iVBOR")


@pytest.mark.vcr
def test_load_ts_from_erddap_returns_the_requested_timeseries():
    df = common.load_ts_from_erddap(NDBC_SST)

    assert df.index.name == TIME_INDEX
    assert isinstance(df.index, pd.DatetimeIndex)
    assert not df.empty
    assert not df.iloc[:, 0].isna().any()


@pytest.mark.vcr
def test_load_ts_from_erddap_raises_for_a_dataset_that_is_not_there(sentry_events):
    """ERDDAP answers a rejected request with a body pandas cannot parse, so
    this failure has to be caught as well as the transport ones."""
    missing = {**NDBC_SST, "dataset": "gov-ndbc-does-not-exist"}

    with pytest.raises(
        common.ErddapLoadError,
        match="gov-ndbc-does-not-exist",
    ) as excinfo:
        common.load_ts_from_erddap(missing)

    # Every caller of load_ts_from_erddap handles ErddapLoadError, so it is
    # reported here, before the wrap, or it would never reach Sentry at all.
    sentry_sdk.flush()
    assert len(sentry_events) == 1
    event = sentry_events[0]
    assert event["level"] == "warning"
    assert event["fingerprint"] == ["erddap-load", NDBC_SST["server"]]
    assert event["tags"]["dataset"] == "gov-ndbc-does-not-exist"

    # Carried on the exception so a caller can offer it back to
    # common.admonition(sentry_event_id=...) and let a feedback submission be
    # linked to this exact event.
    assert excinfo.value.sentry_event_id == event["event_id"]

    # And the reported event's trace matches the load's own span, rather than
    # a fresh, disconnected one -- see monitoring.report()'s docstring for why
    # that depends on reporting from inside the span, not after it has closed.
    assert event["contexts"]["trace"]["op"] == "http.client"
    assert "gov-ndbc-does-not-exist" in event["transaction"]


@pytest.mark.vcr
def test_load_ts_names_the_value_column():
    df = common.load_ts(NDBC_SST, "Sea Surface Temperature")

    assert df.columns[0] == "Sea Surface Temperature"


@pytest.mark.vcr
def test_load_ts_hands_back_a_fresh_frame_each_call():
    """Mutating the cached frame used to poison every later read of it."""
    first = common.load_ts(NDBC_SST, "Sea Surface Temperature")
    del first["Sea Surface Temperature"]

    second = common.load_ts(NDBC_SST, "Sea Surface Temperature")

    assert "Sea Surface Temperature" in second.columns


def test_admonition_offers_no_report_link_without_a_dsn(monkeypatch):
    monkeypatch.delenv("SENTRY_DSN", raising=False)

    rendered = common.admonition("oops", kind="error").text

    assert "data-sentry-report" not in rendered


def test_admonition_offers_a_report_link_for_errors_with_a_dsn(monkeypatch):
    monkeypatch.setenv("SENTRY_DSN", "https://public@example.invalid/1")
    monkeypatch.setenv(
        "SENTRY_LOADER_URL",
        "https://js.sentry-cdn.com/testtesttesttesttesttesttest0000.min.js",
    )

    rendered = common.admonition("oops", kind="error").text

    assert "data-sentry-report" in rendered


def test_admonition_offers_no_report_link_with_a_dsn_but_no_loader_url(monkeypatch):
    """Both are required -- see monitoring.enabled()."""
    monkeypatch.setenv("SENTRY_DSN", "https://public@example.invalid/1")
    monkeypatch.delenv("SENTRY_LOADER_URL", raising=False)

    rendered = common.admonition("oops", kind="error").text

    assert "data-sentry-report" not in rendered


def test_admonition_with_a_report_link_still_parses_as_a_directive(monkeypatch):
    """Regression test: the report link used to be appended on its own line,
    which starts at column 0 while every other line sits at this function's
    source indentation. mo.md() dedents via inspect.cleandoc(), which strips
    the *smallest* common leading whitespace across all lines -- one line at
    column 0 drops that common amount to zero, so the ///-fenced lines keep
    their original indentation and fail to parse as a directive at all,
    rendering literally instead of as a styled admonition box."""
    monkeypatch.setenv("SENTRY_DSN", "https://public@example.invalid/1")
    monkeypatch.setenv(
        "SENTRY_LOADER_URL",
        "https://js.sentry-cdn.com/testtesttesttesttesttesttest0000.min.js",
    )

    rendered = common.admonition("oops", title="Oops", kind="error").text

    assert '<div class="admonition error">' in rendered
    assert "///" not in rendered


def test_admonition_never_offers_a_report_link_for_non_errors(monkeypatch):
    monkeypatch.setenv("SENTRY_DSN", "https://public@example.invalid/1")

    rendered = common.admonition("", kind="attention").text

    assert "data-sentry-report" not in rendered


def test_admonition_report_can_be_forced_on_and_off(monkeypatch):
    monkeypatch.delenv("SENTRY_DSN", raising=False)

    assert (
        "data-sentry-report" in common.admonition("x", kind="error", report=True).text
    )
    assert (
        "data-sentry-report"
        not in common.admonition("x", kind="attention", report=False).text
    )


def test_admonition_embeds_a_valid_sentry_event_id():
    """A real Sentry event id is 32 lowercase hex characters."""
    rendered = common.admonition(
        "x",
        kind="error",
        report=True,
        sentry_event_id="4a99b1f0c54b4b248939e08c6485e90d",
    ).text

    assert 'data-sentry-event-id="4a99b1f0c54b4b248939e08c6485e90d"' in rendered


def hover_frame() -> pd.DataFrame:
    """A frame shaped like the melted/reset frames the two chart pages hover over."""
    return pd.DataFrame(
        {
            TIME_INDEX: pd.date_range("2024-01-01", periods=5, freq="D"),
            "value": [1, 2, 3, 4, 5],
        },
    )


def test_linked_hover_returns_a_layer_chart():
    df = hover_frame()
    line = alt.Chart(df).mark_line().encode(x=f"{TIME_INDEX}:T", y="value:Q")

    layer, hover = common.linked_hover(
        line,
        df,
        TIME_INDEX,
        [("value", "Value")],
    )

    assert isinstance(layer, alt.LayerChart)
    assert isinstance(hover, alt.Parameter)


def test_linked_hover_formats_missing_values_as_no_data():
    """A NaN reading shows as "No data" in the tooltip, not a raw NaN.

    A hover can land on a timestamp where one series in a group has no
    reading (e.g. a sensor outage) while others do -- see by_platform.py's
    per-row hit frame, which can have NaN in any of its series columns.
    """
    df = hover_frame()
    line = alt.Chart(df).mark_line().encode(x=f"{TIME_INDEX}:T", y="value:Q")

    layer, _hover = common.linked_hover(line, df, TIME_INDEX, [("value", "Value")])

    calculates = [
        step["calculate"]
        for entry in layer.to_dict()["layer"]
        for step in entry.get("transform", [])
        if "calculate" in step
    ]
    assert len(calculates) == 1
    assert "isValid" in calculates[0]
    assert "No data" in calculates[0]


def test_linked_hover_reused_across_rows_yields_one_shared_param():
    """Threading the same ``hover`` param through two rows shares one Vega param.

    by_platform.py builds one vconcat row per unit and threads the same
    selection through ``common.linked_hover()`` for each -- Vega-Lite should
    resolve that into exactly one top-level param, not one copy per row. If a
    future change built a fresh selection per row instead, this would start
    failing with more than one entry in ``params``.
    """
    df = hover_frame()
    line = alt.Chart(df).mark_line().encode(x=f"{TIME_INDEX}:T", y="value:Q")
    value_fields = [("value", "Value")]

    row0, hover = common.linked_hover(line, df, TIME_INDEX, value_fields)
    row1, hover = common.linked_hover(line, df, TIME_INDEX, value_fields, hover=hover)

    # Reusing the same hover param across rows is the whole point (see
    # linked_hover()'s docstring) -- Altair's dedup warning fires here, when
    # the rows are composed together, and is expected rather than a sign
    # something's wrong.
    with pytest.warns(UserWarning, match="Automatically deduplicated"):
        spec = alt.vconcat(row0, row1).to_dict()

    assert len(spec["params"]) == 1
    assert "params" not in spec["vconcat"][0]
    assert "params" not in spec["vconcat"][1]


@pytest.mark.parametrize(
    "value",
    [
        None,
        "",
        "not-a-real-event-id",
        '4a99b1f0c54b4b248939e08c6485e90d"><script>alert(1)</script>',
    ],
)
def test_admonition_omits_a_missing_or_malformed_sentry_event_id(value):
    rendered = common.admonition(
        "x",
        kind="error",
        report=True,
        sentry_event_id=value,
    ).text

    assert "data-sentry-event-id" not in rendered
