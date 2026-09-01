"""הסקת טיפוסים אוטומטית מהרצת קוד (Runtime Type Inference & Annotation).

דוגם את הטיפוסים האמיתיים שעוברים בארגומנטים ובערכי החזרה של פונקציות
בזמן ריצת טסטים או תסריט, ומייצר Type Annotations מודרניים עבור קבצי המקור.
"""

from __future__ import annotations

import os
import sys
import types
from dataclasses import dataclass, field
from typing import Any


def _type_name(val: Any) -> str:
    """מחזיר שם טיפוס פייתוני תקני ומודרני."""
    if val is None:
        return "None"
    t = type(val)
    if t is int:
        return "int"
    if t is float:
        return "float"
    if t is str:
        return "str"
    if t is bool:
        return "bool"
    if t is list:
        if val:
            elem_types = {_type_name(x) for x in val[:5]}
            inner = " | ".join(sorted(elem_types))
            return f"list[{inner}]"
        return "list"
    if t is dict:
        return "dict"
    if t is tuple:
        return "tuple"
    if t is set:
        return "set"
    return getattr(t, "__name__", "Any")


@dataclass
class FunctionProfile:
    file: str
    name: str
    args: dict[str, set[str]] = field(default_factory=dict)
    returns: set[str] = field(default_factory=set)


class TypeCollector:
    """עוקב פרופיל קל משקל שאוסף טיפוסים מריצת פונקציות."""

    def __init__(self, target_dir: str = ".") -> None:
        self.target_dir = os.path.abspath(target_dir)
        self.profiles: dict[tuple[str, str], FunctionProfile] = {}
        self._orig_profile: Any = None

    def profile_fn(self, frame: types.FrameType, event: str, arg: Any) -> None:
        filename = frame.f_code.co_filename
        # דוגמים רק קבצים מתוך ספריית הפרויקט
        if not filename.startswith(self.target_dir) or "site-packages" in filename:
            return

        func_name = frame.f_code.co_name
        if func_name.startswith("__"):
            return

        key = (filename, func_name)
        if key not in self.profiles:
            self.profiles[key] = FunctionProfile(file=filename, name=func_name)

        prof = self.profiles[key]

        if event == "call":
            for arg_name, val in frame.f_locals.items():
                if arg_name != "self" and arg_name != "cls":
                    prof.args.setdefault(arg_name, set()).add(_type_name(val))
        elif event == "return":
            prof.returns.add(_type_name(arg))

    def __enter__(self) -> "TypeCollector":
        self._orig_profile = sys.getprofile()
        sys.setprofile(self.profile_fn)
        return self

    def __exit__(self, exc_type: Any, exc_val: Any, exc_tb: Any) -> None:
        sys.setprofile(self._orig_profile)

    def summary(self) -> dict[str, dict[str, Any]]:
        out: dict[str, dict[str, Any]] = {}
        for (f, name), prof in self.profiles.items():
            args_summary = {}
            for arg_name, types_set in prof.args.items():
                if "None" in types_set and len(types_set) > 1:
                    non_none = sorted(t for t in types_set if t != "None")
                    args_summary[arg_name] = f"{' | '.join(non_none)} | None"
                else:
                    args_summary[arg_name] = " | ".join(sorted(types_set))

            ret_summary = ""
            if prof.returns:
                if "None" in prof.returns and len(prof.returns) > 1:
                    non_none = sorted(t for t in prof.returns if t != "None")
                    ret_summary = f"{' | '.join(non_none)} | None"
                else:
                    ret_summary = " | ".join(sorted(prof.returns))

            out.setdefault(f, {})[name] = {
                "args": args_summary,
                "return": ret_summary,
            }
        return out


def generate_type_signatures(inferred: dict[str, dict[str, Any]]) -> dict[str, list[str]]:
    """מפיק שורות חתימה מעודכנות עם Type Hints מומלצים."""
    result: dict[str, list[str]] = {}
    for file_path, funcs in inferred.items():
        lines = []
        for fn_name, meta in funcs.items():
            args_str = ", ".join(f"{arg}: {t}" for arg, t in meta.get("args", {}).items())
            ret_str = f" -> {meta['return']}" if meta.get("return") else ""
            lines.append(f"def {fn_name}({args_str}){ret_str}:")
        result[file_path] = lines
    return result
