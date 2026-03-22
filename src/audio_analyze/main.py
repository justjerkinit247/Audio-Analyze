from pathlib import Path

def main():
    print("Audio Analyze")
    print("Vocal profile prototype is active.")

    project_root = Path(__file__).resolve().parents[2]
    print(f"Project root: {project_root}")

if __name__ == "__main__":
    main()