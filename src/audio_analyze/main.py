from pathlib import Path

def main() -> None:
    print("Audio Analyze is set up.")
    print(f"Project root: {Path(__file__).resolve().parents[2]}")

if __name__ == "__main__":
    main()
