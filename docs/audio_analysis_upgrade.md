# Audio Analysis Upgrade v1

This branch adds a WAV-first beat/onset analysis helper for the LTX planning pipeline.

## Why WAV/FLAC preferred

Lossless audio keeps cleaner transient information for:

```text
beat detection
onset detection
downbeat alignment
scene boundary confidence
motion timing confidence
```

MP3 can still work, but compressed files can smear transients and slightly reduce beat-grid confidence.

## Analyze audio

```powershell
py -m src.audio_analyze.audio_analysis_upgrade `
  --audio "inputs\audio\Holy Cheeks.wav" `
  --output "outputs\ltx_video_run\audio_analysis_upgrade.json"
```

## Analyze audio against an LTX scene plan

```powershell
py -m src.audio_analyze.audio_analysis_upgrade `
  --audio "inputs\audio\Holy Cheeks.wav" `
  --plan-json "outputs\ltx_video_run\holy_cheeks_ltx_plan.json" `
  --output "outputs\ltx_video_run\audio_analysis_upgrade.json"
```

## Output signals

```text
audio source quality class
tempo BPM
beat count
onset count
onset density
beat stability score
beat confidence
scene boundary confidence
```

## Recommended source audio

```text
48 kHz / 24-bit WAV preferred
44.1 kHz / 24-bit WAV acceptable
FLAC acceptable
high-bitrate MP3 usable but not ideal
```
