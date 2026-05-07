"""Vendor-neutral music video pipeline entry point.

This module is the public command target for the music video pipeline.
The implementation currently reuses the existing LTX-compatible pipeline internals
while the project transitions away from the old song/vendor-specific filename.

Preferred command:
    python -m src.audio_analyze.music_video_pipeline plan ...

Convenience behavior:
    If the plan command does not include --audio, this wrapper automatically picks
    an audio file from inputs/audio. If multiple audio files exist, it uses the
    newest modified file and prints the selected path before continuing.
"""

from pathlib import Path
import sys

try:
    from .ltx_holy_cheeks_pipeline import (
        analyze_audio,
        build_plan,
        build_prompt,
        build_scenes,
        export_scene_audio,
        run_preflight,
        submit_all,
        submit_one,
        validate_plan,
        main as _legacy_main,
    )
except ImportError:
    from ltx_holy_cheeks_pipeline import (
        analyze_audio,
        build_plan,
        build_prompt,
        build_scenes,
        export_scene_audio,
        run_preflight,
        submit_all,
        submit_one,
        validate_plan,
        main as _legacy_main,
    )


ALLOWED_AUDIO = {".wav", ".mp3", ".m4a", ".flac", ".ogg", ".aiff", ".aif"}
DEFAULT_AUDIO_DIR = "inputs\\audio"


def _has_option(args, option_name):
    return option_name in args or any(arg.startswith(f"{option_name}=") for arg in args)


def _pop_option_value(args, option_name, default=None):
    cleaned = []
    value = default
    skip_next = False
    for index, arg in enumerate(args):
        if skip_next:
            skip_next = False
            continue
        if arg == option_name:
            if index + 1 >= len(args):
                raise ValueError(f"{option_name} requires a value")
            value = args[index + 1]
            skip_next = True
            continue
        if arg.startswith(f"{option_name}="):
            value = arg.split("=", 1)[1]
            continue
        cleaned.append(arg)
    return cleaned, value


def find_audio_file(audio_dir=DEFAULT_AUDIO_DIR):
    audio_dir = Path(audio_dir)
    if not audio_dir.exists():
        raise FileNotFoundError(f"Audio folder not found: {audio_dir.resolve()}")

    candidates = [
        path for path in audio_dir.iterdir()
        if path.is_file() and path.suffix.lower() in ALLOWED_AUDIO
    ]
    if not candidates:
        allowed = ", ".join(sorted(ALLOWED_AUDIO))
        raise FileNotFoundError(f"No audio files found in {audio_dir.resolve()} matching: {allowed}")

    candidates.sort(key=lambda path: (path.stat().st_mtime, path.name.lower()), reverse=True)
    return candidates[0]


def _inject_default_audio_for_plan(args):
    if not args or args[0] != "plan":
        return args
    if _has_option(args, "--audio"):
        return args

    cleaned_args, audio_dir = _pop_option_value(args, "--audio-dir", DEFAULT_AUDIO_DIR)
    selected_audio = find_audio_file(audio_dir)
    print(f"Auto-selected audio: {selected_audio.resolve()}")

    # Insert after the subcommand so argparse sees it as a normal plan option.
    return [cleaned_args[0], "--audio", str(selected_audio.resolve()), *cleaned_args[1:]]


def main(argv=None):
    original_argv = list(sys.argv if argv is None else argv)
    script_name = original_argv[0] if original_argv else "music_video_pipeline"
    args = original_argv[1:] if len(original_argv) > 1 else []
    patched_args = _inject_default_audio_for_plan(args)

    old_argv = sys.argv
    try:
        sys.argv = [script_name, *patched_args]
        _legacy_main()
    finally:
        sys.argv = old_argv


if __name__ == "__main__":
    main()
