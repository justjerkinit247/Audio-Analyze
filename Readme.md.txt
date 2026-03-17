# Audio Analyze

Starter project for vocal profile and audio analysis experiments.

## Current prototype
This branch contains the first vocal profile prototype.

## Project structure

- `src/audio_analyze/main.py` - starter analysis script
- `tests/test_smoke.py` - basic import test
- `data/sample/` - place sample audio files here
- `outputs/` - analysis results go here
- `docs/notes.md` - working notes

## First goal
Analyze a WAV or MP3 file and output simple metrics:
- duration
- sample rate
- tempo estimate
- pitch estimate
- RMS loudness estimate

## Run

```bash
python -m src.audio_analyze.main "path/to/audio.wav"