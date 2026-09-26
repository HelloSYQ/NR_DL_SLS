"""One simulation drop: geometry, large-scale parameters and port-0 RSRP.

TR 38.901 clause 7.5:

  1. layout, UT drop (indoor/outdoor, floors, cars) and wrap-around;
  2. LOS state per link (Table 7.4.2-1, outdoor distance for O2I UTs);
  3. basic pathloss (Table 7.4.1-1) + O2I / in-car penetration (7.4.3);
  4. the seven LSPs (SF, K, DS, ASD, ASA, ZSD, ZSA), spatially and
     cross-correlated, per site and link condition;
  5-10. (``coupling_model='multipath'``) clusters and rays per link;

then the port-0 gain of every cell toward every UT -- the ray-summed RSRP
of TR 36.873 eq. (8.1-1), or the gain toward the LOS direction for
``coupling_model='los'`` -- the coupling gain, the serving cell (strongest
RSRP) and the geometry.  Link quantities are per site
(S, U): co-sited sectors share the LOS state, pathloss and shadowing.  Cell
quantities are per cell (C, U).
"""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np

from ..antenna.array import BSAntenna
from ..config.scenario import ScenarioConfig
from ..link import association, link_budget
from ..propagation import lsp, o2i as o2i_mod, pathloss
from ..link.rsrp import multipath_gain
from ..propagation.clusters import generate_clusters
from ..propagation.los import los_probability
from ..topology.layout import Layout, build_layout
from ..topology.ue_drop import UEs, drop_ues


@dataclass
class LargeScaleDrop:
    cfg: ScenarioConfig
    layout: Layout
    ues: UEs
    # per link (S, U)
    d2d_m: np.ndarray
    d3d_m: np.ndarray
    az_deg: np.ndarray            # LOS departure azimuth (GCS)
    zen_deg: np.ndarray           # LOS departure zenith (GCS)
    los: np.ndarray               # LOS state of the (outdoor part of the) link
    condition: np.ndarray         # pathloss.LOS / NLOS / O2I
    pathloss_db: np.ndarray       # PL_b
    shadow_fading_db: np.ndarray
    penetration_db: np.ndarray    # O2I + in-car loss
    lsps: lsp.LSPs                # all seven LSPs per link
    # per cell (C, U)
    bs_gain_db: np.ndarray        # port-0 antenna (+ multipath) gain
    coupling_gain_db: np.ndarray
    rx_power_dbm: np.ndarray
    # per UT
    serving_cell: np.ndarray
    geometry_db: np.ndarray
    noise_dbm: float

    @property
    def serving_site(self) -> np.ndarray:
        return self.layout.cell_site[self.serving_cell]

    def per_ut(self, link_quantity: np.ndarray) -> np.ndarray:
        """Value of a (S, U) link quantity on each UT's serving link."""
        return link_quantity[self.serving_site, np.arange(self.ues.n)]

    @property
    def serving_coupling_gain_db(self) -> np.ndarray:
        return self.coupling_gain_db[self.serving_cell, np.arange(self.ues.n)]


def generate_drop(cfg: ScenarioConfig, rng) -> LargeScaleDrop:
    layout = build_layout(cfg)
    ues = drop_ues(cfg, layout, rng)
    n_sites, n_ue = layout.n_sites, ues.n

    # --- geometry toward the closest copy of every site ---
    vxy = layout.virtual_site_xy(ues.xy)                     # (S, U, 2)
    dx = ues.xy[None, :, 0] - vxy[..., 0]
    dy = ues.xy[None, :, 1] - vxy[..., 1]
    d2d = np.hypot(dx, dy)
    h_bs = np.broadcast_to(layout.site_height_m[:, None], d2d.shape)
    h_ut = np.broadcast_to(ues.h_m[None, :], d2d.shape)
    d3d = np.sqrt(d2d ** 2 + (h_bs - h_ut) ** 2)
    az = np.rad2deg(np.arctan2(dy, dx))
    zen = np.rad2deg(np.arccos((h_ut - h_bs) / d3d))
    o2i = np.broadcast_to(ues.o2i[None, :], d2d.shape)

    # --- indoor distance (UT-specific, or link-specific for 'legacy') ---
    if cfg.o2i_model == "legacy":
        d_in = cfg.d2d_in_max_m * rng.random((n_sites, n_ue))
        d_in = np.where(o2i, d_in, 0.0)
    else:
        d_in = np.broadcast_to(ues.d2d_in_m[None, :], d2d.shape)
    d2d_out = np.maximum(d2d - d_in, 0.0)

    # --- LOS state (outdoor part), pathloss ---
    los = rng.random(d2d.shape) < los_probability(cfg.scenario, d2d_out, h_ut)
    fam = cfg.family
    h_e = pathloss.sample_uma_h_e(d2d, h_ut, rng) if fam == "uma" else 1.0
    pl = pathloss.basic_pathloss_db(
        fam, los, d2d, d3d, h_bs, h_ut, cfg.carrier_freq_hz, h_e=h_e,
        building_height=cfg.building_height_m,
        street_width=cfg.street_width_m,
        rma_nlos_offset_db=cfg.rma_nlos_offset_db)

    # --- large-scale parameters (SF, K, DS, ASD, ASA, ZSD, ZSA) ---
    cond = pathloss.link_condition(los, o2i)
    sigma = pathloss.shadow_fading_std_db(fam, cond, d2d, h_bs, h_ut,
                                          cfg.carrier_freq_hz)
    lsps = lsp.draw_lsps(fam, cfg.carrier_freq_ghz, cond, los, d2d, h_bs, h_ut,
                         sigma if cfg.shadow_fading else np.zeros(d2d.shape),
                         ues.xy, ues.floor, rng, spatial=cfg.sf_spatial_correlation)
    sf = lsps.sf_db

    # --- penetration losses ---
    if cfg.o2i_model == "legacy":
        pen = o2i_mod.legacy_o2i_loss_db(o2i, d_in)
    else:
        pen = np.broadcast_to(o2i_mod.o2i_loss_db(
            cfg.carrier_freq_ghz, ues.o2i, ues.high_loss, ues.d2d_in_m, rng),
            d2d.shape)
    car = o2i_mod.in_car_loss_db(ues.in_car, rng, *cfg.car_loss_db)
    pen = pen + car[None, :]

    # --- per-cell port-0 gain toward every UT ---
    ant = BSAntenna(cfg.bs_antenna)
    site = layout.cell_site
    gain = np.empty((layout.n_cells, n_ue))
    if cfg.coupling_model == "los":
        for c, s in enumerate(site):
            gain[c] = ant.port_gain_db(az[s], zen[s], layout.cell_bearing_deg[c])
    else:
        for s in range(n_sites):
            ls = lsp.LSPs(**{k: np.broadcast_to(v, d2d.shape)[s]
                             for k, v in vars(lsps).items()})
            cl = generate_clusters(fam, cfg.carrier_freq_ghz, cond[s], ls,
                                   az[s], zen[s], rng)
            for c in np.nonzero(site == s)[0]:
                b = layout.cell_bearing_deg[c]
                g = multipath_gain(
                    cl, lambda a, z, b=b: ant.port0_field(a, z, b),
                    cfg.ue_antenna.P)
                gain[c] = 10 * np.log10(np.maximum(g, 1e-30))
    ue_gain = cfg.ue_antenna.gain_dbi if cfg.coupling_model == "los" else 0.0
    cg = gain + ue_gain - (pl + sf + pen)[site]
    rx = cfg.bs_tx_power_dbm + cg

    serving = association.associate(cg)
    noise = link_budget.noise_power_dbm(cfg.bandwidth_hz, cfg.ue_noise_figure_db)
    geom = link_budget.geometry_db(rx, serving, noise)

    return LargeScaleDrop(
        cfg=cfg, layout=layout, ues=ues, d2d_m=d2d, d3d_m=d3d, az_deg=az,
        zen_deg=zen, los=los, condition=cond, pathloss_db=pl,
        shadow_fading_db=sf, penetration_db=np.asarray(pen), lsps=lsps,
        bs_gain_db=gain, coupling_gain_db=cg, rx_power_dbm=rx,
        serving_cell=serving, geometry_db=geom, noise_dbm=noise)
