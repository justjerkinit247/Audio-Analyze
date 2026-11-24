import hashlib
import json
import os
from pathlib import Path
import subprocess
import uuid
from fractions import Fraction


def digest(path):
    with Path(path).open("rb") as stream:
        return hashlib.file_digest(stream, "sha256").hexdigest()


def atomic_json(path, value):
    tmp = path.with_name(uuid.uuid4().hex + ".tmp")
    try:
        with tmp.open("x", encoding="utf-8") as out:
            json.dump(value, out, indent=2, ensure_ascii=False, allow_nan=False)
            out.flush()
            os.fsync(out.fileno())
        tmp.replace(path)
    finally:
        tmp.unlink(missing_ok=True)


def load(path):
    return json.loads(path.read_text(encoding="utf-8"))


def audio_window(path, first, end, expected_rate):
    import av
    import torch
    from comfy_extras.nodes_audio import f32_pcm
    with av.open(str(path)) as container:
        stream = container.streams.audio[0]
        rate = stream.codec_context.sample_rate
        if rate != expected_rate:
            raise ValueError("Soundtrack sample rate changed")
        parts = []
        cursor = 0
        for frame in container.decode(stream):
            next_cursor = cursor + frame.samples
            if next_cursor > first:
                buf = torch.from_numpy(frame.to_ndarray())
                if not frame.format.is_planar:
                    buf = buf.reshape(-1,stream.channels).T
                parts.append(f32_pcm(buf[:,max(0,first-cursor):end-cursor]))
            cursor = next_cursor
            if cursor >= end:
                break
        if cursor < end:
            raise ValueError("Original soundtrack ends before scene")
        return torch.cat(parts,dim=1),rate


def accepted(root, key, windows):
    rows = []
    for window in windows:
        receipt = root / f"scene_{window['index']:03}/accepted.json"
        if not receipt.exists():
            continue
        row = load(receipt)
        if (row["key"] != key or row["window"] != window or
                window["index"] != len(rows)+1 or row["review"]["decision"] != "accept"):
            raise ValueError("Checkpoint belongs to another run or is out of sequence")
        for name in ("scene.mkv", "anchor.png"):
            if digest(receipt.parent/name) != row["hashes"][name]:
                raise ValueError(f"Corrupt accepted artifact: {receipt.parent/name}")
        rows.append(row)
    return rows


def save_scene(directory, images, fps, key, window, review, details):
    import av
    import numpy as np
    from PIL import Image
    if review.get("decision") != "accept" or len(images) != window["count"]:
        raise ValueError("A complete accepted batch is required")
    directory.mkdir(parents=True, exist_ok=True)
    if (directory/"accepted.json").exists():
        raise ValueError("Scene already checkpointed")
    tmp = directory/"pending.mkv"
    with av.open(str(tmp), "w") as container:
        stream = container.add_stream("ffv1", rate=fps)
        stream.height, stream.width = images.shape[1:3]
        stream.pix_fmt = "bgr0"
        previous = None
        repeated = 0
        differences = []
        for image in images:
            rgb = (image.detach().cpu().clamp(0, 1).numpy()*255).round().astype(np.uint8)
            sample = rgb[::8,::8].astype(np.float32)
            if previous is None:
                first = sample
            else:
                change = float(np.abs(sample-previous).mean())
                repeated += int(change == 0)
                differences.append(change)
            previous = sample
            frame = av.VideoFrame.from_ndarray(rgb, format="rgb24")
            container.mux(stream.encode(frame))
        container.mux(stream.encode())
    tmp.replace(directory/"scene.mkv")
    Image.fromarray(rgb).save(directory/"pending.png")
    (directory/"pending.png").replace(directory/"anchor.png")
    observations = dict(repeated_sampled_frames=repeated,
                        mean_adjacent_rgb_change=float(np.mean(differences)) if differences else None)
    if window["index"] > 1:
        anchor = directory.parent/f"scene_{window['index']-1:03}"/"anchor.png"
        with Image.open(anchor) as prior:
            before = np.asarray(prior.convert("RGB"))[::8,::8].astype(np.float32)
        observations["boundary_mean_rgb_change"] = float(np.abs(first-before).mean())
        observations["boundary_mean_brightness_change"] = float(first.mean()-before.mean())
    atomic_json(directory/"accepted.json", dict(key=key, window=window, review=review,
                observations=observations, hashes={name:digest(directory/name) for name in ("scene.mkv","anchor.png")}, **details))


def assemble(root, rows, config):
    import av
    import imageio_ffmpeg
    if len(rows) != len(config["windows"]):
        raise ValueError("Incomplete run")
    fps, rate = config["fps"], config["rate"]
    concat = root/"scenes.txt"
    concat.write_text("".join(f"file 'scene_{r['window']['index']:03}/scene.mkv'\n" for r in rows), encoding="ascii")
    samples = rows[-1]["window"]["audio_end"]
    tmp = root/"export.pending.mp4"
    subprocess.run([imageio_ffmpeg.get_ffmpeg_exe(), "-v","error","-y","-f","concat","-safe","1",
                    "-i",concat.name,"-i",config["inputs"]["audio"],"-map","0:v:0","-map","1:a:0",
                    "-vf",f"setpts=N/({fps}*TB)","-r",str(fps),"-c:v","libx264","-pix_fmt","yuv420p",
                    "-af",f"atrim=end_sample={samples},asetpts=PTS-STARTPTS","-c:a","aac",
                    "-movie_timescale",str(rate),"-movflags","+faststart",tmp.name], cwd=root, check=True)
    with av.open(str(tmp)) as container:
        video, audio = container.streams.video[0], container.streams.audio[0]
        times = [f.pts*f.time_base for f in container.decode(video)]
        if len(times) != rows[-1]["window"]["end"] or any(t != Fraction(i,fps) for i,t in enumerate(times)):
            raise ValueError("Export frame count or presentation timestamps differ from master timeline")
        if audio.start_time != 0 or audio.duration*audio.time_base != Fraction(samples,rate):
            raise ValueError("Export soundtrack timing differs from master timeline")
    tmp.replace(root/"continuous.mp4")
    return dict(frames=len(times), samples=samples, rate=rate, fps=fps, path=str(root/"continuous.mp4"))
