# Tap-accent motion sync

## Goal

Visible character accents should land on sharp high-percussive events such as claps, snares, and hi-hats: the **tap**, not the kick/bass **boom**.

For twerk or lower-body dance scenes, the policy is:

```text
boom -> maintain groove or prepare
tap  -> compact localized glute-cheek pulse and controlled recoil
```

The tap detector and timestamps remain unchanged. The choreography profile controls how those timestamps are translated into visible motion.

## Scope

This change is deliberately limited to the standard auto-audio LTX orchestration path.

It does not alter:

- audio-file selection;
- tap detection or timestamp selection;
- scene or seed-image mapping;
- filename-hint expansion;
- ASMO negative-prompt memory;
- LTX live-submit safety or preflight checks;
- video assembly;
- model, resolution, or guidance defaults.

## Detection

`tap_accent_sync.py`:

1. separates the percussive component with harmonic/percussive source separation;
2. measures high-band onset energy above 1,200 Hz;
3. rejects transients dominated by low-frequency energy;
4. includes off-grid sharp tap accents instead of limiting motion to the main beat grid;
5. falls back to the strongest percussive beat-grid hits when no reliable high-band taps are detected.

This is a spectral classification heuristic, not perfect instrument stem separation. It is intended to distinguish sharp tap-like accents from bass-heavy impacts without requiring an external service.

## Scene-aware choreography profiles

The localized glute-pulse profile activates automatically when the seed filename or cleaned scene hint contains terms such as:

- `twerk` or `twerking`;
- `glute`, `glutes`, `cheek`, `cheeks`, `booty`, or `rump`;
- a hip/pelvis term together with a squat/lower-body term.

For these scenes, every detected tap becomes:

- one compact glute-cheek contraction;
- a small backward pelvis pop;
- a controlled recoil;
- optional left/right cheek emphasis when physically natural.

The prompt also requires:

- visible movement beginning at 0.00 seconds;
- subtle continuous pelvic micro-motion between taps;
- planted feet and lowered heels;
- bent knees and the same squat pose family;
- stable head, shoulders, torso, and overall body height;
- no jumping, hopping, standing, repeated squats, or whole-body bouncing.

Scenes without lower-body dance language keep the generic tap-action profile.

## Prompt handoff

Before preflight and submission, each active scene prompt receives:

```text
[TAP_SYNC]
Primary tap-accent times inside this clip: ...
```

For localized glute scenes, the pipeline also extends `[NEGATIVE_PROMPT]` with motion guards including:

```text
static opening frame, delayed motion onset, jumping, hopping,
feet leaving the floor, repeated squats, whole-body bouncing,
vertical pelvic bouncing, large vertical displacement
```

## Disable switch

The default is enabled. The previous behavior remains available through:

```powershell
python -m audio_analyze.ltx_auto_audio_orchestrator --no-tap-accent-sync ...
```

## Validation

The focused tests verify that:

- off-grid high-percussive tap accents outrank beat-grid fallback hits;
- tap timestamps are preserved exactly when the localized profile is applied;
- twerk filenames activate the localized glute-pulse profile;
- non-dance scenes retain the generic tap-action profile;
- jumping and frozen-opening guards are merged into `[NEGATIVE_PROMPT]`;
- existing `[AUDIO_TIMING]`, `[MOTION_PROMPT]`, and `[NEGATIVE_PROMPT]` sections remain intact;
- the offline one-scene CI pipeline remains dry-run only and spends no generation credits.
