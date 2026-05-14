# LTX-ASMO Integrated Intelligence Loop v1

This branch combines the tested add-ons into one workflow:

```text
LTX live session
→ return files
→ assembler journal
→ human scorecard
→ optional visual critic
→ feature extractor
→ feedback analyzer
→ strategy scorer
→ ASMO Memory Bank
→ audio analysis upgrade
→ next scene plan
```

## Run the integrated loop

```powershell
py -m src.audio_analyze.ltx_intelligence_loop `
  --plan-json "outputs\ltx_video_run\holy_cheeks_ltx_plan.json" `
  --state-root "outputs\ltx_video_run\_state" `
  --audio "inputs\audio\Holy Cheeks.wav" `
  --output-plan "outputs\ltx_video_run\holy_cheeks_ltx_plan_next.json"
```

## Optional visual AI input

If an outside visual AI produces a structured JSON report, pass it in:

```powershell
py -m src.audio_analyze.ltx_intelligence_loop `
  --plan-json "outputs\ltx_video_run\holy_cheeks_ltx_plan.json" `
  --state-root "outputs\ltx_video_run\_state" `
  --audio "inputs\audio\Holy Cheeks.wav" `
  --external-critic-json "outputs\ltx_video_run\_state\active\critic\external_visual_ai.json" `
  --output-plan "outputs\ltx_video_run\holy_cheeks_ltx_plan_next.json"
```

## Local test

```powershell
python -m pytest tests/test_ltx_integrated_intelligence_loop_smoke.py
```

## Output files

```text
outputs/ltx_video_run/_state/active/features/audio_analysis_upgrade.json
outputs/ltx_video_run/_state/active/features/scene_features.jsonl
outputs/ltx_video_run/_state/active/critic/visual_critic_report.json
outputs/ltx_video_run/_state/active/feedback/feedback_packet.json
outputs/ltx_video_run/_state/active/feedback/strategy_scores.json
outputs/ltx_video_run/_state/active/feedback/intelligence_loop_summary.json
outputs/ltx_video_run/_state/memory/memory_summary.json
outputs/ltx_video_run/holy_cheeks_ltx_plan_next.json
```
