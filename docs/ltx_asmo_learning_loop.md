# LTX-ASMO Learning Loop v1

This add-on turns LTX live-session outputs into reusable intelligence for ASMO.

## Core loop

```text
live session
→ evidence capture
→ feature extraction
→ feedback analyzer
→ policy memory
→ ASMO feedback adapter
→ improved next plan
```

## State folder

```text
outputs/ltx_video_run/_state/
  active/
    manifest.json
    scene_returns/
    assembler/
      assembly_attempts.jsonl
      latest_assembly_report.json
    review/
      human_scorecard.json
    features/
    feedback/
  previous/
  summaries/
  policy/
  locks/
```

## Start a live session safely

```powershell
py -m src.audio_analyze.ltx_live_session submit-all `
  --plan-json "outputs\ltx_video_run\holy_cheeks_ltx_plan.json" `
  --output-dir "outputs\ltx_video_run" `
  --live
```

This rotates active state, preserves one previous raw session, and ingests result files.

## Assemble with journaling

```powershell
py -m src.audio_analyze.ltx_assemble_state `
  --downloads "outputs\ltx_video_run\downloads" `
  --plan-json "outputs\ltx_video_run\holy_cheeks_ltx_plan.json" `
  --output "outputs\ltx_video_run\assembled\sync_test.mp4" `
  --audio-offset-seconds -0.15
```

Every assembler run appends to:

```text
outputs/ltx_video_run/_state/active/assembler/assembly_attempts.jsonl
```

## Add human review

Create or edit:

```text
outputs/ltx_video_run/_state/active/review/human_scorecard.json
```

Example:

```json
{
  "scene_01": {
    "beat_sync": 7,
    "motion_match": 6,
    "camera_match": 7,
    "visual_quality": 8,
    "prompt_obedience": 6,
    "notes": "motion lagged after midpoint; camera too stiff"
  }
}
```

Scores can be 0-10.

## Analyze feedback and update policy

```powershell
py -m src.audio_analyze.ltx_feedback_analyzer `
  --state-root "outputs\ltx_video_run\_state" `
  --update-policy
```

## Apply feedback to next plan

```powershell
py -m src.audio_analyze.asmo_engine.feedback_adapter `
  --plan-json "outputs\ltx_video_run\holy_cheeks_ltx_plan.json" `
  --state-root "outputs\ltx_video_run\_state" `
  --output "outputs\ltx_video_run\holy_cheeks_ltx_plan_next.json"
```

Use the new plan for the next live session.
