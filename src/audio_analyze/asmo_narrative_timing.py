import json
import sys
from pathlib import Path


def evaluate_narrative_timing(data):
    """Validate visible-event causality, not beat synchronization."""
    failures = []
    unknown = []
    events = data.get("events", {})

    def fail(code, detail):
        failures.append({"code": code, "detail": detail})

    def need(detail):
        if detail not in unknown:
            unknown.append(detail)

    def span(name, obj):
        if not isinstance(obj, dict):
            need(f"{name}: no visual observation")
            return None
        if obj.get("visibly_complete") is False:
            fail("EVENT_INCOMPLETE", name)
        elif obj.get("visibly_complete") is not True:
            need(f"{name}: completion unverified")
        try:
            start = float(obj["start"])
            end = float(obj["end"])
        except (KeyError, TypeError, ValueError):
            need(f"{name}: start/end timestamps missing")
            return None
        if start > end:
            fail("INVALID_TIMESTAMPS", name)
        return (start, end)

    def require_flag(obj, name, field):
        value = obj.get(field) if isinstance(obj, dict) else None
        if value is False:
            fail("VISUAL_REQUIREMENT_FAILED", f"{name}: {field}")
        elif value is not True:
            need(f"{name}: {field} not verified")

    fire = events.get("fire_down")
    night = events.get("night_advanced")
    tree = events.get("trail_to_tree")
    table = events.get("trail_to_refreshments")
    cookie = events.get("cookies_consumed")
    coffee = events.get("coffee_consumed")
    ret = events.get("trail_to_fireplace")
    exit_event = events.get("exit_fireplace")

    fire_time = span("fire_down", fire)
    night_time = span("night_advanced", night)
    tree_time = span("trail_to_tree", tree)
    table_time = span("trail_to_refreshments", table)
    cookie_time = span("cookies_consumed", cookie)
    coffee_time = span("coffee_consumed", coffee)
    return_time = span("trail_to_fireplace", ret)
    exit_time = span("exit_fireplace", exit_event)

    require_flag(fire, "fire_down", "flames_faded")
    require_flag(night, "night_advanced", "moon_lowered")
    require_flag(night, "night_advanced", "exterior_changed")
    require_flag(cookie, "cookies_consumed", "consumed")
    require_flag(coffee, "coffee_consumed", "consumed")

    if data.get("fire_hot_at_first_footprint") is True:
        fail(
            "EARLY_FOOTPRINT_FIRE",
            "First footprint appeared while fire was still strong"
        )

    if data.get("early_night_at_first_footprint") is True:
        fail(
            "EARLY_FOOTPRINT_NIGHT",
            "First footprint preceded visible night advancement"
        )

    def before(label, earlier, later):
        if earlier is not None and later is not None:
            if later[0] < earlier[1]:
                fail(
                    "PREMATURE_TRANSITION",
                    f"{label}: next event began before previous finished"
                )

    before("fire -> night", fire_time, night_time)
    before("night -> footprints", night_time, tree_time)

    gifts = data.get("gifts")
    gift_times = []
    if not isinstance(gifts, list) or not gifts:
        need("Presents: individual gift appearances not documented")
    else:
        for i, gift in enumerate(gifts, 1):
            t = span(f"gift_{i}", gift)
            if t is not None:
                gift_times.append(t)
            require_flag(gift, f"gift_{i}", "arrived_individually")

        if gift_times:
            before("tree -> first gift", tree_time, gift_times[0])
            for i in range(len(gift_times) - 1):
                before(
                    f"gift {i+1} -> gift {i+2}",
                    gift_times[i],
                    gift_times[i+1]
                )
            before("last gift -> refreshments trail",
                   gift_times[-1], table_time)

    before("trail -> cookies", table_time, cookie_time)
    before("trail -> coffee", table_time, coffee_time)
    before("cookies -> return", cookie_time, return_time)
    before("coffee -> return", coffee_time, return_time)
    before("return -> exit", return_time, exit_time)

    def check_steps(name, obj, expected_from, expected_to):
        if not isinstance(obj, dict):
            return
        if obj.get("from") != expected_from or obj.get("to") != expected_to:
            need(f"{name}: route direction not verified")

        steps = obj.get("steps")
        if not isinstance(steps, list) or len(steps) < 2:
            need(f"{name}: insufficient individually observed steps")
            return

        previous = None
        for i, step in enumerate(steps):
            try:
                foot = step["foot"].upper()
                t = float(step["time"])
                progress = float(step["progress"])
            except (KeyError, TypeError, ValueError, AttributeError):
                need(f"{name}: incomplete step evidence")
                return

            if foot not in ("L", "R"):
                fail("INVALID_GAIT", f"{name}: unknown foot {i+1}")
            if previous is not None:
                pf, pt, pp = previous
                if foot == pf:
                    fail("INVALID_GAIT", f"{name}: repeated same foot")
                if t <= pt:
                    fail("SIMULTANEOUS_STEPS", f"{name}: nonsequential steps")
                if progress <= pp:
                    fail("INVALID_DIRECTION", f"{name}: no forward progression")
            previous = (foot, t, progress)

    check_steps("trail_to_tree", tree, "fireplace", "tree")
    check_steps("trail_to_refreshments", table, "tree", "refreshments")
    check_steps("trail_to_fireplace", ret, "refreshments", "fireplace")

    seam = data.get("loop_seam_verified")
    if seam is False:
        fail("LOOP_SEAM_FAILED", "Last-to-first frame transition fails")
    elif seam is not True:
        need("Loop boundary not verified")

    decision = (
        "reject" if failures else
        "review_required" if unknown else
        "pass"
    )

    return {
        "clip": data.get("clip"),
        "decision": decision,
        "beat_sync_applied": False,
        "violations": failures,
        "unverified": unknown
    }


def example_complete():
    def event(a, b, **kw):
        return {
            "start": a, "end": b,
            "visibly_complete": True, **kw
        }

    def trail(a, b, source, destination):
        return event(
            a, b,
            **{
                "from": source,
                "to": destination,
                "steps": [
                    {"foot": "L", "time": a, "progress": 0.1},
                    {"foot": "R", "time": (a+b)/2, "progress": 0.5},
                    {"foot": "L", "time": b, "progress": 0.9}
                ]
            }
        )

    return {
        "clip": "synthetic_correct_sequence",
        "loop_seam_verified": True,
        "events": {
            "fire_down": event(0, 1, flames_faded=True),
            "night_advanced": event(
                1.1, 2.0, moon_lowered=True, exterior_changed=True
            ),
            "trail_to_tree": trail(2.1, 4, "fireplace", "tree"),
            "trail_to_refreshments": trail(
                5.1, 6, "tree", "refreshments"
            ),
            "cookies_consumed": event(6.1, 7, consumed=True),
            "coffee_consumed": event(6.2, 7.1, consumed=True),
            "trail_to_fireplace": trail(
                7.2, 8.5, "refreshments", "fireplace"
            ),
            "exit_fireplace": event(8.6, 9)
        },
        "gifts": [
            event(4.1, 4.4, arrived_individually=True),
            event(4.5, 4.8, arrived_individually=True)
        ]
    }


def self_test():
    import copy

    good = example_complete()
    assert evaluate_narrative_timing(good)["decision"] == "pass"

    early = copy.deepcopy(good)
    early["events"]["trail_to_tree"]["start"] = 0.5
    assert any(
        e["code"] == "PREMATURE_TRANSITION"
        for e in evaluate_narrative_timing(early)["violations"]
    )

    gifts_overlap = copy.deepcopy(good)
    gifts_overlap["gifts"][1]["start"] = 4.2
    assert evaluate_narrative_timing(gifts_overlap)["decision"] == "reject"

    bad_gait = copy.deepcopy(good)
    bad_gait["events"]["trail_to_tree"]["steps"][1]["foot"] = "L"
    assert any(
        e["code"] == "INVALID_GAIT"
        for e in evaluate_narrative_timing(bad_gait)["violations"]
    )

    clip_d = {
        "clip": "D",
        "fire_hot_at_first_footprint": True,
        "early_night_at_first_footprint": True
    }
    assert evaluate_narrative_timing(clip_d)["decision"] == "reject"

    clip_c = {"clip": "C"}
    assert evaluate_narrative_timing(clip_c)["decision"] == "review_required"

    print("PASS: correct sequence")
    print("PASS: premature transitions rejected")
    print("PASS: overlapping presents rejected")
    print("PASS: invalid gait rejected")
    print("PASS: Clip D documented timing violation rejected")
    print("PASS: Clip C remains review_required")
    print("6 regression checks passed")


if __name__ == "__main__":
    if len(sys.argv) == 2 and sys.argv[1] == "--self-test":
        self_test()
    elif len(sys.argv) == 2:
        data = json.loads(Path(sys.argv[1]).read_text(encoding="utf-8-sig"))
        print(json.dumps(evaluate_narrative_timing(data), indent=2))
    else:
        print("Usage: asmo_narrative_timing.py --self-test | evidence.json")
        sys.exit(2)