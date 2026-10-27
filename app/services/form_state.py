"""Pure helpers between widget values and the raw config dict, plus error mapping."""
from __future__ import annotations

from datetime import date
from typing import Any

from pydantic import ValidationError

from app.services.form_model import FieldSpec
from swatprep.config import SWATPrepConfig
from swatprep.qa import QACheck


def to_widget(spec: FieldSpec, raw: Any) -> Any:
    """Value from the YAML dict (or the default when absent) -> value for the widget."""
    value = spec.default if raw is None else raw
    if spec.kind in ("path", "text"):
        return "" if value is None else str(value)
    if spec.kind == "text_list":
        return ", ".join(str(v) for v in value) if value else ""
    if spec.kind == "multichoice":
        return [str(v) for v in value] if value else []
    if spec.kind == "date":
        if value is None or value == "":
            return None
        return value if isinstance(value, date) else date.fromisoformat(str(value))
    if spec.kind == "number":
        if value is None:
            return None
        return int(value) if spec.integer else float(value)
    if spec.kind == "choice":
        return None if value is None else str(value)
    if spec.kind == "mapping":
        return {str(k): str(v) for k, v in (value or {}).items()}
    return value  # bool


def from_widget(spec: FieldSpec, value: Any) -> Any:
    """Widget value -> value stored in the YAML dict (None means 'leave the key out')."""
    if spec.kind in ("path", "text"):
        return value.strip() or None if isinstance(value, str) else value
    if spec.kind == "text_list":
        items = [v.strip() for v in (value or "").split(",") if v.strip()]
        return items or None
    if spec.kind == "multichoice":
        return list(value) if value else None
    if spec.kind == "mapping":
        return dict(value) if value else None
    return value


def apply(section: dict, spec: FieldSpec, widget_value: Any) -> None:
    """Write a widget value into a section without adding defaults or touching unchanged keys."""
    new = from_widget(spec, widget_value)
    if spec.name in section:
        current = from_widget(spec, to_widget(spec, section[spec.name]))
        if new != current:
            if new is None:
                del section[spec.name]
            else:
                section[spec.name] = new
    else:
        default = from_widget(spec, to_widget(spec, None))
        if new is not None and new != default:
            section[spec.name] = new


def _key(loc: tuple) -> str:
    return ".".join(str(part) for part in loc)


def schema_errors(cfg: dict) -> dict[str, str]:
    """Validate the raw config with the core model; {dotted.location: message}, empty when valid."""
    try:
        SWATPrepConfig.model_validate(cfg)
    except ValidationError as exc:
        errors: dict[str, str] = {}
        for err in exc.errors():
            message = err["msg"].removeprefix("Value error, ")
            errors.setdefault(_key(err["loc"]) or "project", message)
        return errors
    return {}


def file_errors(checks: list[QACheck]) -> dict[str, str]:
    """Failed 'file_exists:<label>' checks -> {dotted.location: message}; 'clip[0].src' -> 'clip.0.src'."""
    errors = {}
    for c in checks:
        if c.status == "fail" and c.name.startswith("file_exists:"):
            label = c.name.split(":", 1)[1].replace("[", ".").replace("]", "")
            errors[label] = c.message
    return errors


def count_for(errors: dict[str, str], section: str) -> int:
    return sum(1 for key in errors if key == section or key.startswith(section + "."))


def new_config(name: str, crs: str) -> dict:
    return {"project": {"name": name, "crs": crs, "output_dir": "./output", "targets": ["swatplus"]}}
