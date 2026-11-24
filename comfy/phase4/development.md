# Phase 4.1 development record

## Recovered baseline

The saved 1.3 editor workflow has SHA-256 A45E175893B38C353BF5FD9B1B00E96F0488D6A43D65DA9C045058C151AC957A before and after installation. The original checkout was on main at 869febf with modified engine and CLI files and untracked ASMO feedback/controller sources. Development used a separate feature worktree. No remote publication took place.

The 21m37s local_motion take and 20m07s asmo_motion take both used the 288 × 512 native LTX 2.3 checkpoint, distilled LoRA at 0.5, Euler, CFG 1, noise seed 45 and in-place image strength 0.7. Each exported 51 frames at 24 FPS. The operator identified the second take as directionally correct. In its recorded conditioning prompt, the woman transfers weight onto the carriage step and draws their hands toward the doorway while the man rises and follows. The first prompt describes guiding him forward while the carriage drifts into view. The two native sampling recipes match. The runs establish a change in the actual conditioning text and operator-observed outcome. Neither original graph contained the ASMO review/retry gate.

## Implementation and checks

Version 1.4 wraps the recovered native recipe in a sequential loopback queue controller with disk checkpoints. The dedicated branch extends the installed bridge through version-checked source edits. Private input references and extracted workstation prompts stay outside the branch. The existing ASMO Motion Loop retains authority over acceptance and retries. The coordinator advances after the accepted finalizer output has been saved. It reopens the same single original audio stream for final export. A fresh isolated CPU process loaded the installed nodes and used ComfyUI's native prompt validator on the two-node operator graph and 24-node child graph. Recipe capture verified the positive prompt path and built a 17-node retry expansion.

The portable interpreter passed all five Phase 4 tests. A synthetic two-scene export contained 96 consecutive video timestamps at 24 FPS and an audio stream of exactly 176400 samples at 44100 Hz. The recovery fixture skipped accepted scene one, submitted only scene two and preserved the failed child status. A separate check ran both installed FinishScene calls and compared each original audio slice sample-for-sample. Forty existing focused regression tests passed. Local transcripts and original prompts are in the sibling Phase4-local-baseline evidence directory.

The repository copy of asmo_narrative_timing.py matched the committed baseline. The preserved ASMO-Narrative-Patch copy differed by 97 insertions and two removals including candidate-bound reviews and narrative verdicts. Both versions were preserved. Phase 4 uses the musical review path.

## Remaining validation

A real two-scene 1.4 GPU render, crash/resume across an actual server restart, operator continuity review and choreography approval remain outstanding. The operator's approval of take 00002 applies to 1.3. The source audio drives planning and final output. The native model uses an empty audio latent. Separate model reload overhead has no reliable local receipt. Multi-frame conditioning and latent extension remain experimental. The installed guide node can accept extra frames, but its effect on identity or movement has not been benchmarked. Only the recovered 24 FPS profile is enabled for live use.
