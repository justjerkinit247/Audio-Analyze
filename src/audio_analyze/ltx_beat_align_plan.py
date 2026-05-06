from pathlib import Path
import argparse
import json


DEFAULT_PLAN = "outputs\\ltx_video_run\\holy_cheeks_ltx_plan.json"
DEFAULT_REPORT = "outputs\\ltx_video_run\\beat_alignment_report.json"
MIN_LTX_AUDIO_SECONDS = 2.0
MAX_LTX_AUDIO_SECONDS = 20.0


def read_json(path):
    return json.loads(Path(path).read_text(encoding="utf-8-sig"))


def write_json(path, data):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, indent=2), encoding="utf-8")


def get_tempo_bpm(plan, override_bpm=None):
    if override_bpm:
        return float(override_bpm)
    tempo = (plan.get("analysis") or {}).get("tempo_bpm")
    if not tempo:
        raise RuntimeError("No tempo_bpm found in plan analysis. Rebuild the plan or pass --bpm manually.")
    return float(tempo)


def snap_duration_to_beats(duration, beat_seconds, min_seconds=MIN_LTX_AUDIO_SECONDS, max_seconds=MAX_LTX_AUDIO_SECONDS):
    duration = float(duration)
    beats = max(1, round(duration / beat_seconds))
    snapped = beats * beat_seconds

    if snapped < min_seconds:
        beats = max(1, round(min_seconds / beat_seconds))
        snapped = beats * beat_seconds
    if snapped > max_seconds:
        beats = max(1, round(max_seconds / beat_seconds))
        snapped = beats * beat_seconds

    return beats, snapped


def beat_align_plan(plan_json=DEFAULT_PLAN, output_json=None, report_json=DEFAULT_REPORT, bpm=None, beat_offset_seconds=0.0):
    plan_path = Path(plan_json)
    plan = read_json(plan_path)
    tempo_bpm = get_tempo_bpm(plan, override_bpm=bpm)
    beat_seconds = 60.0 / tempo_bpm
    beat_offset_seconds = float(beat_offset_seconds or 0.0)

    cursor = beat_offset_seconds
    rows = []

    for item in plan.get("results", []):
        scene = item.get("scene", {})
        original_start = float(scene.get("start", cursor))
        original_duration = float(scene.get("duration", 0.0))
        beats, snapped_duration = snap_duration_to_beats(original_duration, beat_seconds)
        new_start = cursor
        new_end = new_start + snapped_duration

        scene["original_start"] = round(original_start, 6)
        scene["original_duration"] = round(original_duration, 6)
        scene["beat_aligned"] = True
        scene["beat_count"] = beats
        scene["beat_seconds"] = round(beat_seconds, 6)
        scene["start"] = round(new_start, 6)
        scene["end"] = round(new_end, 6)
        scene["duration"] = round(snapped_duration, 6)

        item["scene"] = scene

        rows.append({
            "clip_index": item.get("clip_index"),
            "original_start": round(original_start, 3),
            "original_duration": round(original_duration, 3),
            "beat_count": beats,
            "new_start": round(new_start, 3),
            "new_end": round(new_end, 3),
            "new_duration": round(snapped_duration, 3),
            "duration_delta": round(snapped_duration - original_duration, 3),
        })

        cursor = new_end

    plan["beat_alignment"] = {
        "enabled": True,
        "tempo_bpm": round(tempo_bpm, 6),
        "beat_seconds": round(beat_seconds, 6),
        "beat_offset_seconds": beat_offset_seconds,
        "scene_count": len(plan.get("results", [])),
        "final_video_duration": round(cursor, 6),
        "method": "Each scene duration snapped to the nearest whole-beat duration, then scene starts are rebuilt cumulatively so every cut lands on the beat grid.",
        "rows": rows,
    }

    destination = output_json or plan_json
    write_json(destination, plan)
    if report_json:
        write_json(report_json, plan["beat_alignment"])
    return plan


def main():
    parser = argparse.ArgumentParser(description="Snap LTX plan scene durations to the detected BPM beat grid before assembly.")
    parser.add_argument("--plan-json", default=DEFAULT_PLAN)
    parser.add_argument("--output", default=None, help="Optional output plan path. If omitted, rewrites the plan in place.")
    parser.add_argument("--report-json", default=DEFAULT_REPORT)
    parser.add_argument("--bpm", type=float, default=None, help="Optional manual BPM override.")
    parser.add_argument("--beat-offset-seconds", type=float, default=0.0, help="Optional offset for the first beat/cut grid.")
    args = parser.parse_args()

    plan = beat_align_plan(
        plan_json=args.plan_json,
        output_json=args.output,
        report_json=args.report_json,
        bpm=args.bpm,
        beat_offset_seconds=args.beat_offset_seconds,
    )
    info = plan.get("beat_alignment", {})
    print("LTX beat-aligned plan complete.")
    print(f"Tempo BPM: {info.get('tempo_bpm')}")
    print(f"Beat length: {info.get('beat_seconds')} seconds")
    print(f"Scene count: {info.get('scene_count')}")
    print(f"Final beat-aligned duration: {info.get('final_video_duration')} seconds")
    for row in info.get("rows", []):
        print(
            "Scene {clip_index:02d}: {beat_count} beats, {new_start:.3f}s -> {new_end:.3f}s "
            "({new_duration:.3f}s, delta {duration_delta:+.3f}s)".format(**row)
        )
    if args.report_json:
        print(f"Report: {Path(args.report_json).resolve()}")


if __name__ == "__main__":
    main()
