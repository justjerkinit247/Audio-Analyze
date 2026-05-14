from __future__ import annotations

from pathlib import Path
from datetime import datetime, timezone
import argparse
import json
import shutil
import uuid


DEFAULT_STATE_ROOT = "outputs/ltx_video_run/_state"


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def make_session_id() -> str:
    stamp = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S_utc")
    return f"live_{stamp}_{uuid.uuid4().hex[:6]}"


def read_json(path: Path, default=None):
    path = Path(path)
    if not path.exists():
        return default
    return json.loads(path.read_text(encoding="utf-8-sig"))


def write_json(path: Path, data) -> Path:
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, indent=2), encoding="utf-8")
    return path


def append_jsonl(path: Path, row: dict) -> Path:
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8") as f:
        f.write(json.dumps(row, ensure_ascii=False) + "\n")
    return path


def summarize_active_session(active_dir: Path) -> dict:
    manifest = read_json(active_dir / "manifest.json", default={}) or {}
    scene_dir = active_dir / "scene_returns"
    assembler_dir = active_dir / "assembler"
    feedback_dir = active_dir / "feedback"

    scene_results = []
    if scene_dir.exists():
        for path in sorted(scene_dir.glob("scene_*_result.json")):
            item = read_json(path, default={}) or {}
            scene_results.append({
                "file": path.name,
                "clip_index": item.get("clip_index"),
                "status": item.get("status"),
                "failure_class": item.get("failure_class"),
                "retry_recommended": item.get("retry_recommended"),
                "downloaded_mp4": item.get("downloaded_mp4"),
                "scene_audio_format": item.get("scene_audio_format"),
                "error": item.get("error"),
            })

    assembly_attempts = 0
    attempt_path = assembler_dir / "assembly_attempts.jsonl"
    if attempt_path.exists():
        assembly_attempts = sum(1 for _ in attempt_path.open("r", encoding="utf-8"))

    latest_feedback = read_json(feedback_dir / "feedback_packet.json", default=None)

    return {
        "session_id": manifest.get("session_id"),
        "status": manifest.get("status"),
        "created_at_utc": manifest.get("created_at_utc"),
        "summarized_at_utc": utc_now(),
        "scene_count": len(scene_results),
        "successful_scenes": sum(1 for r in scene_results if r.get("status") not in {None, "failed"}),
        "failed_scenes": sum(1 for r in scene_results if r.get("status") == "failed"),
        "assembly_attempts": assembly_attempts,
        "scene_results": scene_results,
        "latest_feedback_summary": latest_feedback.get("summary") if isinstance(latest_feedback, dict) else None,
    }


def ensure_state_dirs(state_root: Path) -> None:
    for name in ("active", "previous", "summaries", "policy", "locks"):
        (state_root / name).mkdir(parents=True, exist_ok=True)


def rotate_for_new_live_session(state_root: Path, keep_previous: bool = True) -> dict:
    state_root = Path(state_root)
    ensure_state_dirs(state_root)

    active = state_root / "active"
    previous = state_root / "previous"
    summaries = state_root / "summaries"

    if (active / "manifest.json").exists():
        summary = summarize_active_session(active)
        append_jsonl(summaries / "run_summaries.jsonl", summary)
        write_json(summaries / "latest_summary.json", summary)

        if previous.exists():
            shutil.rmtree(previous)
        if keep_previous:
            shutil.move(str(active), str(previous))
        else:
            shutil.rmtree(active)

    active.mkdir(parents=True, exist_ok=True)
    for sub in ("scene_returns", "assembler", "review", "features", "feedback"):
        (active / sub).mkdir(parents=True, exist_ok=True)

    manifest = {
        "session_id": make_session_id(),
        "status": "LIVE_SESSION_STARTED",
        "created_at_utc": utc_now(),
        "state_policy": {
            "raw_active_sessions_to_keep": 1,
            "raw_previous_sessions_to_keep": 1 if keep_previous else 0,
            "summary_history": "jsonl_compact",
            "assembler_may_read": True,
            "assembler_may_delete": False,
            "delete_raw_older_than_previous": True,
            "never_delete_downloaded_clips": True,
            "never_delete_final_assemblies": True,
        },
    }
    write_json(active / "manifest.json", manifest)

    (active / "README_TEMP_STATE.txt").write_text(
        "Temporary active LTX live-session state.\n"
        "Assembler may read this folder and append attempt journal entries.\n"
        "This active state rotates to previous when the next live session starts.\n",
        encoding="utf-8",
    )
    return manifest


def get_active_manifest(state_root: Path) -> dict:
    state_root = Path(state_root)
    manifest_path = state_root / "active" / "manifest.json"
    if not manifest_path.exists():
        ensure_state_dirs(state_root)
        manifest = {
            "session_id": "manual_active_" + uuid.uuid4().hex[:6],
            "status": "MANUAL_ACTIVE_STATE",
            "created_at_utc": utc_now(),
        }
        for sub in ("scene_returns", "assembler", "review", "features", "feedback"):
            (state_root / "active" / sub).mkdir(parents=True, exist_ok=True)
        write_json(manifest_path, manifest)
        return manifest
    return read_json(manifest_path, default={}) or {}


def update_active_manifest(state_root: Path, **updates) -> dict:
    state_root = Path(state_root)
    manifest = get_active_manifest(state_root)
    manifest.update(updates)
    manifest["updated_at_utc"] = utc_now()
    write_json(state_root / "active" / "manifest.json", manifest)
    return manifest


def ingest_scene_result(state_root: Path, result_json: Path) -> Path:
    state_root = Path(state_root)
    get_active_manifest(state_root)
    result_json = Path(result_json)
    data = read_json(result_json, default={}) or {}
    clip_index = int(data.get("clip_index") or 0)
    name = f"scene_{clip_index:02d}_result.json" if clip_index else result_json.name
    out = state_root / "active" / "scene_returns" / name
    write_json(out, data)

    request = {
        "clip_index": data.get("clip_index"),
        "model": data.get("model"),
        "guidance_scale": data.get("guidance_scale"),
        "resolution": data.get("resolution"),
        "seed_image_used": data.get("seed_image_used"),
        "source_audio_path": data.get("source_audio_path"),
        "scene": data.get("scene"),
        "prompt_text": data.get("prompt_text"),
    }
    write_json(state_root / "active" / "scene_returns" / name.replace("_result.json", "_request.json"), request)
    return out


def ingest_result_folder(state_root: Path, folder: Path) -> list[str]:
    folder = Path(folder)
    copied = []
    for path in sorted(folder.glob("scene_*_result.json")):
        copied.append(str(ingest_scene_result(state_root, path)))
    return copied


def append_assembly_attempt(state_root: Path, attempt: dict) -> Path:
    state_root = Path(state_root)
    manifest = get_active_manifest(state_root)
    attempt = dict(attempt)
    attempt.setdefault("session_id", manifest.get("session_id"))
    attempt.setdefault("created_at_utc", utc_now())
    path = state_root / "active" / "assembler" / "assembly_attempts.jsonl"
    append_jsonl(path, attempt)
    write_json(state_root / "active" / "assembler" / "latest_assembly_report.json", attempt)
    update_active_manifest(state_root, status="ASSEMBLY_TESTING")
    return path


def status(state_root: Path) -> dict:
    state_root = Path(state_root)
    active_manifest = read_json(state_root / "active" / "manifest.json", default=None)
    previous_manifest = read_json(state_root / "previous" / "manifest.json", default=None)
    latest_summary = read_json(state_root / "summaries" / "latest_summary.json", default=None)
    attempts_path = state_root / "active" / "assembler" / "assembly_attempts.jsonl"
    attempts = sum(1 for _ in attempts_path.open("r", encoding="utf-8")) if attempts_path.exists() else 0
    scene_returns = len(list((state_root / "active" / "scene_returns").glob("scene_*_result.json"))) if (state_root / "active" / "scene_returns").exists() else 0
    return {
        "active": active_manifest,
        "previous": previous_manifest,
        "latest_summary": latest_summary,
        "active_scene_returns": scene_returns,
        "active_assembly_attempts": attempts,
    }


def main():
    parser = argparse.ArgumentParser(description="Manage LTX run state.")
    sub = parser.add_subparsers(dest="command", required=True)

    p_start = sub.add_parser("start-live-session")
    p_start.add_argument("--state-root", default=DEFAULT_STATE_ROOT)
    p_start.add_argument("--no-previous", action="store_true")

    p_ingest = sub.add_parser("ingest-results")
    p_ingest.add_argument("--state-root", default=DEFAULT_STATE_ROOT)
    p_ingest.add_argument("--results-dir", default="outputs/ltx_video_run")

    p_status = sub.add_parser("status")
    p_status.add_argument("--state-root", default=DEFAULT_STATE_ROOT)

    args = parser.parse_args()

    if args.command == "start-live-session":
        manifest = rotate_for_new_live_session(Path(args.state_root), keep_previous=not args.no_previous)
        print(json.dumps(manifest, indent=2))
    elif args.command == "ingest-results":
        copied = ingest_result_folder(Path(args.state_root), Path(args.results_dir))
        print(json.dumps({"copied": copied}, indent=2))
    elif args.command == "status":
        print(json.dumps(status(Path(args.state_root)), indent=2))


if __name__ == "__main__":
    main()
