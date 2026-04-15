from pathlib import Path
import argparse
import math

from moviepy import VideoFileClip, AudioFileClip, concatenate_videoclips


def collect_scene_clips(download_dir: Path):
    clips = []
    for i in range(1, 7):
        p = download_dir / f"Gospel_Twerk_-_Holy_Cheeks_1_scene_{i:02d}.mp4"
        if not p.exists():
            raise FileNotFoundError(f"Missing required scene clip: {p}")
        clips.append(p)
    return clips


def make_piece(src_clip, target_duration, seed):
    if src_clip.duration <= 0:
        raise ValueError("Invalid source clip duration.")

    if src_clip.duration <= target_duration:
        loops = max(1, int(math.ceil(target_duration / src_clip.duration)))
        pieces = [src_clip.subclipped(0, src_clip.duration) for _ in range(loops)]
        merged = concatenate_videoclips(pieces, method="compose")
        return merged.subclipped(0, target_duration)

    max_start = max(0.0, src_clip.duration - target_duration)
    offset = (seed * 0.61) % (max_start if max_start > 0 else 0.01)
    return src_clip.subclipped(offset, offset + target_duration)


def build_reel(audio_path: Path, download_dir: Path, start_seconds: float, duration_seconds: float, output_path: Path):
    scene_paths = collect_scene_clips(download_dir)
    src_clips = [VideoFileClip(str(p)) for p in scene_paths]

    audio_full = AudioFileClip(str(audio_path))
    audio_end = start_seconds + duration_seconds
    if audio_end > audio_full.duration:
        raise ValueError(
            f"Requested reel ends at {audio_end}s, but audio duration is only {audio_full.duration:.2f}s"
        )

    audio_clip = audio_full.subclipped(start_seconds, audio_end)

    num_clips = len(src_clips)
    target_piece_duration = duration_seconds / num_clips

    assembled = []
    for idx, src_clip in enumerate(src_clips, start=1):
        piece = make_piece(src_clip, target_piece_duration, idx)
        assembled.append(piece)

    final_video = concatenate_videoclips(assembled, method="compose")

    if final_video.duration > duration_seconds:
        final_video = final_video.subclipped(0, duration_seconds)

    final_video = final_video.with_audio(audio_clip)

    output_path.parent.mkdir(parents=True, exist_ok=True)
    final_video.write_videofile(
        str(output_path),
        codec="libx264",
        audio_codec="aac",
        fps=24,
        preset="veryfast"
    )

    for c in src_clips:
        c.close()
    audio_clip.close()
    audio_full.close()
    final_video.close()


def parse_args():
    parser = argparse.ArgumentParser(description="Build a 30-second mid-song reel from six scene clips.")
    parser.add_argument("--audio", required=True)
    parser.add_argument("--downloads", required=True)
    parser.add_argument("--start-seconds", type=float, required=True)
    parser.add_argument("--duration-seconds", type=float, default=30.0)
    parser.add_argument("--output", required=True)
    return parser.parse_args()


def main():
    args = parse_args()
    build_reel(
        audio_path=Path(args.audio),
        download_dir=Path(args.downloads),
        start_seconds=args.start_seconds,
        duration_seconds=args.duration_seconds,
        output_path=Path(args.output),
    )
    print("30-second mid-song reel export complete.")
    print(Path(args.output).resolve())


if __name__ == "__main__":
    main()
