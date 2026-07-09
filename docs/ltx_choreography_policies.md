# LTX Choreography Policies

The LTX pipeline uses one universal caller. Scene-specific choreography behavior is selected by a structured per-run policy rather than by a separate hardwired pipeline.

## Default behavior

`auto` is the default profile request. The policy resolver uses the exact seed filename direction and generated scene metadata to select a configured profile. If no specialized profile matches, the universal `generic_tap_action` profile is used.

The target count remains analysis-derived. Profiles currently use `all_reliable`, which retains every reliable tap event inside the clip window after spectral classification and minimum-spacing filtering. There is no default numerical floor or ceiling.

## Explicit controlled runs

The live launcher accepts:

```powershell
.\run-ltx-live.cmd --choreography-profile auto
```

A configured profile can be selected explicitly for an A/B test:

```powershell
.\run-ltx-live.cmd --choreography-profile localized_glute_pulse
```

Explicit selection is a per-run override. It does not modify repository defaults or future runs.

## Specialized target selection

The profile schema supports a future `strongest_limited` target-selection mode with a profile-owned `max_targets` value. This should be used only for a deliberately designed policy, not as a hidden global limiter. Current profiles use `all_reliable`.

## Configuration

Profiles are defined in `config/ltx_choreography_profiles.json`. Each profile contains:

- activation rules;
- target-selection policy;
- tap-sync prompt template;
- negative terms;
- required validation phrases;
- choreography-manifest rules.

Shared orchestration code resolves and applies those data structures without embedding scene-specific prompt branches.
