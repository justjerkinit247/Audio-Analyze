#!/usr/bin/env python3
"""An explicitly gated, single-call Modal A100-80GB GPU readiness probe.

This is NOT an LTX renderer. It transfers no model, workflow, music, or secrets
to the cloud. Running without --run-cloud only prints a safe preflight summary.
"""
import modal

app = modal.App("gtrg-a100-80gb-readiness-canary")


@app.function(
    image=modal.Image.debian_slim(python_version="3.11"),
    gpu="A100-80GB",
    timeout=90,
    min_containers=0,
    max_containers=1,
    scaledown_window=2,
    retries=0,
)
def inspect_gpu():
    """Execute one bounded NVIDIA query on a cloud A100 80GB."""
    import subprocess

    completed = subprocess.run(
        [
            "nvidia-smi",
            "--query-gpu=name,memory.total,compute_cap",
            "--format=csv,noheader,nounits",
        ],
        capture_output=True,
        text=True,
        check=True,
        timeout=20,
    )
    return completed.stdout.strip()


@app.local_entrypoint()
def main(run_cloud: bool = False):
    print("=== GTRG MODAL GPU READINESS CANARY ===")
    print("GPU: one A100-80GB; no ComfyUI, models, audio, or rendering transferred")
    print("Timeout: 90 seconds; zero retries; max one container; no warm minimum")
    print("Estimate: A100 GPU only $0.000694/s (~$0.0625 for 90 seconds)")
    print("CPU, memory and other Modal charges are additional.")
    if not run_cloud:
        print("Status: DRY-RUN / no remote GPU invocation")
        print("To authorize one GPU check: modal run scripts/gtrg_modal_gpu_canary.py --run-cloud")
        return
    print("Submitting exactly one GPU query to Modal...")
    result = inspect_gpu.remote()
    print("Cloud GPU confirmed: " + result)
    print("Done. This did NOT generate any LTX frames.")
