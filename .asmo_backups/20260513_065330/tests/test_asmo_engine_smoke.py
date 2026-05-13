from pathlib import Path

from src.audio_analyze.asmo_engine.asmo_engine import ASMOEngine


def test_asmo_generates_motion_timeline(tmp_path):
    lyrics = tmp_path / "test_song.txt"

    lyrics.write_text(
        "[00:00.500] hands in the air\n"
        "[00:01.500] drop down low\n",
        encoding="utf-8",
    )

    timeline = ASMOEngine().generate_timeline(
        lyric_path=lyrics,
    )

    assert timeline["schema"] == "asmo.motion_timeline.v1"
    assert len(timeline["events"]) >= 2
