"""UT dropping (TR 38.901 clause 7.2, TR 36.873 for UT heights).

Outdoor-BS scenarios (UMa, UMi, RMa):
  * ``ue_per_cell`` UTs uniformly in each sector rhombus, at least
    ``min_d2d_m`` (2-D) from their own site;
  * a UT is indoor (O2I) with probability ``indoor_ratio``.  Indoor UTs sit in
    buildings of N_fl ~ U{n_floors} floors on floor n_fl ~ U{1..N_fl},
    h_UT = 3 (n_fl - 1) + 1.5 m, with an indoor distance
    d2D-in = min(U(0, d_max), U(0, d_max)) (TR 38.901 Table 7.4.3-2);
  * an indoor UT is in a high-loss building with probability
    ``o2i_high_loss_ratio`` (only for ``o2i_model='mixed'``);
  * an outdoor UT is inside a car with probability ``in_car_ratio``.

InH: ``ue_per_cell * n_cells`` UTs uniformly over the hall at h_UT = 1 m.
"""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np

from ..config.scenario import ScenarioConfig
from .layout import Layout


@dataclass
class UEs:
    xy: np.ndarray            # (U, 2) position [m]
    h_m: np.ndarray           # (U,) antenna height [m]
    o2i: np.ndarray           # (U,) bool: indoor UT served by outdoor BSs
    floor: np.ndarray         # (U,) int: floor number n_fl (1 = ground)
    d2d_in_m: np.ndarray      # (U,) UT-specific indoor distance (0 outdoor)
    high_loss: np.ndarray     # (U,) bool: high-loss building (O2I only)
    in_car: np.ndarray        # (U,) bool
    drop_cell: np.ndarray     # (U,) int: cell whose area the UT was dropped in

    @property
    def n(self) -> int:
        return len(self.xy)


def _drop_in_rhombus(layout: Layout, cell: int, n: int, min_d: float, rng):
    o, a, b = layout.sector_rhombus(cell)
    out = np.empty((0, 2))
    while len(out) < n:
        st = rng.random((2 * (n - len(out)) + 4, 2))
        xy = o + st[:, :1] * a + st[:, 1:] * b
        keep = np.hypot(*(xy - o).T) >= min_d
        out = np.vstack([out, xy[keep]])
    return out[:n]


def drop_ues(cfg: ScenarioConfig, layout: Layout, rng) -> UEs:
    if layout.kind == "hall":
        n = cfg.ue_per_cell * layout.n_cells
        length, width = layout.hall_m
        xy = (rng.random((n, 2)) - 0.5) * np.array([length, width])
        # nearest TRP as the nominal drop cell (statistics only)
        d = np.hypot(*(xy[None, :, :] - layout.site_xy[:, None, :]).transpose(2, 0, 1))
        drop_cell = np.argmin(d, axis=0)
        z = np.zeros(n, bool)
        return UEs(xy=xy, h_m=np.full(n, cfg.h_ut_outdoor_m), o2i=z,
                   floor=np.ones(n, int), d2d_in_m=np.zeros(n),
                   high_loss=z.copy(), in_car=z.copy(), drop_cell=drop_cell)

    xy = np.vstack([_drop_in_rhombus(layout, c, cfg.ue_per_cell,
                                     cfg.min_d2d_m, rng)
                    for c in range(layout.n_cells)])
    drop_cell = np.repeat(np.arange(layout.n_cells), cfg.ue_per_cell)
    n = len(xy)

    o2i = rng.random(n) < cfg.indoor_ratio
    lo, hi = cfg.n_floors
    n_fl = rng.integers(lo, hi + 1, size=n)                 # building floors
    floor = np.floor(rng.random(n) * n_fl).astype(int) + 1  # U{1..N_fl}
    floor = np.where(o2i, floor, 1)
    h = np.where(o2i, 3.0 * (floor - 1) + 1.5, cfg.h_ut_outdoor_m)

    d_in = cfg.d2d_in_max_m * rng.random((n, 2)).min(axis=1)
    d_in = np.where(o2i, d_in, 0.0)

    if cfg.o2i_model == "high":
        high = o2i.copy()
    elif cfg.o2i_model == "mixed":
        high = o2i & (rng.random(n) < cfg.o2i_high_loss_ratio)
    else:
        high = np.zeros(n, bool)

    in_car = ~o2i & (rng.random(n) < cfg.in_car_ratio)
    return UEs(xy=xy, h_m=h, o2i=o2i, floor=floor, d2d_in_m=d_in,
               high_loss=high, in_car=in_car, drop_cell=drop_cell)
