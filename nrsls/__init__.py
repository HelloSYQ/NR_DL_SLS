"""nrsls: an NR downlink system-level simulator built on ``nrdlsim``.

Packages
--------
config        scenario presets: UMa, UMi, RMa, InH (TR 38.901 clause 7.2)
topology      hexagonal / InH layouts, wrap-around, UT dropping
antenna       gNB panel + TXRU virtualisation (TR 38.901 7.3, TR 36.897)
propagation   pathloss, LOS probability, O2I loss, LSPs (TR 38.901 7.4, 7.5)
link          link budget, serving-cell association
engine        one drop (large-scale geometry) and the multi-drop driver
metrics       CDF / percentile KPIs, calibration comparison
plots         CDF plotting
"""

from .config.scenario import (ScenarioConfig, BSAntennaConfig, UEAntenna,
                              get_preset, PRESETS)
from .engine.drop import generate_drop, LargeScaleDrop
from .engine.simulator import run_large_scale, LargeScaleStats

__all__ = [
    "ScenarioConfig", "BSAntennaConfig", "UEAntenna", "get_preset", "PRESETS",
    "generate_drop", "LargeScaleDrop", "run_large_scale", "LargeScaleStats",
]

__version__ = "0.1.0"
