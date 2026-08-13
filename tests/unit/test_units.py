"""Unit tests for display unit conversion."""

import numpy as np
import pandas as pd
import pytest

import units


def rounded(values: pd.Series) -> list[float]:
    """Values rounded to 2dp for comparison against the verified numbers."""
    return np.round(values.to_numpy(), 2).tolist()


# Real (standard_name, source) pairs Buoy Barn returns today, with the
# verified English and Metric results (rounded to 2dp). Visibility is the one
# family where Metric is not a no-op: the source is metres but the Metric
# target is km.
BUOY_BARN_CASES = [
    (
        "air_temperature",
        "celsius",
        [0.0, 10.0, 21.5],
        [32.0, 50.0, 70.7],
        "degree_Fahrenheit",
        "°F",
        [0.0, 10.0, 21.5],
        "degree_Celsius",
        "°C",
    ),
    (
        # Exercises the degree_C alias -- ERDDAP's own spelling.
        "sea_surface_temperature",
        "degree_C",
        [0.0, 10.0, 21.5],
        [32.0, 50.0, 70.7],
        "degree_Fahrenheit",
        "°F",
        [0.0, 10.0, 21.5],
        "degree_Celsius",
        "°C",
    ),
    (
        "wind_speed",
        "m/s",
        [1.0, 10.0],
        [1.94, 19.44],
        "knot",
        "kn",
        [1.0, 10.0],
        "m/s",
        "m/s",
    ),
    (
        "significant_wave_height",
        "m",
        [1.0, 2.5],
        [3.28, 8.2],
        "foot",
        "ft",
        [1.0, 2.5],
        "m",
        "m",
    ),
    (
        "visibility_in_air",
        "meters",
        [1852.0, 10000.0],
        [1.0, 5.4],
        "nautical_mile",
        "nmi",
        [1.85, 10.0],
        "km",
        "km",
    ),
]


@pytest.mark.parametrize(
    (
        "standard_name",
        "source",
        "raw",
        "english",
        "english_unit",
        "english_label",
        "metric",
        "metric_unit",
        "metric_label",
    ),
    BUOY_BARN_CASES,
    ids=[case[0] for case in BUOY_BARN_CASES],
)
def test_buoy_barn_inventory_converts_for_both_systems(
    standard_name,
    source,
    raw,
    english,
    english_unit,
    english_label,
    metric,
    metric_unit,
    metric_label,
):
    values = pd.Series(raw, name="value")

    target = units.target_unit(standard_name, source, units.ENGLISH)
    assert target == english_unit
    assert rounded(units.convert(values, source, target)) == english
    assert units.label(target) == english_label

    target = units.target_unit(standard_name, source, units.METRIC)
    assert target == metric_unit
    assert rounded(units.convert(values, source, target)) == metric
    assert units.label(target) == metric_label


# barometric_pressure/millibars, air_pressure/mbar and air_pressure_at_sea_level/hPa
# are the same physical unit under three different spellings -- issue #144
# put mb (not psi) in TARGETS for both systems, since that is what mariners
# read off a barometer face.
PRESSURE_CASES = [
    ("barometric_pressure", "millibars"),
    ("air_pressure", "mbar"),
    ("air_pressure_at_sea_level", "hPa"),
]


@pytest.mark.parametrize(("standard_name", "source"), PRESSURE_CASES)
@pytest.mark.parametrize("system", [units.ENGLISH, units.METRIC])
def test_pressure_family_labels_as_mb_in_both_systems(standard_name, source, system):
    values = pd.Series([1013.0, 1020.5])

    target = units.target_unit(standard_name, source, system)
    converted = units.convert(values, source, target)

    assert units.label(target) == "mb"
    assert rounded(converted) == [1013.0, 1020.5]


# Standard names Buoy Barn reports that are absent from TARGETS, with the real
# unit strings it uses for them.
PASSTHROUGH_CASES = [
    ("sea_water_salinity", "psu"),
    ("turbidity", "ntu"),
    ("sea_water_density", "kg/m^3"),
    ("wind_from_direction", "degrees"),
    ("sea_water_pressure", "decibars"),
    ("sea_water_pH_reported_on_total_scale", "1"),
]


@pytest.mark.parametrize(("standard_name", "source"), PASSTHROUGH_CASES)
@pytest.mark.parametrize("system", [units.ENGLISH, units.METRIC])
def test_standard_names_outside_targets_pass_through_unchanged(
    standard_name,
    source,
    system,
):
    values = pd.Series([1.0, 2.0, 3.0])

    target = units.target_unit(standard_name, source, system)

    assert target == source
    assert units.convert(values, source, target).tolist() == values.tolist()


def test_unparsable_source_passes_through_target_unit():
    assert units.target_unit("air_temperature", "bogus_unit", units.ENGLISH) == (
        "bogus_unit"
    )


def test_convert_leaves_values_alone_for_an_unparsable_source():
    """convert() is expected to see this directly: target_unit() already
    returns the source unchanged when it can't be parsed, but convert() must
    not raise either, in case a caller reaches it with the mismatch still in
    place."""
    values = pd.Series([1.0, 2.0])

    result = units.convert(values, "bogus_unit", "degree_Fahrenheit")

    assert result.tolist() == [1.0, 2.0]


def test_dimensionality_mismatch_passes_through_target_unit():
    """air_temperature in metres makes no physical sense -- Buoy Barn and our
    table disagree, which is a bug, but not one that should raise."""
    target = units.target_unit("air_temperature", "m", units.ENGLISH)

    assert target == "m"


def test_dimensionality_mismatch_reports_to_monitoring(monkeypatch):
    reported = {}

    def fake_report(error, *, where, level, **tags):
        reported["error"] = error
        reported["where"] = where
        reported["level"] = level
        reported["tags"] = tags

    monkeypatch.setattr(units.monitoring, "report", fake_report)

    units.target_unit("air_temperature", "m", units.ENGLISH)

    assert reported["where"] == "units.target_unit"
    assert reported["level"] == "warning"
    assert reported["tags"] == {
        "standard_name": "air_temperature",
        "source": "m",
        "target": "degree_Fahrenheit",
    }


def test_resolved_dimensionality_mismatch_is_then_a_no_op_conversion():
    """Once target_unit() has fallen back to the source, convert() sees
    source == target and leaves the values alone rather than raising."""
    values = pd.Series([1.0, 2.0])
    target = units.target_unit("air_temperature", "m", units.ENGLISH)

    result = units.convert(values, "m", target)

    assert result.tolist() == [1.0, 2.0]


def test_nan_survives_a_conversion():
    values = pd.Series([0.0, np.nan, 21.5])

    result = units.convert(values, "celsius", "degree_Fahrenheit")

    assert result.iloc[0] == pytest.approx(32.0)
    assert pd.isna(result.iloc[1])
    assert result.iloc[2] == pytest.approx(70.7)


def test_dataframe_converts_like_a_series_keeping_columns_and_index():
    df = pd.DataFrame(
        {"a": [0.0, 10.0], "b": [21.5, np.nan]},
        index=["first", "second"],
    )

    result = units.convert(df, "celsius", "degree_Fahrenheit")

    assert isinstance(result, pd.DataFrame)
    assert list(result.columns) == ["a", "b"]
    assert list(result.index) == ["first", "second"]
    assert rounded(result["a"]) == [32.0, 50.0]
    assert result["b"].iloc[0] == pytest.approx(70.7)
    assert pd.isna(result["b"].iloc[1])


LABEL_CASES = [
    ("degree_Celsius", "°C"),
    ("degree_Fahrenheit", "°F"),
    ("knot", "kn"),
    ("foot", "ft"),
    ("nautical_mile", "nmi"),
    ("m/s", "m/s"),
    ("m", "m"),
    ("km", "km"),
    ("celsius", "°C"),
    ("ntu", "ntu"),
    # The mb override, both spellings that TARGETS' pressure family can
    # produce as a target string.
    ("mbar", "mb"),
    ("millibars", "mb"),
    # Numerically identical to a millibar, but pint gives it a distinct
    # symbol ("hPa"), so the override on the formatted result doesn't fire
    # here directly -- it only ever sees "mbar", once target_unit() has
    # already collapsed the pressure family onto that string.
    ("hPa", "hPa"),
    # Unparsable -- falls back to the raw string rather than raising.
    ("bogus_unit", "bogus_unit"),
    # pint formats the dimensionless unit as an empty string, which would
    # otherwise render an axis as "Something ()".
    ("1", "1"),
]


@pytest.mark.parametrize(("unit", "expected"), LABEL_CASES)
def test_label(unit, expected):
    assert units.label(unit) == expected
