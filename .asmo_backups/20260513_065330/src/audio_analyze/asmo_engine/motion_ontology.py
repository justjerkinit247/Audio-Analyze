from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class MotionDirective:
    movement_type: str
    body_region: str
    camera_behavior: str
    energy: float
    prompt_fragment: str


DEFAULT_DIRECTIVE = MotionDirective(
    movement_type="groove",
    body_region="full_body",
    camera_behavior="steady_tracking",
    energy=0.45,
    prompt_fragment="maintain rhythmic full-body groove synchronized to beat",
)


ONTOLOGY: dict[str, MotionDirective] = {
    "hands": MotionDirective(
        movement_type="raise_arms",
        body_region="upper_body",
        camera_behavior="upward_follow",
        energy=0.55,
        prompt_fragment="raise hands upward in synchronized praise motion",
    ),
    "clap": MotionDirective(
        movement_type="clap",
        body_region="upper_body",
        camera_behavior="snap_zoom",
        energy=0.65,
        prompt_fragment="perform synchronized clap accents on beat",
    ),
    "walk": MotionDirective(
        movement_type="walk_cycle",
        body_region="legs",
        camera_behavior="tracking_dolly",
        energy=0.40,
        prompt_fragment="walk forward rhythmically with controlled momentum",
    ),
    "look back": MotionDirective(
        movement_type="look_back",
        body_region="head_shoulders",
        camera_behavior="shoulder_tracking",
        energy=0.52,
        prompt_fragment="turn and look back over shoulder in sync with lyric emphasis",
    ),
    "drop": MotionDirective(
        movement_type="drop_low",
        body_region="hips_legs",
        camera_behavior="downward_follow",
        energy=0.82,
        prompt_fragment="drop low with strong synchronized hip-driven motion",
    ),
    "twerk": MotionDirective(
        movement_type="hip_isolation",
        body_region="hips",
        camera_behavior="waist_tracking",
        energy=0.95,
        prompt_fragment="perform controlled hip isolation synchronized tightly to rhythm",
    ),
}


class MotionOntology:
    """Maps lyric phrases into motion and camera directives."""

    def resolve(self, lyric: str) -> MotionDirective:
        lowered = lyric.lower()

        for phrase, directive in ONTOLOGY.items():
            if phrase in lowered:
                return directive

        return DEFAULT_DIRECTIVE
