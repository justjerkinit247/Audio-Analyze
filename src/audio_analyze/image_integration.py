import base64
from pathlib import Path

IMAGE_DIR = Path("inputs/runway_seed_images")


def load_seed_image():
    if not IMAGE_DIR.exists():
        return None

    for file in IMAGE_DIR.iterdir():
        if file.suffix.lower() in [".png", ".jpg", ".jpeg"]:
            return file

    return None


def image_to_data_uri(image_path):
    with open(image_path, "rb") as f:
        encoded = base64.b64encode(f.read()).decode("utf-8")

    mime = "image/png"
    if image_path.suffix.lower() in [".jpg", ".jpeg"]:
        mime = "image/jpeg"

    return f"data:{mime};base64,{encoded}"


def inject_image(payload):
    image_path = load_seed_image()

    if image_path:
        payload["promptImage"] = image_to_data_uri(image_path)
        payload["seed_image_used"] = str(image_path.resolve())

    return payload
