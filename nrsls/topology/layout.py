"""Network layouts: the hexagonal macro grid and the InH-Office hall.

Hexagonal grid (TR 38.901 Table 7.2-1, TR 36.814 A.2.1.1)
---------------------------------------------------------
Sites sit on a hexagonal lattice with spacing ISD; ``n_rings`` rings around
the centre site give 1 + 3 n (n + 1) sites (19 for two rings).  Neighbouring
sites are at azimuths 0, 60, ..., 300 deg, so the three sector boresights
30, 150 and 270 deg each point at a corner of the site hexagon.  Each sector
(cell) covers the rhombus between its site and that corner.

Wrap-around: the whole cluster tiles the plane under the translations
t = (n+1) v1 + n v2 and its rotations by multiples of 60 deg, where v1, v2
are the lattice vectors.  Each UT sees every site through its closest copy,
so every UT has a full ring of interferers wherever it is in the cluster.

InH-Office (TR 38.901 Table 7.2-2)
----------------------------------
A 120 m x 50 m hall with 12 ceiling TRPs on a 6 x 2 grid, 20 m apart.
"""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np

from ..config.scenario import ScenarioConfig


@dataclass
class Layout:
    kind: str                       # 'hex' or 'hall'
    site_xy: np.ndarray             # (S, 2) site positions [m]
    site_height_m: np.ndarray       # (S,)
    cell_site: np.ndarray           # (C,) site of each cell
    cell_bearing_deg: np.ndarray    # (C,) sector boresight azimuth
    wrap_offsets: np.ndarray        # (K, 2) copies of the cluster, incl. (0, 0)
    isd_m: float
    hall_m: tuple = (0.0, 0.0)      # hall length x width ('hall' only)

    @property
    def n_sites(self) -> int:
        return len(self.site_xy)

    @property
    def n_cells(self) -> int:
        return len(self.cell_site)

    def virtual_site_xy(self, ue_xy: np.ndarray) -> np.ndarray:
        """Closest copy of every site as seen from every UT, shape (S, U, 2).

        Without wrap-around this is just the site position.
        """
        ue_xy = np.asarray(ue_xy, float)
        cand = (self.site_xy[:, None, :] + self.wrap_offsets[None, :, :])
        # (S, K, U, 2) displacement from each candidate copy to each UT
        diff = ue_xy[None, None, :, :] - cand[:, :, None, :]
        k = np.argmin(np.einsum("skud,skud->sku", diff, diff), axis=1)
        return np.take_along_axis(cand, k[:, :, None], axis=1)

    def sector_rhombus(self, cell: int):
        """(origin, edge_a, edge_b) of a hex cell: origin + s a + t b, s,t in [0,1]."""
        o = self.site_xy[self.cell_site[cell]]
        r = self.isd_m / np.sqrt(3.0)          # site-hexagon circumradius
        b = np.deg2rad(self.cell_bearing_deg[cell])
        a = r * np.array([np.cos(b - np.pi / 3), np.sin(b - np.pi / 3)])
        c = r * np.array([np.cos(b + np.pi / 3), np.sin(b + np.pi / 3)])
        return o, a, c


def hex_site_positions(isd: float, n_rings: int) -> np.ndarray:
    """Hexagonal lattice sites within ``n_rings`` of the origin, ring by ring."""
    pts = []
    for q in range(-n_rings, n_rings + 1):
        for r in range(-n_rings, n_rings + 1):
            if max(abs(q), abs(r), abs(q + r)) <= n_rings:
                ring = max(abs(q), abs(r), abs(q + r))
                xy = isd * np.array([q + r / 2.0, r * np.sqrt(3.0) / 2.0])
                ang = np.arctan2(xy[1], xy[0]) % (2 * np.pi)
                pts.append((ring, round(ang, 9), xy))
    pts.sort(key=lambda p: (p[0], p[1]))
    return np.array([p[2] for p in pts])


def hex_wrap_offsets(isd: float, n_rings: int) -> np.ndarray:
    """The origin plus the six translations that tile the plane with the cluster."""
    n = n_rings
    t = isd * np.array([(n + 1) + n / 2.0, n * np.sqrt(3.0) / 2.0])
    offs = [np.zeros(2)]
    for k in range(6):
        a = k * np.pi / 3
        rot = np.array([[np.cos(a), -np.sin(a)], [np.sin(a), np.cos(a)]])
        offs.append(rot @ t)
    return np.array(offs)


def build_layout(cfg: ScenarioConfig) -> Layout:
    if cfg.is_indoor_scenario:
        return _hall_layout(cfg)
    sites = hex_site_positions(cfg.isd_m, cfg.n_rings)
    n_sec = len(cfg.sector_bearings_deg)
    offsets = (hex_wrap_offsets(cfg.isd_m, cfg.n_rings) if cfg.wrap_around
               else np.zeros((1, 2)))
    return Layout(
        kind="hex",
        site_xy=sites,
        site_height_m=np.full(len(sites), cfg.h_bs_m),
        cell_site=np.repeat(np.arange(len(sites)), n_sec),
        cell_bearing_deg=np.tile(np.asarray(cfg.sector_bearings_deg, float),
                                 len(sites)),
        wrap_offsets=offsets,
        isd_m=cfg.isd_m,
    )


def _hall_layout(cfg: ScenarioConfig) -> Layout:
    nx, ny = cfg.inh_trp_grid
    xs = (np.arange(nx) - (nx - 1) / 2.0) * cfg.isd_m
    ys = (np.arange(ny) - (ny - 1) / 2.0) * cfg.isd_m
    sites = np.array([[x, y] for y in ys for x in xs])
    n_sec = len(cfg.sector_bearings_deg)
    return Layout(
        kind="hall",
        site_xy=sites,
        site_height_m=np.full(len(sites), cfg.h_bs_m),
        cell_site=np.repeat(np.arange(len(sites)), n_sec),
        cell_bearing_deg=np.tile(np.asarray(cfg.sector_bearings_deg, float),
                                 len(sites)),
        wrap_offsets=np.zeros((1, 2)),
        isd_m=cfg.isd_m,
        hall_m=tuple(cfg.inh_hall_m),
    )
