# ASMO continuous generation 1.4

Open the 1.4 editor workflow after starting ComfyUI with the updated RenderBridge. Set the original audio, one identity seed and optional lyrics in the input node. The second node takes total duration, FPS, scene count, the checkpoint, the attempt limit per scene and a run name. The workstation copy uses the same local input paths as 1.3. The portable workflows in this repository have blank input paths.

Press Run once. The first prompt returns the path to the run status. A coordinator in the local ComfyUI process submits one scene at a time to that server's normal queue. Keep ComfyUI open during generation. Under the ComfyUI output folder, open `ASMO_1_4/<run_name>/status.json` for the current scene, prompt ID or error. A successful export appears there as `continuous.mp4`.

To resume after a restart, submit the same workflow with the same run name and inputs. Each scene has an accepted receipt, a lossless FFV1 intermediate and a PNG anchor. The coordinator checks the configuration and checkpoint hashes before selecting the first incomplete scene. Use a new name for a different run. If only export failed, resubmission retries assembly using the existing receipts.

## Installation on this workstation

The adapter extends the existing local RenderBridge and orchestration worker. The installer checks for the expected source fragments, compiles the edited modules and backs up each changed file. To reproduce installation, run `python install.py <ComfyUI/custom_nodes>` from this directory, then load the editor JSON in ComfyUI after a restart. The accompanying API JSON is the operator submission for API clients. Both require the existing workstation model files, Python environments, RenderBridge, ASMO feedback modules and local Gemma.

## Timing and resources

The initial production profile exposes the recovered 288 × 512 native LTX 2.3 recipe at 24 FPS. The existing planner supports 2–20 seconds per scene. The workstation measurement covers a 57-frame generation. Longer durations within the allowed model and planner limits still need hardware testing. The adapter rejects unverified model/FPS selections.

The planner rounds cumulative requested boundaries to the nearest frame, then derives audio sample boundaries from absolute frame positions. Scene two and later include the previous accepted frame's time slot in generation. Native in-place image conditioning writes the seed at latent time zero with strength 0.7. That slot can differ visually from the seed after sampling. The adapter trims that time slot and trailing padding before ASMO evaluation. Accepted timing edits are included in the saved anchor.

The recovered recipe uses an empty audio latent. Original audio supplies planning, cue evaluation and the single final soundtrack. The model receives the same generation frame count for the audio and video latents. Gemma's generation cue times include the leading anchor. The quality gate measures the trimmed output on its own clock.

CPU boundary metrics report sampled color change and repeated frames. Gemma receives the current seed, recent accepted motion history and original identity reference. Pose and movement direction remain uncertain unless observed. Temporal-tail and latent-extension strategies have no enabled profile. A two-scene GPU run and operator review are required to establish visual continuity and choreography on this workstation.
