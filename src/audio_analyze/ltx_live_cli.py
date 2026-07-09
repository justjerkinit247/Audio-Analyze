from __future__ import annotations

import builtins

from . import ltx_live_run


_ORIGINAL_INPUT = builtins.input


def _normalized_input(prompt: str = "") -> str:
    value = _ORIGINAL_INPUT(prompt)
    if "Type LIVE to submit" in prompt:
        return value.strip().upper()
    return value


def main() -> None:
    builtins.input = _normalized_input
    try:
        ltx_live_run.main()
    finally:
        builtins.input = _ORIGINAL_INPUT


if __name__ == "__main__":
    main()
