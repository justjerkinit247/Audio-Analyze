from pathlib import Path
import argparse

try:
    from .pipeline_batch import analyze_folder as analyze_pipeline_batch
    from .prompt_compiler import compile_prompt_bundle
    from .creative_prompt_compiler import compile_creative_bundle
    from .style_mode_compiler import compile_style_mode_bundle
except ImportError:
    from pipeline_batch import analyze_folder as analyze_pipeline_batch
    from prompt_compiler import compile_prompt_bundle
    from creative_prompt_compiler import compile_creative_bundle
    from style_mode_compiler import compile_style_mode_bundle


def run_workflow(input_dir, working_dir, mode):
    working_dir = Path(working_dir)
    pipeline_dir = working_dir / 'pipeline_batch_run'
    prompt_dir = working_dir / 'prompt_bundle_run'
    creative_dir = working_dir / 'creative_prompt_bundle_run'
    style_dir = working_dir / 'style_mode_run'

    pipeline_result = analyze_pipeline_batch(input_dir=Path(input_dir), output_dir=pipeline_dir)
    manifest_path = pipeline_dir / 'manifest.json'

    prompt_result = compile_prompt_bundle(manifest_path, prompt_dir)
    creative_result = compile_creative_bundle(manifest_path, creative_dir)
    style_result = compile_style_mode_bundle(manifest_path, style_dir, mode)

    return {
        'pipeline': pipeline_result,
        'prompt_bundle': prompt_result,
        'creative_prompt_bundle': creative_result,
        'style_mode_bundle': style_result,
    }


def parse_args():
    parser = argparse.ArgumentParser(description='Run the full local audio-to-prompt workflow.')
    parser.add_argument('--input-dir', required=True, help='Folder containing audio files')
    parser.add_argument('--working-dir', default='outputs', help='Base output folder for workflow artifacts')
    parser.add_argument('--mode', default='performance-video', choices=['suno', 'cinematic', 'performance-video', 'short-form-social'], help='Target style mode for style-specific prompts')
    return parser.parse_args()


def main():
    args = parse_args()
    result = run_workflow(args.input_dir, args.working_dir, args.mode)

    print('Workflow wrapper complete.')
    print(f"Pipeline output dir       : {result['pipeline']['output_dir']}")
    print(f"Prompt bundle output dir  : {result['prompt_bundle']['output_dir']}")
    print(f"Creative bundle output dir: {result['creative_prompt_bundle']['output_dir']}")
    print(f"Style bundle output dir   : {result['style_mode_bundle']['output_dir']}")
    print(f"Style mode               : {result['style_mode_bundle']['mode']}")


if __name__ == '__main__':
    main()
