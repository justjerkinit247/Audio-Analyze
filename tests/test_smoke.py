from src.audio_analyze.main import analyze_audio


def test_import_smoke():
    assert callable(analyze_audio)
