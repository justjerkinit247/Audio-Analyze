from pathlib import Path
import json
from .image_integration import inject_image

IMAGE_DIR = Path("inputs/runway_seed_images")


def load_images():
    if not IMAGE_DIR.exists():
        return []
    return sorted([p for p in IMAGE_DIR.iterdir() if p.suffix.lower() in [".png", ".jpg", ".jpeg"]])


def generate_multi_clip_payloads(base_payloads):
    images = load_images()
    if not images:
        return base_payloads

    new_payloads = []

    for i, payload in enumerate(base_payloads):
        image_index = i % len(images)
        payload_copy = payload.copy()

        # inject different image per clip
        payload_copy = inject_image(payload_copy)
        payload_copy["clip_index"] = i
        payload_copy["assigned_image"] = str(images[image_index])

        new_payloads.append(payload_copy)

    return new_payloads
