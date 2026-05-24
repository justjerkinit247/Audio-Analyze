from pathlib import Path
import json
import sys

from src.audio_analyze.asmo_engine.ltx_run_integrator import inject_asmo_into_ltx_run_plan

repo = Path(".").resolve()

plan_json = repo / "outputs" / "ltx_video_run" / "holy_cheeks_ltx_plan_next_reviewed.json"
output_json = repo / "outputs" / "ltx_video_run" / "holy_cheeks_ltx_plan_true_asmo_injected.json"

lyrics_dir = repo / "inputs" / "lyrics"

print("Repo:", repo)
print("Plan exists:", plan_json.exists(), plan_json)
print("Lyrics dir exists:", lyrics_dir.exists(), lyrics_dir)

if not plan_json.exists():
    raise FileNotFoundError(f"Missing plan file: {plan_json}")

lyric_candidates = []
if lyrics_dir.exists():
    lyric_candidates = sorted(
        [p for p in lyrics_dir.rglob("*") if p.suffix.lower() in {".txt", ".lrc", ".srt"}],
        key=lambda p: p.stat().st_mtime,
        reverse=True,
    )

print("Lyrics found:", len(lyric_candidates))
for p in lyric_candidates[:10]:
    print(" -", p)

if not lyric_candidates:
    raise FileNotFoundError("No lyrics file found in inputs\\lyrics. Put the Holy Cheeks lyrics text file there first.")

lyric_path = lyric_candidates[0]

plan = json.loads(plan_json.read_text(encoding="utf-8-sig"))
results = plan.get("results", [])
if not results:
    raise ValueError("Input plan has no results.")

first_scene = results[0].get("scene", {}) or {}
scene_start = float(first_scene.get("start", 0.0) or 0.0)

print("Using lyrics:", lyric_path)
print("Scene start offset:", scene_start)
print("Injecting true ASMO directives...")

patched = inject_asmo_into_ltx_run_plan(
    plan_json=plan_json,
    lyric_path=lyric_path,
    output_json=output_json,
    max_events_per_scene=8,
    start_offset_seconds=scene_start,
)

statuses = []
for item in patched.get("results", []):
    statuses.append({
        "clip_index": item.get("clip_index"),
        "asmo_injection_status": item.get("asmo_injection_status"),
        "asmo_motion_event_count": item.get("asmo_motion_event_count"),
        "asmo_start_offset_seconds": item.get("asmo_start_offset_seconds"),
    })

print(json.dumps({
    "status": "complete",
    "output_plan": str(output_json),
    "scene_count": len(patched.get("results", [])),
    "asmo_statuses": statuses,
}, indent=2))
