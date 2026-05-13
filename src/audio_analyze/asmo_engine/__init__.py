"""Adaptive Semantic Motion Orchestration utilities.

ASMO is an additive control layer for the Audio-Analyze LTX pipeline.
It converts lyric text plus audio analysis into millisecond-level motion,
camera, and LTX prompt timeline directives.

This package produces timing-aware choreography and camera metadata
that can be injected into existing LTX scene plans.
"""

from .asmo_engine import ASMOEngine, generate_asmo_timeline

__all__ = ["ASMOEngine", "generate_asmo_timeline"]
