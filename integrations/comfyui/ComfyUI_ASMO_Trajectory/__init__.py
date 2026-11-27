import json
import math

VERSION = "1.0.0"

DEFAULT_PLAN = json.dumps({
    "tracks": [{
        "id": "subject_01",
        "easing": "smoothstep",
        "keyframes": [
            {"t": 0.0, "x": 0.30, "y": 0.50},
            {"t": 1.0, "x": 0.70, "y": 0.50}
        ]
    }]
}, indent=2)


def unit(value, label):
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise ValueError(f"{label}: expected a number")
    value = float(value)
    if not math.isfinite(value) or not 0 <= value <= 1:
        raise ValueError(f"{label}: must be between 0 and 1")
    return value


def validate_tracks(tracks, width, height, frames):
    if not isinstance(tracks, list) or not tracks:
        raise ValueError("No motion tracks supplied")

    for index, track in enumerate(tracks):
        if not isinstance(track, list) or len(track) != frames:
            raise ValueError(
                f"Track {index}: expected {frames} samples"
            )

        for point in track:
            x, y = point["x"], point["y"]

            if not (
                isinstance(x, (int, float))
                and isinstance(y, (int, float))
                and 0 <= x < width
                and 0 <= y < height
            ):
                raise ValueError(
                    f"Track {index}: coordinate outside canvas: {point}"
                )

    return tracks


def compile_tracks(plan, width, height, frames):
    if width < 2 or height < 2:
        raise ValueError("Invalid image dimensions")

    if frames < 9 or (frames - 1) % 8:
        raise ValueError("LTX frame count must satisfy 8n+1")

    data = json.loads(plan) if isinstance(plan, str) else plan
    definitions = data["tracks"]

    if not isinstance(definitions, list) or not definitions:
        raise ValueError("At least one track is required")

    tracks = []

    for definition in definitions:
        easing = definition.get("easing", "linear")

        if easing not in ("linear", "smoothstep"):
            raise ValueError(f"Unsupported easing: {easing}")

        keys = [
            {
                axis: unit(k[axis], axis)
                for axis in ("t", "x", "y")
            }
            for k in definition["keyframes"]
        ]

        if len(keys) < 2:
            raise ValueError("At least two keyframes required")

        if keys[0]["t"] != 0 or keys[-1]["t"] != 1:
            raise ValueError("Keyframes must span t=0 to t=1")

        if any(
            b["t"] <= a["t"]
            for a, b in zip(keys, keys[1:])
        ):
            raise ValueError("Keyframe times must strictly increase")

        track = []
        segment = 0

        for frame in range(frames):
            t = frame / (frames - 1)

            while (
                segment < len(keys) - 2
                and t > keys[segment + 1]["t"]
            ):
                segment += 1

            a = keys[segment]
            b = keys[segment + 1]

            u = (t - a["t"]) / (b["t"] - a["t"])
            u = max(0.0, min(1.0, u))

            if easing == "smoothstep":
                u = u * u * (3 - 2 * u)

            x = a["x"] + (b["x"] - a["x"]) * u
            y = a["y"] + (b["y"] - a["y"]) * u

            track.append({
                "x": round(x * (width - 1)),
                "y": round(y * (height - 1))
            })

        tracks.append(track)

    return validate_tracks(tracks, width, height, frames)


def make_overlay(image, tracks):
    import numpy as np
    import torch
    from PIL import Image, ImageDraw

    array = (
        image[0, :, :, :3]
        .detach().cpu().float().clamp(0, 1).numpy() * 255
    ).astype(np.uint8)

    canvas = Image.fromarray(array)
    draw = ImageDraw.Draw(canvas)

    colors = [
        (30, 255, 160),
        (255, 190, 30),
        (70, 190, 255),
        (255, 70, 190)
    ]

    radius = max(3, min(canvas.size) // 100)

    for index, track in enumerate(tracks):
        color = colors[index % len(colors)]
        points = [(p["x"], p["y"]) for p in track]

        draw.line(points, fill=color, width=2)

        for x, y in (points[0], points[-1]):
            draw.ellipse(
                (x-radius, y-radius, x+radius, y+radius),
                fill=color
            )

        draw.text(
            points[0], f"START {index+1}",
            fill=color, stroke_width=1,
            stroke_fill=(0, 0, 0)
        )

        draw.text(
            points[-1], f"END {index+1}",
            fill=color, stroke_width=1,
            stroke_fill=(0, 0, 0)
        )

    return torch.from_numpy(
        np.array(canvas).astype(np.float32) / 255.0
    ).unsqueeze(0)


class ASMOAutomaticTrajectoryV1:

    @classmethod
    def INPUT_TYPES(cls):
        return {
            "required": {
                "image": ("IMAGE",),
                "frames": (
                    "INT",
                    {"default": 97, "min": 9, "max": 10001, "step": 8}
                ),
                "mode": (["automatic", "manual"],),
                "motion_plan": (
                    "STRING",
                    {"default": DEFAULT_PLAN, "multiline": True}
                )
            },
            "optional": {
                "manual_tracks": (
                    "STRING",
                    {"default": "[]", "forceInput": True}
                )
            }
        }

    RETURN_TYPES = ("STRING", "IMAGE")
    RETURN_NAMES = ("tracks", "trajectory_preview")
    FUNCTION = "execute"
    CATEGORY = "GTRG/ASMO"

    def execute(
        self, image, frames, mode,
        motion_plan, manual_tracks="[]"
    ):
        height = int(image.shape[1])
        width = int(image.shape[2])

        if frames < 9 or (frames - 1) % 8:
            raise ValueError("LTX frame count must satisfy 8n+1")

        if mode == "manual":
            tracks = validate_tracks(
                json.loads(manual_tracks),
                width, height, frames
            )
        else:
            tracks = compile_tracks(
                motion_plan, width, height, frames
            )

        print(
            f"[ASMO Trajectory {VERSION}] "
            f"{width}x{height}, {frames} frames, "
            f"{len(tracks)} tracks, mode={mode}"
        )

        print("[ASMO] Coordinate validation: PASS")

        return (
            json.dumps(tracks),
            make_overlay(image, tracks)
        )


NODE_CLASS_MAPPINGS = {
    "ASMOAutomaticTrajectoryV1": ASMOAutomaticTrajectoryV1
}

NODE_DISPLAY_NAME_MAPPINGS = {
    "ASMOAutomaticTrajectoryV1":
        "ASMO Automatic Trajectory V1"
}


def self_test():
    for width, height in [(320, 320), (288, 512), (512, 896)]:
        for frames in (9, 33, 97, 121):
            tracks = compile_tracks(
                DEFAULT_PLAN, width, height, frames
            )
            assert len(tracks[0]) == frames
            assert tracks[0][0]["x"] == round(.30 * (width-1))
            assert tracks[0][-1]["x"] == round(.70 * (width-1))
            print(
                f"PASS: {width}x{height}, "
                f"{frames} frames"
            )

    invalid = json.loads(DEFAULT_PLAN)
    invalid["tracks"][0]["keyframes"][0]["x"] = 1.2

    try:
        compile_tracks(invalid, 320, 320, 97)
    except ValueError:
        print("PASS: Invalid coordinates rejected")
    else:
        raise AssertionError("Out-of-bounds test failed")

    try:
        compile_tracks(DEFAULT_PLAN, 320, 320, 100)
    except ValueError:
        print("PASS: Invalid LTX frame count rejected")
    else:
        raise AssertionError("Frame validation failed")

    print("ASMO TRAJECTORY SELF-TEST: PASS")


if __name__ == "__main__":
    self_test()