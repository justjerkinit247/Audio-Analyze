from pathlib import Path
import json

from src.audio_analyze.ltx_client import LTXClient

plan_path = Path("outputs/ltx_video_run/holy_cheeks_ltx_plan.json")
plan = json.loads(plan_path.read_text(encoding="utf-8-sig"))

client = LTXClient()
downloads = Path("outputs/ltx_video_run/downloads")
downloads.mkdir(parents=True, exist_ok=True)

scene_num = 9
item = next(x for x in plan["results"] if int(x["clip_index"]) == scene_num)
scene = item["scene"]

prompt = item["prompt_text"][:900]
image_uri = item["seed_image_used"]
duration = float(scene.get("duration", 8.0))
output = downloads / ("hop_out_the_whip_ltx_scene_{:02d}.mp4".format(scene_num))

print("Submitting IMAGE-TO-VIDEO fallback scene {:02d}".format(scene_num))
print("Seed image:", image_uri)
print("Duration:", duration)
print("Output:", output)

result = client.image_to_video(
    image_uri=image_uri,
    prompt=prompt,
    output_path=str(output),
    model="ltx-2-3-pro",
    duration=duration,
    resolution=item.get("resolution", "1080x1920"),
    fps=24,
    guidance_scale=6.5,
    dry_run=False,
)

print(result)
