from __future__ import annotations

import argparse
import json
import re
from datetime import datetime, timezone
from pathlib import Path
from typing import Iterable, Any


NEGATIVE_MARKER = "[NEGATIVE_PROMPT]"

DEFAULT_ISSUE_NEGATIVE_TERMS: dict[str, list[str]] = {
    "generation_failed": [
        "incomplete generation",
        "stalled motion",
        "broken temporal continuity",
    ],
    "weak_beat_sync": [
        "off-beat motion",
        "rhythm drift",
        "unsynced body movement",
    ],
    "motion_intent_mismatch": [
        "motion drift",
        "unclear subject movement",
        "wrong motion direction",
    ],
    "camera_intent_mismatch": [
        "chaotic camera movement",
        "camera drift away from subject",
        "conflicting camera motion",
    ],
    "prompt_obedience_low": [
        "ignored prompt instructions",
        "unrelated visual elements",
        "scene concept drift",
    ],
    "prompt_too_long": [
        "overloaded prompt interpretation",
        "conflicting details",
        "visual clutter",
    ],
    "conflicting_directives_detected": [
        "conflicting motion directives",
        "conflicting camera directives",
        "continuity breaks",
    ],
    "motion_overload": [
        "overactive motion",
        "jittery motion",
        "unreadable movement",
    ],
    "camera_overload": [
        "overactive camera",
        "rapid camera swings",
        "unreadable framing",
    ],
    "seed_drift": [
        "seed image drift",
        "changed subject identity",
        "changed background",
        "changed framing",
    ],
}

SUBJECT_NEGATIVE_TERMS: dict[str, list[str]] = {
    "duck": ["malformed wings", "duplicate wings", "broken beak", "feather smear"],
    "bird": ["malformed wings", "duplicate wings", "broken beak", "feather smear"],
    "wing": ["malformed wings", "duplicate wings", "feather smear"],
    "wings": ["malformed wings", "duplicate wings", "feather smear"],
}

BASELINE_NEGATIVE_TERMS = [
    "blurry motion",
    "jittery motion",
    "chaotic camera movement",
    "warped background",
    "distorted subject",
    "duplicate subject",
    "low detail",
    "flicker",
]


def read_json(path: Path, default=None):
    path = Path(path)
    if not path.exists():
        return default
    return json.loads(path.read_text(encoding="utf-8-sig"))


def write_json(path: Path, data) -> Path:
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, indent=2, ensure_ascii=False), encoding="utf-8")
    return path


def append_jsonl(path: Path, row: dict) -> Path:
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8") as handle:
        handle.write(json.dumps(row, ensure_ascii=False) + "\n")
    return path


def normalize_term(term: Any) -> str:
    term = re.sub(r"\s+", " ", str(term or "")).strip().strip(",")
    return term.lower()


def unique_terms(terms: Iterable[Any]) -> list[str]:
    seen = set()
    result = []
    for raw in terms:
        term = normalize_term(raw)
        if not term or term in seen:
            continue
        seen.add(term)
        result.append(term)
    return result


def memory_root(state_root: Path) -> Path:
    root = Path(state_root) / "memory"
    root.mkdir(parents=True, exist_ok=True)
    return root


def memory_path(state_root: Path) -> Path:
    return memory_root(state_root) / "asmo_negative_prompt_memory.json"


def ledger_path(state_root: Path) -> Path:
    return memory_root(state_root) / "negative_prompt_ledger.jsonl"


def default_memory() -> dict:
    return {
        "version": 1,
        "created_at_utc": datetime.now(timezone.utc).isoformat(),
        "updated_at_utc": None,
        "baseline_terms": list(BASELINE_NEGATIVE_TERMS),
        "issue_terms": json.loads(json.dumps(DEFAULT_ISSUE_NEGATIVE_TERMS)),
        "term_counts": {},
        "issue_counts": {},
        "scene_terms": {},
        "last_session_id": None,
    }


def load_negative_prompt_memory(state_root: Path) -> dict:
    path = memory_path(state_root)
    existing = read_json(path, default=None)
    if existing:
        return existing
    memory = default_memory()
    write_json(path, memory)
    ledger_path(state_root).touch(exist_ok=True)
    return memory


def subject_terms_from_hint(scene_hint: str) -> list[str]:
    tokens = set(re.split(r"\W+", str(scene_hint or "").lower()))
    terms: list[str] = []
    for token, mapped in SUBJECT_NEGATIVE_TERMS.items():
        if token in tokens:
            terms.extend(mapped)
    return unique_terms(terms)


def terms_for_issues(issues: Iterable[str], memory: dict | None = None) -> list[str]:
    source = (memory or {}).get("issue_terms") or DEFAULT_ISSUE_NEGATIVE_TERMS
    terms: list[str] = []
    for issue in issues:
        terms.extend(source.get(str(issue), []))
    return unique_terms(terms)


def extract_feedback_terms(feedback_packet: dict, memory: dict | None = None) -> dict:
    scene_rows = []
    global_terms: list[str] = []
    for scene in feedback_packet.get("scene_feedback", []) or []:
        issues = [str(issue) for issue in scene.get("detected_issues", []) if str(issue)]
        terms = terms_for_issues(issues, memory=memory)
        scene_id = scene.get("scene_id")
        if terms:
            scene_rows.append(
                {
                    "scene_id": scene_id,
                    "issues": issues,
                    "terms": terms,
                    "scores": scene.get("scores", {}),
                }
            )
            global_terms.extend(terms)
    return {
        "session_id": feedback_packet.get("session_id"),
        "created_at_utc": datetime.now(timezone.utc).isoformat(),
        "global_terms": unique_terms(global_terms),
        "scene_terms": scene_rows,
    }


def update_negative_prompt_memory_from_feedback(state_root: Path, feedback_packet: dict | None = None) -> dict:
    state_root = Path(state_root)
    memory = load_negative_prompt_memory(state_root)
    if feedback_packet is None:
        feedback_packet = read_json(state_root / "active" / "feedback" / "feedback_packet.json", default={}) or {}

    extracted = extract_feedback_terms(feedback_packet, memory=memory)
    now = datetime.now(timezone.utc).isoformat()
    memory["updated_at_utc"] = now
    memory["last_session_id"] = extracted.get("session_id")

    term_counts = memory.setdefault("term_counts", {})
    issue_counts = memory.setdefault("issue_counts", {})
    scene_terms = memory.setdefault("scene_terms", {})

    for term in extracted.get("global_terms", []):
        term_counts[term] = int(term_counts.get(term, 0)) + 1

    for row in extracted.get("scene_terms", []):
        scene_key = str(row.get("scene_id"))
        scene_terms[scene_key] = unique_terms(list(scene_terms.get(scene_key, [])) + row.get("terms", []))
        for issue in row.get("issues", []):
            issue_counts[issue] = int(issue_counts.get(issue, 0)) + 1
        append_jsonl(
            ledger_path(state_root),
            {
                "created_at_utc": now,
                "session_id": extracted.get("session_id"),
                "scene_id": row.get("scene_id"),
                "issues": row.get("issues", []),
                "terms": row.get("terms", []),
                "scores": row.get("scores", {}),
            },
        )

    write_json(memory_path(state_root), memory)
    write_json(state_root / "active" / "feedback" / "asmo_negative_prompt_terms.json", extracted)
    return {
        "status": "complete",
        "memory_path": str(memory_path(state_root)),
        "ledger_path": str(ledger_path(state_root)),
        "global_term_count": len(memory.get("term_counts", {})),
        "scene_count": len(extracted.get("scene_terms", [])),
        "global_terms": extracted.get("global_terms", []),
    }


def ranked_memory_terms(memory: dict, limit: int = 12) -> list[str]:
    counts = memory.get("term_counts", {}) or {}
    ranked = sorted(counts.items(), key=lambda kv: (-int(kv[1]), kv[0]))
    return [term for term, _ in ranked[:limit]]


def terms_for_next_run(state_root: Path, scene_id: int | str | None = None, scene_hint: str = "", limit: int = 24) -> list[str]:
    memory = load_negative_prompt_memory(state_root)
    terms: list[str] = []
    terms.extend(memory.get("baseline_terms", []))
    if scene_id is not None:
        terms.extend((memory.get("scene_terms", {}) or {}).get(str(scene_id), []))
    terms.extend(subject_terms_from_hint(scene_hint))
    terms.extend(ranked_memory_terms(memory, limit=12))
    return unique_terms(terms)[:limit]


def merge_negative_prompt(existing: str, learned_terms: Iterable[str]) -> str:
    existing_terms = [part.strip() for part in str(existing or "").split(",") if part.strip()]
    return ", ".join(unique_terms(existing_terms + list(learned_terms)))


def replace_negative_section(prompt_text: str, negative_prompt: str) -> str:
    prompt_text = str(prompt_text or "")
    if NEGATIVE_MARKER not in prompt_text:
        return prompt_text
    before = prompt_text.split(NEGATIVE_MARKER, 1)[0].rstrip()
    return f"{before}\n\n{NEGATIVE_MARKER}\n{negative_prompt}\n"


def scene_hint_for_item(item: dict) -> str:
    return str(
        item.get("seed_filename_prompt_hint")
        or item.get("filename_hint_expansion", {}).get("scene_hint")
        or item.get("seed_assignment", {}).get("filename_prompt_hint")
        or ""
    )


def apply_negative_memory_to_plan_data(plan: dict, state_root: Path, limit: int = 24) -> dict:
    patched = json.loads(json.dumps(plan))
    records = []
    for item in patched.get("results", []) or []:
        scene_id = item.get("clip_index")
        scene_hint = scene_hint_for_item(item)
        learned_terms = terms_for_next_run(state_root, scene_id=scene_id, scene_hint=scene_hint, limit=limit)
        expansion = item.get("filename_hint_expansion") if isinstance(item.get("filename_hint_expansion"), dict) else None

        old_negative = ""
        if expansion:
            old_negative = expansion.get("negative_prompt", "")
        new_negative = merge_negative_prompt(old_negative, learned_terms)

        if expansion:
            expansion["negative_prompt_before_asmo_memory"] = old_negative
            expansion["negative_prompt"] = new_negative
            if expansion.get("combined_ltx_text") and NEGATIVE_MARKER in expansion["combined_ltx_text"]:
                expansion["combined_ltx_text"] = replace_negative_section(expansion["combined_ltx_text"], new_negative)

        if item.get("prompt_text") and NEGATIVE_MARKER in str(item.get("prompt_text")):
            item["prompt_text"] = replace_negative_section(str(item.get("prompt_text")), new_negative)
        elif learned_terms:
            directive = "ASMO learned negative prompt memory: " + ", ".join(learned_terms)
            item["prompt_text"] = (str(item.get("prompt_text") or "").rstrip() + " " + directive).strip()

        item["asmo_negative_prompt_memory"] = {
            "status": "applied",
            "scene_id": scene_id,
            "terms": learned_terms,
            "negative_prompt": new_negative,
        }
        records.append({"scene_id": scene_id, "term_count": len(learned_terms), "terms": learned_terms})

    patched["asmo_negative_prompt_memory_applied"] = True
    patched["asmo_negative_prompt_memory_records"] = records
    return patched


def apply_negative_memory_to_plan(plan_json: Path, state_root: Path, output: Path, limit: int = 24) -> dict:
    plan = read_json(Path(plan_json), default={}) or {}
    patched = apply_negative_memory_to_plan_data(plan, Path(state_root), limit=limit)
    write_json(Path(output), patched)
    return patched


def main() -> None:
    parser = argparse.ArgumentParser(description="Update/apply ASMO negative prompt memory.")
    sub = parser.add_subparsers(dest="command", required=True)

    p_update = sub.add_parser("update")
    p_update.add_argument("--state-root", default="outputs/ltx_video_run/_state")
    p_update.add_argument("--feedback", default=None)

    p_terms = sub.add_parser("terms")
    p_terms.add_argument("--state-root", default="outputs/ltx_video_run/_state")
    p_terms.add_argument("--scene-id", default=None)
    p_terms.add_argument("--scene-hint", default="")
    p_terms.add_argument("--limit", type=int, default=24)

    p_apply = sub.add_parser("apply-plan")
    p_apply.add_argument("--plan-json", required=True)
    p_apply.add_argument("--state-root", default="outputs/ltx_video_run/_state")
    p_apply.add_argument("--output", required=True)
    p_apply.add_argument("--limit", type=int, default=24)

    args = parser.parse_args()
    if args.command == "update":
        feedback = read_json(Path(args.feedback), default={}) if args.feedback else None
        print(json.dumps(update_negative_prompt_memory_from_feedback(Path(args.state_root), feedback_packet=feedback), indent=2))
    elif args.command == "terms":
        print(json.dumps(terms_for_next_run(Path(args.state_root), scene_id=args.scene_id, scene_hint=args.scene_hint, limit=args.limit), indent=2))
    elif args.command == "apply-plan":
        result = apply_negative_memory_to_plan(Path(args.plan_json), Path(args.state_root), Path(args.output), limit=args.limit)
        print(json.dumps({"status": "complete", "output": str(Path(args.output).resolve()), "scene_count": len(result.get("results", []))}, indent=2))


if __name__ == "__main__":
    main()
