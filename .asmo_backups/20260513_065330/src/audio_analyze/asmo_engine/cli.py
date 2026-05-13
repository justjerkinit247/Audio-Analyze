from __future__ import annotations

import argparse
from pathlib import Path

from .asmo_engine import ASMOEngine


def main() -> None:
    parser = argparse.ArgumentParser(description="ASMO lyric/audio motion sync tools")
    parser.add_argument("--lyrics", required=True)

    args = parser.parse_args()

    engine = ASMOEngine()
    timeline = engine.generate_timeline(lyric_path=args.lyrics)

    print("ASMO timeline created.")
    print(f"Events: {len(timeline.get('events', []))}")
    print(Path(args.lyrics).resolve())


if __name__ == "__main__":
    main()
