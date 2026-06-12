# ASMO negative prompt memory

This workflow lets ASMO convert failed-run feedback into reusable negative prompt terms for the next LTX rerun.

The intent is simple:

```text
last run failure -> ASMO issue detection -> learned cleanup terms -> next run [NEGATIVE_PROMPT]
```

## What gets saved

ASMO writes a compact memory file:

```text
outputs/ltx_video_run/_state/memory/asmo_negative_prompt_memory.json
```

And an append-only ledger:

```text
outputs/ltx_video_run/_state/memory/negative_prompt_ledger.jsonl
```

The ledger records:

- session id
- scene id
- detected issues
- terms added
- scores that caused the lesson
- timestamp

## Update memory from feedback

After `ltx_feedback_analyzer.py` creates a feedback packet, run:

```powershell
$env:PYTHONPATH = "src"
python -m audio_analyze.asmo_negative_prompt_memory update --state-root "outputs\ltx_video_run\_state"
```

This reads:

```text
outputs/ltx_video_run/_state/active/feedback/feedback_packet.json
```

and writes:

```text
outputs/ltx_video_run/_state/active/feedback/asmo_negative_prompt_terms.json
outputs/ltx_video_run/_state/memory/asmo_negative_prompt_memory.json
outputs/ltx_video_run/_state/memory/negative_prompt_ledger.jsonl
```

## Preview terms for a scene

```powershell
python -m audio_analyze.asmo_negative_prompt_memory terms --state-root "outputs\ltx_video_run\_state" --scene-id 1 --scene-hint "duck flies toward clouds"
```

## Apply memory to a plan manually

```powershell
python -m audio_analyze.asmo_negative_prompt_memory apply-plan --plan-json "outputs\ltx_video_run\current_plan.json" --state-root "outputs\ltx_video_run\_state" --output "outputs\ltx_video_run\next_plan_with_negative_memory.json"
```

## Automatic next-plan integration

`ltx_next_scene_planner.py` now updates and applies negative prompt memory when building the next plan.

```powershell
python -m audio_analyze.ltx_next_scene_planner --plan-json "outputs\ltx_video_run\current_plan.json" --state-root "outputs\ltx_video_run\_state" --output "outputs\ltx_video_run\next_plan.json"
```

The next plan gets:

```text
asmo_negative_prompt_memory_applied: true
asmo_negative_prompt_memory_records: [...]
asmo_negative_prompt_memory_summary: {...}
```

Each scene also gets:

```text
asmo_negative_prompt_memory
```

and its `[NEGATIVE_PROMPT]` section is updated with learned cleanup terms.

## Example issue-to-term mapping

```text
motion_intent_mismatch -> motion drift, unclear subject movement, wrong motion direction
camera_intent_mismatch -> chaotic camera movement, camera drift away from subject, conflicting camera motion
prompt_obedience_low -> ignored prompt instructions, unrelated visual elements, scene concept drift
seed_drift -> seed image drift, changed subject identity, changed background, changed framing
```

## Guardrails

- This does not call LTX or any external service.
- This does not require local AI/Ollama.
- This does not delete old memory.
- This appends a local audit trail so bad runs become reusable correction data.
