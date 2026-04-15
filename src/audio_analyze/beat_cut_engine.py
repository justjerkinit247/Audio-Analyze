from pathlib import Path
import argparse
import json
import math

import librosa
import numpy as np
from moviepy import VideoFileClip, AudioFileClip, concatenate_videoclips


def write_json(path, data):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, indent=2), encoding="utf-8")


def detect_beats(audio_path: Path):
    y, sr = librosa.load(str(audio_path), sr=None, mono=True)
    tempo_raw, beats = librosa.beat.beat_track(y=y, sr=sr)
    tempo = float(np.asarray(tempo_raw).reshape(-1)[0]) if np.asarray(tempo_raw).size else None
    beat_times = librosa.frames_to_time(beats, sr=sr).tolist()
    duration = float(librosa.get_duration(y=y, sr=sr))
    return {
        "tempo_bpm": round(tempo, 3) if tempo is not None else None,
        "duration_seconds": round(duration, 3),
        "beat_times": beat_times,
    }


def build_intervals(beat_times, total_duration, beats_per_cut=8, min_len=1.5, max_len=5.0):
    if not beat_times:
        return [(0.0, total_duration)]

    points = [0.0] + beat_times + [total_duration]
    intervals = []
    i = 0

    while i < len(points) - 1:
        j = min(i + beats_per_cut, len(points) - 1)
        start_t = points[i]
        end_t = points[j]
        dur = end_t - start_t

        while dur < min_len and j < len(points) - 1:
            j += 1
            end_t = points[j]
            dur = end_t - start_t

        if dur > max_len:
            pieces = max(1, math.ceil(dur / max_len))
            piece_len = dur / pieces
            for k in range(pieces):
                s = start_t + (k * piece_len)
                e = min(end_t, start_t + ((k + 1) * piece_len))
                intervals.append((round(s, 3), round(e, 3)))
        else:
            intervals.append((round(start_t, 3), round(end_t, 3)))

        i = j

    return intervals


def get_scene_clips(download_dir: Path):
    clips = []
    for i in range(1, 7):
        p = download_dir / f"Gospel_Twerk_-_Holy_Cheeks_1_scene_{i:02d}.mp4"
        if not p.exists():
            raise FileNotFoundError(f"Missing scene clip: {p}")
        clips.append(p)
    return clips


def extract_piece(src_clip, target_duration, offset_seed):
    if src_clip.duration <= 0:
        raise ValueError("Source clip duration invalid.")

    if src_clip.duration <= target_duration:
        loops = max(1, int(math.ceil(target_duration / src_clip.duration)))
        pieces = [src_clip.subclipped(0, src_clip.duration) for _ in range(loops)]
        merged = concatenate_videoclips(pieces, method="compose")
        return merged.subclipped(0, target_duration)

    max_start = max(0.0, src_clip.duration - target_duration)
    offset = (offset_seed * 0.73) % (max_start if max_start > 0 else 0.01)
    return src_clip.subclipped(offset, offset + target_duration)


def build_video(audio_path: Path, download_dir: Path, output_path: Path, manifest_path: Path, beats_per_cut=8):
    beat_data = detect_beats(audio_path)
    total_duration = beat_data["duration_seconds"]
    intervals = build_intervals(
        beat_times=beat_data["beat_times"],
        total_duration=total_duration,
        beats_per_cut=beats_per_cut,
        min_len=1.5,
        max_len=5.0,
    )

    clip_paths = get_scene_clips(download_dir)
    src_clips = [VideoFileClip(str(p)) for p in clip_paths]

    assembled = []
    manifest_rows = []

    for idx, (start_t, end_t) in enumerate(intervals, start=1):
        target_dur = max(0.1, end_t - start_t)
        src_idx = (idx - 1) % len(src_clips)
        src_path = clip_paths[src_idx]
        src_clip = src_clips[src_idx]

        piece = extract_piece(src_clip, target_dur, idx)
        assembled.append(piece)

        manifest_rows.append({
            "segment_index": idx,
            "music_start": round(start_t, 3),
            "music_end": round(end_t, 3),
            "segment_duration": round(target_dur, 3),
            "source_scene_file": src_path.name,
        })

    final_video = concatenate_videoclips(assembled, method="compose")
    final_audio = AudioFileClip(str(audio_path))

    if final_video.duration > final_audio.duration:
        final_video = final_video.subclipped(0, final_audio.duration)

    final_video = final_video.with_audio(final_audio)

    output_path.parent.mkdir(parents=True, exist_ok=True)
    final_video.write_videofile(
        str(output_path),
        codec="libx264",
        audio_codec="aac",
        fps=24,
        preset="medium"
    )

    manifest = {
        "tempo_bpm": beat_data["tempo_bpm"],
        "audio_duration_seconds": beat_data["duration_seconds"],
        "beats_per_cut": beats_per_cut,
        "segments": manifest_rows,
        "output_video": str(output_path.resolve()),
    }
    write_json(manifest_path, manifest)

    for c in src_clips:
        c.close()
    final_audio.close()
    final_video.close()

    return manifest


def parse_args():
    parser = argparse.ArgumentParser(description="Auto snap scene transitions to music beats for short-form export.")
    parser.add_argument("--audio", required=True)
    parser.add_argument("--downloads", required=True)
    parser.add_argument("--output", required=True)
    parser.add_argument("--manifest", required=True)
    parser.add_argument("--beats-per-cut", type=int, default=8)
    return parser.parse_args()


def main():
    args = parse_args()
    manifest = build_video(
        audio_path=Path(args.audio),
        download_dir=Path(args.downloads),
        output_path=Path(args.output),
        manifest_path=Path(args.manifest),
        beats_per_cut=args.beats_per_cut,
    )
    print("Beat-cut export complete.")
    print(f"Tempo BPM: {manifest['tempo_bpm']}")
    print(f"Output: {manifest['output_video']}")
    print(f"Segments: {len(manifest['segments'])}")


if __name__ == "__main__":
    main()
