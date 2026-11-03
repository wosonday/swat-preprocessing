"""Example 4: how the web form is generated from the Pydantic models (no Streamlit needed).

Run:  uv run python docs/learning/04_form_from_model.py
"""
from app.services.form_layout import LABELS, LAYOUT
from app.services.form_model import field_spec, humanize
from app.services.form_state import apply, schema_errors, to_widget
from swatprep.config import WeatherFillConfig

# 1. Each field becomes a FieldSpec: kind -> which widget, bounds, default, help text.
for name in LAYOUT[WeatherFillConfig][:7]:
    spec = field_spec(WeatherFillConfig, name)
    print(f"{LABELS.get(name, humanize(name)):38} kind={spec.kind:6} default={spec.default!r:12} "
          f"min={spec.min_value}")

# 2. A widget change is written into the raw YAML dict; defaults are not added, so the YAML stays short.
section = {"type": "netcdf"}
apply(section, field_spec(WeatherFillConfig, "fill_ungauged"), True)        # changed -> written
apply(section, field_spec(WeatherFillConfig, "correct_ungauged"), True)     # equals default -> left out
apply(section, field_spec(WeatherFillConfig, "max_borrow_km"), 30.0)
print("\nraw dict:", section)
print("widget value of max_borrow_km:", to_widget(field_spec(WeatherFillConfig, "max_borrow_km"), section["max_borrow_km"]))

# 3. Errors come from the same core model, keyed by the field's dotted path (shown under that field).
cfg = {"project": {"name": "Demo", "crs": "EPSG:32648"},
       "weather": {"start": "2000-01-01", "end": "2000-12-31", "stations": "s.csv", "data_dir": "d",
                   "fill": {"type": "netcdf", "max_borrow_km": 0}}}
for where, message in schema_errors(cfg).items():
    print(f"error at {where}: {message}")
