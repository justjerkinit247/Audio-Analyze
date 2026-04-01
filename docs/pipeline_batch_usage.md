# Pipeline Batch Usage

This branch contains two batch-oriented entrypoints:

- `src/audio_analyze/batch_main.py` — minimal Phase 2 batch analysis
- `src/audio_analyze/pipeline_batch.py` — pipeline-oriented batch analysis with manifest and video cues

## Recommended local test command

```powershell
python .\src\audio_analyze\pipeline_batch.py --input-dir "C:\Users\Tt-rexX\Music\TestAudio"
```

## Output files

The pipeline-oriented command writes to `outputs\pipeline_batch_run` by default and creates:

- `summary.csv`
- `prompt_profiles.txt`
- `video_cues.txt`
- `manifest.json`
- `json\*_analysis.json`

## Why this exists

This is a bridge layer between raw audio analysis and later music-video workflow steps.
It produces outputs that are easier to reuse for prompt construction, batch tracking, and downstream automation.
