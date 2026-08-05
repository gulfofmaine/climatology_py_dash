"""Climatology math, free of marimo, altair and network access.

Everything here is a plain function over a pandas DataFrame so that it can be
unit tested.
"""

import pandas as pd

DAILY = "Daily"
MONTHLY = "Monthly"

# Minimum observations for a period to be eligible for the climatology.
# 18 daily assumes 3/4 of hourly observations; 20 monthly assumes 2/3 of days.
DAILY_THRESHOLD = 18
MONTHLY_THRESHOLD = 20

# Name of the timestamp column once the ERDDAP time index has been reset.
TIME_COLUMN = "Date"

# Name it takes when the climatology is of monthly rather than daily averages.
MONTH_COLUMN = "Month"

# Internal name for the group key a period average is collected under.
_PERIOD = "_period"

# The one calendar day that has nowhere to land in three years out of four.
_LEAP_DAY = "02-29"


def threshold_default(period: str) -> int:
    """Default minimum observation count for an averaging period."""
    return DAILY_THRESHOLD if period == DAILY else MONTHLY_THRESHOLD


def time_column(period: str) -> str:
    """Name of the column a climatology of this averaging period is indexed by."""
    return TIME_COLUMN if period == DAILY else MONTH_COLUMN


def available_years(df: pd.DataFrame) -> list[str]:
    """Every year with an observation, oldest first.

    Sorted explicitly: callers treat the last entry as the most recent year, and
    ERDDAP is not obliged to hand back rows in time order.
    """
    return sorted({str(year) for year in df[TIME_COLUMN].dt.year.unique()})


def end_year_options(years: list[str], start_year: str | int) -> list[str]:
    """Years eligible as a climatology end year, given the start year.

    Inclusive of ``start_year``, so that a single-year climatology is
    expressible. Excluding it left the list empty whenever the newest year was
    chosen as the start, and every default below then raised ``IndexError``.
    """
    return [year for year in years if int(year) >= int(start_year)]


def default_end_year(options: list[str]) -> str:
    """Second-newest eligible year, so the latest (partial) year is excluded."""
    if not options:
        msg = "No end years available for the selected start year"
        raise ValueError(msg)
    return options[-2] if len(options) > 1 else options[-1]


def _period_keys(times, period: str):
    """The group key each observation time falls under.

    Accepts a Series or a DatetimeIndex, since observations arrive as a column
    and period averages as an index.

    Daily keys are the calendar month and day rather than the day of the year:
    day 60 is Feb 29 in a leap year and Mar 1 in every other one, so keying on
    day of year averaged Mar 1 together with Feb 29, Mar 2 with Mar 1, and so
    on through to the end of December.
    """
    accessor = times.dt if isinstance(times, pd.Series) else times
    return accessor.strftime("%m-%d") if period == DAILY else accessor.month


def _period_dates(periods: pd.Series, period: str, display_year: int) -> pd.Series:
    """Map group keys back onto timestamps within the year being displayed."""
    if period == DAILY:
        # Feb 29 has nowhere to land in a non-leap display year; coerced to NaT
        # here and dropped by _with_period_dates.
        return pd.to_datetime(
            f"{display_year}-" + periods.astype(str),
            format="%Y-%m-%d",
            errors="coerce",
        )

    months = periods.astype(int).astype(str).str.zfill(2)
    return pd.to_datetime(f"{display_year}-" + months + "-01", format="%Y-%m-%d")


def _with_period_dates(
    frame: pd.DataFrame,
    period: str,
    display_year: int,
) -> pd.DataFrame:
    """Add the display-year time column, dropping a leap day it cannot hold.

    Anything other than Feb 29 failing to map is a bug rather than a calendar
    quirk, so it raises instead of being quietly dropped.
    """
    column = time_column(period)
    frame[column] = _period_dates(frame[_PERIOD], period, display_year)

    unplaced = frame[column].isna()
    if unplaced.any():
        unexpected = frame.loc[unplaced, _PERIOD].ne(_LEAP_DAY)
        if unexpected.any():
            keys = frame.loc[unplaced, _PERIOD][unexpected].tolist()
            msg = f"Could not place period keys {keys} in {display_year}"
            raise ValueError(msg)
        frame = frame[~unplaced]

    return frame.reset_index(drop=True)


def period_means(df: pd.DataFrame, column: str, period: str) -> pd.DataFrame:
    """Average ``column`` over each day or month, with the observation count."""
    times = df[TIME_COLUMN]
    if period == DAILY:
        keys = times.dt.normalize()
    else:
        # Midnight on the first of the month. Going via to_period() would drop
        # the timezone, leaving the monthly index naive and the daily one aware.
        keys = times.dt.normalize() - pd.to_timedelta(times.dt.day - 1, unit="D")

    means = df[column].groupby(keys).agg(["mean", "count"])
    means.index = pd.DatetimeIndex(means.index, name=TIME_COLUMN)
    return means.sort_index()


def filter_means(
    means: pd.DataFrame,
    *,
    threshold: int,
    start_year: str | int,
    end_year: str | int,
) -> pd.DataFrame:
    """Keep periods with enough observations, within the climatology year range.

    The bounds take their timezone from the index: ERDDAP hands back UTC-aware
    times, and comparing those against a naive Timestamp is a TypeError.
    """
    tz = means.index.tz
    start = pd.Timestamp(year=int(start_year), month=1, day=1, tz=tz)
    end = pd.Timestamp(year=int(end_year) + 1, month=1, day=1, tz=tz)

    return means[
        (means["count"] > threshold) & (means.index >= start) & (means.index < end)
    ]


def climatology(
    means_filtered: pd.DataFrame,
    period: str,
    display_year: str | int,
) -> pd.DataFrame:
    """Collapse period means from many years into one climatological year.

    Returns canonical column names -- the time column plus ``mean``, ``max``,
    ``min``, ``min_date`` and ``max_date`` -- leaving the caller to relabel them
    for display.

    A Feb 29 climatology is computed from the leap years in range but only
    plotted when the display year can hold it.
    """
    display_year = int(display_year)
    keys = _period_keys(means_filtered.index, period).rename(_PERIOD)

    clim = (
        means_filtered.groupby(keys)["mean"]
        .agg(["mean", "max", "min", "idxmin", "idxmax"])
        .reset_index()
    )

    clim = _with_period_dates(clim, period, display_year)

    for name, source in (("min_date", "idxmin"), ("max_date", "idxmax")):
        clim[name] = pd.to_datetime(clim[source]).dt.date

    column = time_column(period)
    ordered = [column, "mean", "max", "min", "min_date", "max_date"]
    return clim[ordered]


def _every_period_of(period: str, display_year: int) -> pd.DatetimeIndex:
    """Every day or month of the year, so a series can be laid over all of it."""
    if period == DAILY:
        return pd.date_range(f"{display_year}-01-01", f"{display_year}-12-31", freq="D")
    return pd.date_range(f"{display_year}-01-01", periods=12, freq="MS")


def year_series(
    df: pd.DataFrame,
    column: str,
    period: str,
    display_year: str | int,
) -> pd.DataFrame:
    """Daily or monthly means of ``column`` for a single year, gaps included.

    Selected with ``.dt.year`` rather than string bounds: the comparison this
    replaces was exclusive at both ends, so an observation landing exactly on
    midnight, Jan 1 was dropped.

    Laid over every period of the year, so periods without observations are
    present as NaN rather than missing. That is what lets the plotted line break
    at a data gap instead of drawing straight through it.
    """
    display_year = int(display_year)
    in_year = df[df[TIME_COLUMN].dt.year == display_year]

    keys = _period_keys(in_year[TIME_COLUMN], period).rename(_PERIOD)
    means = in_year[column].groupby(keys).mean().rename("mean").reset_index()

    means = _with_period_dates(means, period, display_year)

    column_name = time_column(period)
    return (
        means.set_index(column_name)["mean"]
        .reindex(_every_period_of(period, display_year))
        .rename_axis(column_name)
        .reset_index()
    )
