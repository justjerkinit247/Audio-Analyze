from __future__ import annotations

import builtins
from pathlib import Path
from typing import Any

from . import ltx_live_run
from .ltx_motion_freedom import (
    DEFAULT_LIVE_GUIDANCE_SCALE,
    DEFAULT_MAX_PROMPTED_TAPS,
    apply_motion_freedom_to_plan_file,
)


_ORIGINAL_INPUT = builtins.input
_ORIGINAL_RUN_AUTO = ltx_live_run.run_auto_audio_orchestrator
_ORIGINAL_GUIDANCE = ltx_live_run.DEFAULT_GUIDANCE_SCALE


def _normalized_input(prompt: str = "") -> str:
    value = _ORIGINAL_INPUT(prompt)
    if "Type LIVE to submit" in prompt:
        return value.strip().upper()
    return value


def _run_auto_with_motion_freedom(*args: Any, **kwargs: Any) -> dict[str, Any]:
    report = _ORIGINAL_RUN_AUTO(*args, **kwargs)
    plan_value = report.get("active_plan_json_resolved") or kwargs.get("output_plan")
    if not plan_value:
        raise RuntimeError("Motion-freedom profile could not locate the fresh plan JSON.")

    plan_path = Path(plan_value).resolve()
    patched = apply_motion_freedom_to_plan_file(
        plan_path,
        max_prompted_taps=DEFAULT_MAX_PROMPTED_TAPS,
    )
    profile = patched.get("motion_freedom_profile") or {}
    report["motion_freedom_profile"] = profile
    print(
        "Motion-freedom profile applied: "
        f"guidance {DEFAULT_LIVE_GUIDANCE_SCALE}, "
        f"maximum {DEFAULT_MAX_PROMPTED_TAPS} prompted tap accents."
    )
    return report


def main() -> None:
    builtins.input = _normalized_input
    ltx_live_run.DEFAULT_GUIDANCE_SCALE = DEFAULT_LIVE_GUIDANCE_SCALE
    ltx_live_run.run_auto_audio_orchestrator = _run_auto_with_motion_freedom
    try:
        ltx_live_run.main()
    finally:
        builtins.input = _ORIGINAL_INPUT
        ltx_live_run.DEFAULT_GUIDANCE_SCALE = _ORIGINAL_GUIDANCE
        ltx_live_run.run_auto_audio_orchestrator = _ORIGINAL_RUN_AUTO


if __name__ == "__main__":
    main()
