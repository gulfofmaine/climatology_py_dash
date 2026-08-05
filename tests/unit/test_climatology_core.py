"""Unit tests for the pure climatology math.

Every case here is one a marimo cell could not be tested for: the computation
used to live inside the notebook, so the only coverage it had was whichever path
the Playwright suite happened to click through.
"""

import datetime

import pandas as pd
import pytest

import climatology_core as core

COLUMN = "sea_water_temperature (degree_C)"


def observations(
    start: str,
    periods: int,
    *,
    freq: str = "1D",
    tz: str | None = "UTC",
) -> pd.DataFrame:
    """Observations whose value encodes their calendar month and day, as MMDD.

    That makes a climatology assertion meaningful: if the average for a given
    calendar day is not exactly MMDD, values from other calendar days were
    folded into it.

    UTC-aware by default, because that is what ERDDAP hands back.
    """
    times = pd.date_range(start, periods=periods, freq=freq, tz=tz)
    return pd.DataFrame(
        {
            core.TIME_COLUMN: times,
            COLUMN: (times.month * 100 + times.day).astype(float),
        },
    )


def two_non_leap_years(tz: str | None = "UTC") -> pd.DataFrame:
    """2021 and 2022 -- neither is a leap year, so calendar days line up."""
    return pd.concat(
        [
            observations("2021-01-01", 365, tz=tz),
            observations("2022-01-01", 365, tz=tz),
        ],
        ignore_index=True,
    )


def test_available_years_are_sorted_oldest_first():
    df = pd.concat(
        [observations("2022-06-01", 3), observations("2019-06-01", 3)],
        ignore_index=True,
    )

    assert core.available_years(df) == ["2019", "2022"]


def test_threshold_defaults_differ_by_period():
    assert core.threshold_default(core.DAILY) == core.DAILY_THRESHOLD
    assert core.threshold_default(core.MONTHLY) == core.MONTHLY_THRESHOLD


def test_end_year_options_include_the_start_year():
    assert core.end_year_options(["2019", "2020", "2021"], "2020") == ["2020", "2021"]


def test_end_year_options_are_non_empty_for_the_newest_start_year():
    """Choosing the newest year as the start used to raise IndexError."""
    years = ["2019", "2020", "2021"]

    options = core.end_year_options(years, "2021")

    assert options == ["2021"]
    assert core.default_end_year(options) == "2021"


def test_default_end_year_skips_the_latest_partial_year():
    assert core.default_end_year(["2019", "2020", "2021"]) == "2020"


def test_default_end_year_rejects_an_empty_range():
    with pytest.raises(ValueError, match="No end years"):
        core.default_end_year([])


def test_period_means_counts_observations_per_day():
    df = observations("2024-01-01", 48, freq="1h")

    means = core.period_means(df, COLUMN, core.DAILY)

    assert means.index.name == core.TIME_COLUMN
    assert list(means.index) == [
        pd.Timestamp("2024-01-01", tz="UTC"),
        pd.Timestamp("2024-01-02", tz="UTC"),
    ]
    assert means["count"].tolist() == [24, 24]
    assert means["mean"].tolist() == [101.0, 102.0]


@pytest.mark.parametrize("tz", ["UTC", None])
def test_filter_means_handles_aware_and_naive_indexes(tz):
    """ERDDAP indexes are UTC-aware; comparing them against a naive Timestamp
    raises TypeError, which the string bounds this replaced hid."""
    means = core.period_means(two_non_leap_years(tz=tz), COLUMN, core.DAILY)

    kept = core.filter_means(means, threshold=0, start_year=2022, end_year=2022)

    assert len(kept) == 365
    assert set(kept.index.year.unique()) == {2022}


def test_period_means_collects_months_onto_the_first_of_the_month():
    df = observations("2024-01-01", 60)

    means = core.period_means(df, COLUMN, core.MONTHLY)

    assert list(means.index) == [
        pd.Timestamp("2024-01-01", tz="UTC"),
        pd.Timestamp("2024-02-01", tz="UTC"),
    ]
    assert means["count"].tolist() == [31, 29]
    assert means.index.tz is not None, "the monthly index must stay timezone aware"


def test_filter_means_threshold_is_exclusive():
    df = observations("2024-01-01", 48, freq="1h")
    means = core.period_means(df, COLUMN, core.DAILY)

    kept = core.filter_means(means, threshold=23, start_year=2024, end_year=2024)
    dropped = core.filter_means(means, threshold=24, start_year=2024, end_year=2024)

    assert len(kept) == 2
    assert dropped.empty


def test_filter_means_year_range_includes_all_of_the_end_year():
    means = core.period_means(two_non_leap_years(), COLUMN, core.DAILY)

    kept = core.filter_means(means, threshold=0, start_year=2021, end_year=2022)

    assert kept.index.min() == pd.Timestamp("2021-01-01", tz="UTC")
    assert kept.index.max() == pd.Timestamp("2022-12-31", tz="UTC")


def test_filter_means_year_range_excludes_years_outside_it():
    means = core.period_means(two_non_leap_years(), COLUMN, core.DAILY)

    kept = core.filter_means(means, threshold=0, start_year=2022, end_year=2022)

    assert set(kept.index.year.unique()) == {2022}


def test_climatology_averages_the_same_calendar_day_across_years():
    means = core.period_means(two_non_leap_years(), COLUMN, core.DAILY)
    filtered = core.filter_means(means, threshold=0, start_year=2021, end_year=2022)

    clim = core.climatology(filtered, core.DAILY, display_year=2023)

    assert len(clim) == 365
    march_first = clim[clim[core.TIME_COLUMN] == pd.Timestamp("2023-03-01")]
    assert march_first["mean"].item() == 301.0
    assert march_first["min"].item() == 301.0
    assert march_first["max"].item() == 301.0
    assert march_first["min_date"].item() == datetime.date(2021, 3, 1)


def test_climatology_reports_the_year_that_set_each_extreme():
    warm = observations("2021-01-01", 2)
    cold = observations("2022-01-01", 2)
    cold[COLUMN] = cold[COLUMN] - 10
    means = core.period_means(
        pd.concat([warm, cold], ignore_index=True),
        COLUMN,
        core.DAILY,
    )
    filtered = core.filter_means(means, threshold=0, start_year=2021, end_year=2022)

    clim = core.climatology(filtered, core.DAILY, display_year=2023)

    first = clim.iloc[0]
    assert first["max_date"] == datetime.date(2021, 1, 1)
    assert first["min_date"] == datetime.date(2022, 1, 1)


def test_climatology_monthly_is_indexed_by_month():
    means = core.period_means(two_non_leap_years(), COLUMN, core.MONTHLY)
    filtered = core.filter_means(means, threshold=0, start_year=2021, end_year=2022)

    clim = core.climatology(filtered, core.MONTHLY, display_year=2023)

    assert core.MONTH_COLUMN in clim.columns
    assert len(clim) == 12
    assert clim[core.MONTH_COLUMN].min() == pd.Timestamp("2023-01-01")
    assert clim[core.MONTH_COLUMN].max() == pd.Timestamp("2023-12-01")


def test_year_series_includes_an_observation_at_midnight_january_first():
    """The string bounds this replaces were exclusive at both ends."""
    df = observations("2023-12-31", 3)

    series = core.year_series(df, COLUMN, core.DAILY, 2024)

    assert series[core.TIME_COLUMN].min() == pd.Timestamp("2024-01-01")
    assert len(series) == 2


def test_year_series_only_covers_the_requested_year():
    df = two_non_leap_years()

    series = core.year_series(df, COLUMN, core.DAILY, 2022)

    assert len(series) == 365
    assert series[core.TIME_COLUMN].dt.year.unique().tolist() == [2022]


@pytest.mark.parametrize("period", [core.DAILY, core.MONTHLY])
def test_climatology_and_year_series_align_for_the_data_table(period):
    """The data table merges the two frames, so their time columns must match."""
    df = two_non_leap_years()
    means = core.period_means(df, COLUMN, period)
    filtered = core.filter_means(means, threshold=0, start_year=2021, end_year=2022)

    clim = core.climatology(filtered, period, display_year=2022)
    series = core.year_series(df, COLUMN, period, 2022)

    merged = clim.merge(series, on=core.time_column(period), how="left")

    assert len(merged) == len(clim)
    assert merged["mean_y"].notna().all()
