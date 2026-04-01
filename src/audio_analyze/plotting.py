from pathlib import Path
import numpy as np
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt


def save_waveform_plot(y, sr, output_path, title=None):
    output_path = Path(output_path)
    output_path.parent.mkdir(parents=True, exist_ok=True)

    times = np.arange(len(y)) / float(sr)

    fig, ax = plt.subplots(figsize=(12, 4))
    ax.plot(times, y, linewidth=0.8)
    ax.set_xlabel("Time (s)")
    ax.set_ylabel("Amplitude")
    ax.set_title(title or "Waveform")
    ax.grid(True, alpha=0.3)
    fig.tight_layout()
    fig.savefig(output_path, dpi=150)
    plt.close(fig)


def save_loudness_envelope_plot(rms, sr, hop_length, output_path, title=None):
    output_path = Path(output_path)
    output_path.parent.mkdir(parents=True, exist_ok=True)

    times = (np.arange(len(rms)) * hop_length) / float(sr)

    fig, ax = plt.subplots(figsize=(12, 4))
    ax.plot(times, rms, linewidth=1.0)
    ax.set_xlabel("Time (s)")
    ax.set_ylabel("RMS")
    ax.set_title(title or "Loudness Envelope")
    ax.grid(True, alpha=0.3)
    fig.tight_layout()
    fig.savefig(output_path, dpi=150)
    plt.close(fig)
