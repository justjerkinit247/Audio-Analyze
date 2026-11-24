"""Frame intervals are half open. Quantize each absolute boundary exactly once."""
from dataclasses import dataclass
from fractions import Fraction


@dataclass(frozen=True)
class Profile:
    checkpoint: str
    modulus: int
    offset: int
    minimum: int
    maximum: int
    spatial_step: int
    tested_fps: tuple
    strategies: tuple
    audio_conditioning: str = "empty joint audio latent; original audio for ASMO timing and export"
    audio_vae: str = "same native checkpoint as video VAE"
    batch_size: int = 1
    continuation_frames: int = 1
    measured_shape: tuple = (288, 512, 57)
    simultaneous_jobs: int = 1
    planner_seconds: tuple = (2, 20)

    def length(self, count):
        if count < 1:
            raise ValueError("Empty scene")
        steps = (max(self.minimum, count) - self.offset + self.modulus - 1) // self.modulus
        result = self.offset + steps * self.modulus
        if result > self.maximum:
            raise ValueError("Scene exceeds native joint A/V latent frame limit")
        return result


LTX = "ltx-2.3-22b-dev-fp8.safetensors"
PROFILES = {LTX: Profile(LTX, 8, 1, 9, 993, 32, (24,), ("last_frame_auto",))}


def nearest(value):
    return int(value + Fraction(1, 2))


def boundaries(durations, fps, sample_rate, profile, overlap=1):
    if not durations or fps <= 0 or sample_rate <= 0 or overlap < 0:
        raise ValueError("Invalid master timeline")
    fps = Fraction(str(fps))
    elapsed = Fraction()
    start = 0
    scenes = []
    for index, duration in enumerate(durations):
        elapsed += Fraction(str(duration))
        end = nearest(elapsed * fps)
        count = end - start
        leading = overlap if index else 0
        if count < 1 or start < leading:
            raise ValueError("Insufficient frames for scene or overlap")
        generated = profile.length(count + leading)
        sample = lambda frame: nearest(frame * sample_rate / fps)
        scenes.append(dict(index=index + 1, start=start, end=end, count=count,
                           generated=generated, leading=leading, trailing=generated-count-leading,
                           conditioning_start_sample=sample(start-leading),
                           audio_start=sample(start), audio_end=sample(end)))
        start = end
    return scenes


def request_clock(model, duration, count, fps, rate):
    if model not in PROFILES or fps not in PROFILES[model].tested_fps:
        raise ValueError("Unverified model or conditioning FPS")
    if not 1 <= count <= 20:
        raise ValueError("Scene count must be 1–20")
    windows = boundaries([Fraction(str(duration))/count]*count, fps, rate, PROFILES[model])
    low, high = PROFILES[model].planner_seconds
    if any(not low*fps <= w["count"] <= high*fps for w in windows):
        raise ValueError("Existing ASMO planner requires each output scene to span 2–20 seconds")
    return windows


def trim(images, window):
    if images.ndim != 4 or len(images) != window["generated"]:
        raise ValueError("Decoder output differs from planned generation length")
    start = window["leading"]
    return images[start:start+window["count"]]


def conditioning_scene(scene, phase, cues):
    """Translate verified output-relative cues into the sampler's time coordinates."""
    shift = phase["window"]["leading"] / phase["fps"]
    return {**scene, "scene":{**scene["scene"], "duration":scene["scene"]["duration"]+shift},
            "tap_sync":{**(scene.get("tap_sync") or {}),
                        "primary_sync_targets_relative_seconds":[t+shift for t in cues]}}
