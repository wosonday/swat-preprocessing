import pytest

from app.services.form_layout import LAYOUT, SECTIONS, all_models, path_kind
from app.services.form_model import field_spec, humanize
from swatprep.config import (
    DEMConfig, FillNetCDFConfig, ProjectConfig, StreamflowConfig, SWATPrepConfig, WeatherConfig, WeatherFillConfig,
)


@pytest.mark.parametrize(
    "model,name,kind",
    [
        (DEMConfig, "path", "path"),
        (ProjectConfig, "boundary", "path"),
        (DEMConfig, "resampling", "choice"),
        (ProjectConfig, "targets", "multichoice"),
        (DEMConfig, "clip", "bool"),
        (DEMConfig, "resolution", "number"),
        (WeatherConfig, "start", "date"),
        (ProjectConfig, "name", "text"),
        (StreamflowConfig, "stations", "text_list"),
        (FillNetCDFConfig, "var_map", "mapping"),
        (WeatherConfig, "units", "model"),
        (SWATPrepConfig, "clip", "model_list"),
    ],
)
def test_kinds(model, name, kind):
    assert field_spec(model, name).kind == kind


def test_choice_values_and_default():
    spec = field_spec(DEMConfig, "resampling")
    assert spec.choices == ("nearest", "bilinear", "cubic")
    assert spec.default == "bilinear"


def test_required_and_optional():
    assert field_spec(DEMConfig, "path").required
    resolution = field_spec(DEMConfig, "resolution")
    assert not resolution.required and resolution.optional and resolution.default is None


def test_number_bounds():
    resolution = field_spec(DEMConfig, "resolution")
    assert resolution.min_value == 0 and resolution.exclusive_min and not resolution.integer
    radius = field_spec(FillNetCDFConfig, "search_radius")
    assert (radius.min_value, radius.max_value, radius.integer) == (0, 5, True)
    assert field_spec(WeatherFillConfig, "min_overlap_days").min_value == 0


def test_defaults_are_plain_values():
    assert field_spec(ProjectConfig, "output_dir").default == "output"
    assert field_spec(ProjectConfig, "targets").default == ["swatplus"]
    assert field_spec(WeatherConfig, "units").default == {"precip": "mm", "temperature": "degC"}


def test_every_field_type_is_supported():
    for model in all_models():
        for name in model.model_fields:
            field_spec(model, name)  # raises UnsupportedFieldError otherwise


def test_layout_covers_every_config_field():
    models = all_models()
    assert set(LAYOUT) == set(models)
    for model in models:
        assert sorted(LAYOUT[model]) == sorted(model.model_fields), model.__name__


def test_sections_match_root_fields():
    assert list(SECTIONS) == [n for n in LAYOUT[SWATPrepConfig] if n != "project"]


def test_path_kinds():
    assert path_kind(DEMConfig, "path") == "file"
    assert path_kind(WeatherConfig, "data_dir") == "dir"
    assert path_kind(StreamflowConfig, "path") == "file_or_dir"
    assert path_kind(ProjectConfig, "output_dir") == "output"


def test_humanize():
    assert humanize("swat_code_col") == "Swat code col"
