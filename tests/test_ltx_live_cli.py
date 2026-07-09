from audio_analyze import ltx_live_cli


def test_live_confirmation_is_case_insensitive(monkeypatch):
    monkeypatch.setattr(ltx_live_cli, "_ORIGINAL_INPUT", lambda prompt="": "live")

    assert ltx_live_cli._normalized_input(
        "Type LIVE to submit exactly one paid LTX request: "
    ) == "LIVE"


def test_non_confirmation_input_is_unchanged(monkeypatch):
    monkeypatch.setattr(ltx_live_cli, "_ORIGINAL_INPUT", lambda prompt="": " 12.5 ")

    assert ltx_live_cli._normalized_input("Audio starting second [0]: ") == " 12.5 "
