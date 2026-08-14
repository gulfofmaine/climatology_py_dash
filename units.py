"""Unit conversion for display, free of marimo and network access.

Buoy Barn (and the ERDDAP servers behind it) report each variable in whatever
unit its instrument or provider used, not necessarily the one this dashboard
wants to show. This module maps a CF standard name plus a source unit onto a
metric or English display unit, converts the values, and formats a short
label for an axis or column header.

The conversion table below is transcribed from the Mariner's Dashboard
(https://github.com/gulfofmaine/Neracoos-1-Buoy-App/tree/main/src/Features/Units)
and deliberately covers more standard names than Buoy Barn currently exposes,
so a newly flagged variable is already handled rather than silently falling
back to passthrough the day it first appears.
"""

import json
from string import Template

import pint

import monitoring

ENGLISH = "English"
METRIC = "Metric"

# ERDDAP/Buoy Barn emits degree_C, which bare pint does not define -- only
# degC and the Celsius/celsius spellings. degree_Celsius is already a pint
# alias for celsius and needs no define of its own.
ureg = pint.UnitRegistry()
ureg.define("@alias degree_Celsius = degree_C = degrees_C")
ureg.define("@alias degree_Fahrenheit = degree_F = degrees_F")

# standard_name -> (metric unit, english unit), as pint unit strings.
TARGETS: dict[str, tuple[str, str]] = {
    # Temperature
    "air_temperature": ("degree_Celsius", "degree_Fahrenheit"),
    "sea_water_temperature": ("degree_Celsius", "degree_Fahrenheit"),
    "sea_surface_temperature": ("degree_Celsius", "degree_Fahrenheit"),
    "dew_point_temperature": ("degree_Celsius", "degree_Fahrenheit"),
    # Speed
    "wind_speed": ("m/s", "knot"),
    "wind_speed_of_gust": ("m/s", "knot"),
    "wind_speed_sc": ("m/s", "knot"),
    "wind_speed_ve": ("m/s", "knot"),
    "sea_water_speed": ("m/s", "knot"),
    "sea_water_velocity": ("m/s", "knot"),
    "eastward_wind": ("m/s", "knot"),
    "northward_wind": ("m/s", "knot"),
    "eastward_sea_water_velocity": ("m/s", "knot"),
    "northward_sea_water_velocity": ("m/s", "knot"),
    "wind_gust": ("m/s", "knot"),
    "wind_min": ("m/s", "knot"),
    "wind_peak": ("m/s", "knot"),
    # Height/level
    "significant_wave_height": ("m", "foot"),
    "max_wave_height": ("m", "foot"),
    "significant_height_of_wind_and_swell_waves": ("m", "foot"),
    "significant_height_of_wind_and_swell_waves_3": ("m", "foot"),
    "sea_surface_wave_significant_height": ("m", "foot"),
    "sea_water_level": ("m", "foot"),
    "surface_altitude": ("m", "foot"),
    "predicted_sea_water_level": ("m", "foot"),
    "sea_surface_height_above_geopotential_datum": ("m", "foot"),
    "tidal_sea_surface_height_above_mean_higher_high_water": ("m", "foot"),
    "tidal_sea_surface_height_above_mean_lower_low_water": ("m", "foot"),
    "tidal_sea_surface_height_above_mean_sea_level": ("m", "foot"),
    # Visibility -- metric is km, not the source metres, so "metric" is not a
    # no-op here the way it is for the other families.
    "visibility_in_air": ("km", "nautical_mile"),
    "min_visibility": ("km", "nautical_mile"),
    "max_visibility": ("km", "nautical_mile"),
    # Atmospheric pressure, in mb in both systems: mariners read mb off a
    # barometer face, and the Mariner's Dashboard's psi for English is an
    # oversight (issue #144). sea_water_pressure (decibars) is deliberately
    # absent -- it is a water pressure, not an atmospheric one.
    "barometric_pressure": ("mbar", "mbar"),
    "air_pressure": ("mbar", "mbar"),
    "air_pressure_at_sea_level": ("mbar", "mbar"),
    "sea_level_pressure": ("mbar", "mbar"),
}

# Overrides applied to pint's short pretty format, keyed on the formatted
# result. Both a millibars and an hPa source end up displayed as mb: the
# pressure family's target is literally the string "mbar" in TARGETS above,
# regardless of which of the two the source happened to be.
_LABEL_OVERRIDES = {"mbar": "mb"}


# Pages that carry the sidebar toggle. The <head> snippet below is injected
# into every notebook, root and the datum calculator included, and neither of
# those has a unit preference to restore -- seeding one onto their URL would
# just be a meaningless query string the user is left looking at.
_TOGGLE_PATHS = ("/by_platform", "/by_standard_name", "/climatology")

# Runs before marimo's own (deferred, module) bundle, so the URL is already
# seeded by the time marimo reads its query parameters.
#
# ?units= stays the single source of truth: an explicit one in the URL always
# wins over the stored preference, so a shared link keeps meaning what its
# sender saw. localStorage rather than a cookie -- this is a first-party
# display preference and the server has no use for it.
_HEAD_SCRIPT = Template("""<script>
(function () {
  var KEY = "neracoos-units";
  var PARAM = "units";
  var ALLOWED = $systems;
  var PATHS = $paths;

  function stored() {
    try {
      var value = window.localStorage.getItem(KEY);
      return ALLOWED.indexOf(value) === -1 ? null : value;
    } catch (error) {
      return null;
    }
  }

  function persist() {
    var value = new URLSearchParams(window.location.search).get(PARAM);
    if (ALLOWED.indexOf(value) === -1) return;
    try {
      window.localStorage.setItem(KEY, value);
    } catch (error) {
      /* Private browsing refuses writes; the toggle still works per-tab. */
    }
  }

  function onToggledPage() {
    return PATHS.some(function (path) {
      return window.location.pathname.indexOf(path) === 0;
    });
  }

  var params = new URLSearchParams(window.location.search);
  if (onToggledPage() && !params.has(PARAM)) {
    var value = stored();
    if (value) {
      params.set(PARAM, value);
      history.replaceState(
        history.state,
        "",
        window.location.pathname + "?" + params.toString() + window.location.hash
      );
    }
  }

  /* The History API fires no event for its own calls, and marimo writes the
     toggle back through it, so the only way to notice is to wrap them. */
  ["pushState", "replaceState"].forEach(function (name) {
    var original = history[name];
    history[name] = function () {
      var result = original.apply(this, arguments);
      persist();
      return result;
    };
  });
  window.addEventListener("popstate", persist);
  persist();
})();
</script>
""")


def head_script() -> str:
    """The <head> snippet for ``marimo.create_asgi_app(html_head=...)``.

    Carries the unit preference across pages and sessions in ``localStorage``,
    seeding ``?units=`` onto the URL of a page that has the toggle before
    marimo reads its query parameters, and writing back whatever the toggle
    later sets.
    """
    return _HEAD_SCRIPT.substitute(
        systems=json.dumps([ENGLISH, METRIC]),
        paths=json.dumps(list(_TOGGLE_PATHS)),
    )


def target_unit(standard_name: str, source: str, system: str) -> str:
    """The unit values for ``standard_name`` should be displayed in.

    Passes ``source`` through unchanged for a standard name outside
    ``TARGETS``, or when ``source`` cannot be resolved against the target
    dimensionally -- either way there is nothing sensible to convert to.
    """
    entry = TARGETS.get(standard_name)
    if entry is None:
        return source
    target = entry[1] if system == ENGLISH else entry[0]

    try:
        source_unit = ureg.Unit(source)
    except (pint.UndefinedUnitError, TypeError):
        # Bare pint raises UndefinedUnitError for a name it has never heard
        # of, but a plain TypeError from its parser for CF-spaced compound
        # forms like "m s-1" -- both just mean "not a unit we can use."
        return source

    try:
        (1 * source_unit).to(target)
    except pint.DimensionalityError as error:
        # Source parses but its dimension doesn't match the target: Buoy Barn
        # says one thing and this table says another, which is a real bug
        # worth knowing about -- but not one worth crashing the dashboard over.
        monitoring.report(
            error,
            where="units.target_unit",
            level="warning",
            standard_name=standard_name,
            source=source,
            target=target,
        )
        return source

    return target


def convert(values, source: str, target: str):
    """Convert ``values`` (a Series or DataFrame of floats) from ``source`` to
    ``target``, preserving index/columns/name and any NaN gaps.

    Goes via a plain numpy array and pint's Quantity rather than pint-pandas'
    dtype: that dtype leaks into to_csv/to_dict and breaks marimo's table
    download and the vega spec, so the pandas object here is always a normal
    float frame, just with different numbers in it.
    """
    if source == target:
        return values

    try:
        source_unit = ureg.Unit(source)
    except (pint.UndefinedUnitError, TypeError):
        return values

    # Temperature is non-multiplicative (a Celsius-to-Fahrenheit conversion is
    # an offset, not just a scale); going through a Quantity rather than a bare
    # Unit multiplication is what makes pint apply that offset correctly.
    converted = (values.to_numpy() * source_unit).to(target).magnitude

    if hasattr(values, "columns"):
        return values.__class__(converted, index=values.index, columns=values.columns)
    return values.__class__(converted, index=values.index, name=values.name)


def label(unit: str) -> str:
    """Short display form of ``unit`` for an axis title or column header."""
    try:
        formatted = f"{ureg.Unit(unit):~P}"
    except (pint.UndefinedUnitError, TypeError):
        return unit

    formatted = _LABEL_OVERRIDES.get(formatted, formatted)
    # pint formats the dimensionless unit "1" as an empty string, which would
    # render an axis as "Something ()" -- fall back to the raw unit instead.
    return formatted if formatted.strip() else unit
