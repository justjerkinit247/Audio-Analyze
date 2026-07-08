# Tap-accent motion sync

## Goal

Visible character direction changes should land on sharp high-percussive accents such as claps, snares, and hi-hats: the **tap**, not the kick/bass **boom**.

For twerk or lower-body dance scenes, the intended policy is:

```text
boom -> travel, hold, or prepare
tap  -> reverse or accent hip/glute direction
```

## Scope

This change is deliberately limited to the standard auto-audio LTX orchestration path.

It does not alter:

- audio-file selection;
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

## Prompt handoff

Before preflight and submission, each active scene prompt receives:

```text
[TAP_SYNC]
Primary tap-accent times inside this clip: ...
```

The block tells the generation path to:

- use clap/snare/hi-hat-like transients as visible motion triggers;
- reverse hip/glute travel on each listed tap for dance/twerk choreography;
- avoid using kick/bass-only boom hits as direction-change triggers.

## Disable switch

The default is enabled. The previous behavior remains available through:

```powershell
python -m audio_analyze.ltx_auto_audio_orchestrator --no-tap-accent-sync ...
```

## Validation

The focused tests verify that:

- off-grid high-percussive tap accents outrank beat-grid fallback hits;
- the `[TAP_SYNC]` block appears before `[MOTION_PROMPT]`;
- existing `[AUDIO_TIMING]`, `[MOTION_PROMPT]`, and `[NEGATIVE_PROMPT]` sections remain intact;
- the offline one-scene CI pipeline reports the `tap_not_boom` policy without using `--live`.
