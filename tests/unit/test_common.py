"""Unit tests for the shared helpers.

The tests that reach ERDDAP or Buoy Barn are recorded with pytest-recording, see
conftest.py.
"""

import pandas as pd
import pytest

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

    assert list(platforms) == ["44007", "Western Maine Shelf"]
    assert platforms["44007"]["id"] == "44007"
    assert platforms["Western Maine Shelf"]["id"] == "44005"


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
def test_load_ts_from_erddap_raises_for_a_dataset_that_is_not_there():
    """ERDDAP answers a rejected request with a body pandas cannot parse, so
    this failure has to be caught as well as the transport ones."""
    missing = {**NDBC_SST, "dataset": "gov-ndbc-does-not-exist"}

    with pytest.raises(common.ErddapLoadError, match="gov-ndbc-does-not-exist"):
        common.load_ts_from_erddap(missing)


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
