"""Vendor-neutral music video pipeline entry point.

This module is the public command target for the music video pipeline.
The implementation currently reuses the existing LTX-compatible pipeline internals
while the project transitions away from the old song/vendor-specific filename.

Preferred command:
    python -m src.audio_analyze.music_video_pipeline plan ...
"""

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
        main,
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
        main,
    )


if __name__ == "__main__":
    main()
