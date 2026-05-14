# LTX-ASMO Memory Bank v1

This branch extends the learning loop with:

```text
optional visual critic
strategy scorer
ASMO Memory Bank
next scene planner
```

## Full pipeline

```text
LTX live session
→ return files
→ assembler journal
→ human scorecard
→ optional visual critic
→ feature extractor
→ strategy scorer
→ ASMO Memory Bank
→ next scene plan
```

## Build visual critic report

```powershell
py -m src.audio_analyze.ltx_visual_critic `
  --state-root "outputs\ltx_video_run\_state"
```

Optional external visual AI JSON can be supplied later:

```powershell
py -m src.audio_analyze.ltx_visual_critic `
  --state-root "outputs\ltx_video_run\_state" `
  --external-critic-json "outputs\ltx_video_run\_state\active\critic\external_visual_ai.json"
```

## Score strategies

```powershell
py -m src.audio_analyze.ltx_strategy_scorer `
  --state-root "outputs\ltx_video_run\_state"
```

## Update ASMO Memory Bank

```powershell
py -m src.audio_analyze.asmo_memory_bank init `
  --state-root "outputs\ltx_video_run\_state"

py -m src.audio_analyze.asmo_memory_bank update `
  --state-root "outputs\ltx_video_run\_state"
```

## Build next scene plan

```powershell
py -m src.audio_analyze.ltx_next_scene_planner `
  --plan-json "outputs\ltx_video_run\holy_cheeks_ltx_plan.json" `
  --state-root "outputs\ltx_video_run\_state" `
  --output "outputs\ltx_video_run\holy_cheeks_ltx_plan_next.json"
```

## Memory files

```text
outputs/ltx_video_run/_state/memory/
  winning_patterns.jsonl
  failure_patterns.jsonl
  movement_skills.json
  camera_skills.json
  prompt_rules.json
  strategy_scores.jsonl
```

This keeps compact learned memory without saving endless raw JSON.
