# Local image generation through ComfyUI

Audio-Analyze can submit local image-generation jobs to a running ComfyUI server, collect the generated files, and preserve a run report. This is a separate image-generation route; it does not replace or alter the LTX Studio submission route.

## Requirements

- ComfyUI running locally, normally at `http://127.0.0.1:8188`
- The `RealVisXL_V5.0_fp16.safetensors` checkpoint in ComfyUI's `models/checkpoints` directory
- The repository Python environment with the packages in `requirements.txt`

The default API workflow is `workflows/comfyui_sdxl_api.json`. It uses standard ComfyUI nodes: CheckpointLoaderSimple, CLIPTextEncode, EmptyLatentImage, KSampler, VAEDecode, and SaveImage. The workflow must remain in ComfyUI API format, not the ordinary UI workflow format.

## One image

Start ComfyUI using your existing portable installation, then run this from the Audio-Analyze repository root:

```powershell
$env:PYTHONPATH = "src"
python -m audio_analyze.comfyui_image_pipeline --prompt "A cinematic photorealistic gospel performance in a grand cathedral, two adult dancers in coordinated formal outfits, full-body wide composition, stained-glass light, realistic anatomy" --checkpoint "RealVisXL_V5.0_fp16.safetensors" --width 768 --height 1024 --steps 28 --cfg 5.5
```

For a song-aware prompt, add `--audio "C:\path\to\song.wav"`. Audio-Analyze reads tempo and other basic audio features, then adds rhythm/pacing context without replacing the user's visual brief.

## Multiple scene images

Create a JSON manifest:

```json
{
  "images": [
    {
      "name": "scene_01_cathedral_intro",
      "prompt": "Wide establishing keyframe of a grand cathedral performance, two adult dancers in coordinated formal outfits."
    },
    {
      "name": "scene_02_cathedral_chorus",
      "prompt": "Closer full-body performance keyframe of the same two dancers, choir visible behind them."
    }
  ]
}
```

Then run:

```powershell
$env:PYTHONPATH = "src"
python -m audio_analyze.comfyui_image_pipeline --manifest "inputs\prompts\image_scenes.json" --audio "C:\path\to\song.wav"
```

Use `--gemma-refine` to ask the local Ollama model (default `gemma3:4b`) to polish each positive prompt before ComfyUI receives it. This is optional; the original user prompt remains in the generation report. If refinement returns an empty or invalid response, the job is stopped rather than silently submitting a changed prompt.

Generated files are written beneath `outputs\comfyui_image_run\<run-id>\images`, with a `generation_report.json` containing the positive prompt, negative prompt, seed, model, sampler settings, ComfyUI prompt ID, and saved paths. Point the existing LTX seed-image picker or `--seed-dir` option at that run's `images` folder when you are ready to use the images for video.

## GTX 1070 starting settings

Start at 768 x 1024, one image at a time, 28 steps, CFG 5.5, DPM++ 2M / Karras. If ComfyUI runs out of VRAM, lower the dimensions to 640 x 896 or 576 x 832 before changing packages or replacing the model. Exact memory behavior depends on the installed PyTorch build, ComfyUI version, other GPU usage, and any custom nodes.

The generator talks to ComfyUI's local HTTP API. It does not download models, send prompts to a cloud service, or make LTX Studio requests.
