"""Describe each config field (from the Pydantic models) so the UI can draw the right input."""
from __future__ import annotations

import types
import typing
from dataclasses import dataclass
from datetime import date
from pathlib import Path
from typing import Any, Literal

from pydantic import BaseModel
from pydantic_core import PydanticUndefined

Kind = Literal[
    "path", "choice", "multichoice", "bool", "number", "date", "text", "text_list", "mapping", "model", "model_list"
]


class UnsupportedFieldError(TypeError):
    """A config field uses a type the form does not know how to draw."""


@dataclass(frozen=True)
class FieldSpec:
    name: str
    kind: Kind
    required: bool
    optional: bool  # None is an accepted value
    default: Any = None
    choices: tuple[str, ...] = ()
    integer: bool = False
    min_value: float | None = None  # from ge / gt
    max_value: float | None = None  # from le
    exclusive_min: bool = False  # True when the bound came from gt
    nested: type[BaseModel] | None = None


def _unwrap_optional(annotation: Any) -> tuple[Any, bool]:
    origin = typing.get_origin(annotation)
    if origin in (typing.Union, types.UnionType):
        args = [a for a in typing.get_args(annotation) if a is not type(None)]
        if len(args) == 1:
            return args[0], True
    return annotation, False


def _is_model(tp: Any) -> bool:
    return isinstance(tp, type) and issubclass(tp, BaseModel)


def _classify(tp: Any) -> tuple[Kind, dict]:
    origin = typing.get_origin(tp)
    if tp is Path:
        return "path", {}
    if origin is Literal:
        return "choice", {"choices": tuple(typing.get_args(tp))}
    if origin is list:
        (item,) = typing.get_args(tp)
        if typing.get_origin(item) is Literal:
            return "multichoice", {"choices": tuple(typing.get_args(item))}
        if item is str:
            return "text_list", {}
        if _is_model(item):
            return "model_list", {"nested": item}
    if origin is dict and typing.get_args(tp) == (str, str):
        return "mapping", {}
    if tp is bool:
        return "bool", {}
    if tp in (int, float):
        return "number", {"integer": tp is int}
    if tp is date:
        return "date", {}
    if tp is str:
        return "text", {}
    if _is_model(tp):
        return "model", {"nested": tp}
    raise UnsupportedFieldError(f"No form input for type {tp!r}")


def field_spec(model: type[BaseModel], name: str) -> FieldSpec:
    info = model.model_fields[name]
    tp, optional = _unwrap_optional(info.annotation)
    kind, extra = _classify(tp)

    if info.default_factory is not None:
        default = info.default_factory()
    elif info.default is PydanticUndefined:
        default = None
    else:
        default = info.default
    if isinstance(default, Path):
        default = default.as_posix()
    if isinstance(default, BaseModel):
        default = default.model_dump()

    bounds: dict[str, Any] = {}
    for meta in info.metadata:
        if getattr(meta, "ge", None) is not None:
            bounds["min_value"] = meta.ge
        if getattr(meta, "gt", None) is not None:
            bounds["min_value"], bounds["exclusive_min"] = meta.gt, True
        if getattr(meta, "le", None) is not None:
            bounds["max_value"] = meta.le

    return FieldSpec(name=name, kind=kind, required=info.is_required(), optional=optional,
                     default=default, **extra, **bounds)


def humanize(name: str) -> str:
    """'swat_code_col' -> 'Swat code col'."""
    text = name.replace("_", " ")
    return text[:1].upper() + text[1:]
