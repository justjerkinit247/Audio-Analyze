# ASMO Engine Usage

ASMO means Adaptive Semantic Motion Orchestration.

It is an additive lyric/audio motion-sync layer for the existing Audio-Analyze LTX workflow.

## Basic Usage

```bash
python -m src.audio_analyze.asmo_engine.cli --lyrics inputs/lyrics/song.txt
```

## Output

The engine produces:

- motion timeline metadata
- beat-locked event timing
- camera state transitions
- LTX prompt directives

## Purpose

ASMO exists to reduce random AI motion generation by synchronizing choreography and camera timing to lyric structure and rhythmic anchors.
