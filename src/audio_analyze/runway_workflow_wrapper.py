from pathlib import Path
import argparse

try:
    from .workflow_wrapper import run_workflow as run_base_workflow
    from .runway_video_compiler import compile_runway_bundle
except ImportError:
    from workflow_wrapper import run_workflow as run_base_workflow
    from runway_video_compiler import compile_runway_bundle


def run_workflow(input_dir, working_dir, mode, runway_model, ratio):
    working_dir = Path(working_dir)

    result = run_base_workflow(
        input_dir=input_dir,
        working_dir=working_dir,
        mode=mode
    )

    manifest_path = working_dir / "pipeline_batch_run" / "manifest.json"
    runway_dir = working_dir / "runway_video_run"

    runway_result = compile_runway_bundle(
        manifest_path,
        runway_dir,
        runway_model,
        ratio
    )

    result["runway_video_bundle"] = runway_result

    return result


def parse_args():
    parser = argparse.ArgumentParser()
    parser.add_argument("--input-dir", required=True)
    parser.add_argument("--working-dir", default="outputs")
    parser.add_argument("--mode", default="short-form-social")
    parser.add_argument("--runway-model", default="gen4.5")
    parser.add_argument("--ratio", default="9:16")
    return parser.parse_args()


def main():
    args = parse_args()

    result = run_workflow(
        args.input_dir,
        args.working_dir,
        args.mode,
        args.runway_model,
        args.ratio
    )

    runway_bundle = result["runway_video_bundle"]
    runway_output_dir = Path(args.working_dir) / "runway_video_run"

    print("Runway workflow wrapper complete.")
    print(f"Pipeline output dir       : {result['pipeline']['output_dir']}")
    print(f"Prompt bundle output dir  : {result['prompt_bundle']['output_dir']}")
    print(f"Creative bundle output dir: {result['creative_prompt_bundle']['output_dir']}")
    print(f"Style bundle output dir   : {result['style_mode_bundle']['output_dir']}")
    print(f"Runway output dir         : {runway_output_dir}")
    print(f"Runway payloads created   : {runway_bundle.get('files_compiled', 'unknown')}")
    print(f"Style mode               : {result['style_mode_bundle']['mode']}")
    print(f"Runway model             : {runway_bundle.get('model', 'gen4.5')}")
    print(f"Runway ratio             : {runway_bundle.get('ratio', args.ratio)}")


if __name__ == "__main__":
    main()