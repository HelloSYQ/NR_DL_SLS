"""Full-buffer SU-MIMO system simulation of one drop (phase 3).

Per drop:
  * the large-scale drop with its clusters (phase 2);
  * link set per UT: the serving cell plus the ``k_interferers`` strongest
    other cells as explicit MIMO links; every other cell adds its wideband
    received power as white interference;
  * the channel H[f, u, s] of every explicit link, per group of ``rb_step``
    RBs, refreshed every ``channel_update_slots`` slots (Doppler from the UT
    velocity), normalised to the noise power per RE.

Per slot:
  1. each cell schedules its RBGs: pending HARQ retransmissions first (same
     RBGs, rank, precoder and MCS), then proportional fair among its UTs
     with a CSI report, metric rank x log2(1 + SINR_subband) / R_avg;
     cells without a schedulable UT transmit a random rank-1 precoder
     (full-buffer interference);
  2. every UT whitens its channel with the interference covariance built
     from the precoders its explicit interferers actually use in this slot
     (MMSE-IRC) and gets its per-layer SINR on its RBGs;
  3. MIESM -> BLER (nrdlsim) decides each TB; chase combining adds the
     SINRs of retransmissions; OLLA follows first-transmission ACK/NACKs;
  4. every ``csi_period_slots`` each UT reports RI/PMI/CQI measured on the
     current channel and interference, usable ``csi_delay_slots`` later.

KPIs after ``warmup_slots``: UT throughput, UT spectral efficiency
(throughput / occupied bandwidth), cell spectral efficiency (sum throughput /
(cells x bandwidth)), first-transmission BLER, rank and MCS statistics.
"""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np

from nrdlsim import resource_grid as rg
from nrdlsim import tbs as tbs_mod
from nrdlsim.config import PDSCHConfig

from ..config.scenario import ScenarioConfig
from ..mac.link_adaptation import LinkAdaptation
from ..phy.csi import CSIProcessor
from ..phy.sinr import whitening
from ..propagation.fast_fading import channel_batch, concat_clusters, subset_clusters
from .drop import generate_drop
from .link import decode_tb, new_tb, tb_precoder


@dataclass
class FullBufferConfig:
    n_slots: int = 200
    warmup_slots: int = 40
    k_interferers: int = 8
    rb_step: int = 2                  # RBs per channel frequency point
    channel_update_slots: int = 10   # 5 ms at 30 kHz: 0.05 lambda at 3 km/h
    csi_period_slots: int = 10       # 5 ms CSI periodicity
    csi_delay_slots: int = 4
    rbg_size: int = 16                # also the CSI sub-band size
    codebook: str = "type1"           # 'type1', 'etype2', 'svd' or 'svd_rb'
    etype2_combo: int = 6             # Table 5.2.2.2.5-1 parameter combination
    n_beams: int = 4                  # Type-I beams kept after stage 1
    type1_subband_pmi: bool = True    # Type-I i2 per sub-band (else wideband)
    pmi_score_step: int = 4           # frequency subsampling of PMI scoring
    max_rank: int = 4
    mcs_table: int = 2
    target_bler: float = 0.1
    olla_step_db: float = 0.5
    harq_max_tx: int = 4
    harq_rtt_slots: int = 8
    pf_window_slots: float = 100.0
    link_batch: int = 128


@dataclass
class FullBufferResult:
    ue_throughput_bps: np.ndarray
    ue_se: np.ndarray                 # bit/s/Hz per UT
    cell_se: float                    # bit/s/Hz per cell
    bler_first: float
    mean_rank: float
    mean_mcs: float
    mean_pmi_bits: float
    serving_cell: np.ndarray
    geometry_db: np.ndarray
    bandwidth_hz: float
    n_cells: int


def _links(d, k):
    """(cells (U, 1+K), rest interference per RE in mW / received power)."""
    cg = d.coupling_gain_db                              # (C, U)
    order = np.argsort(-cg, axis=0)
    u = np.arange(d.ues.n)
    serving = d.serving_cell
    others = np.array([[c for c in order[:, i] if c != serving[i]][:k] for i in u])
    return np.column_stack([serving, others])


def run_full_buffer_drop(cfg: ScenarioConfig, fb: FullBufferConfig, rng
                         ) -> FullBufferResult:
    d = generate_drop(cfg, rng, keep_clusters=True)
    lay, n_ue = d.layout, d.ues.n
    car = cfg.carrier
    n_rb, scs, t_slot = car.n_size_grid, car.subcarrier_spacing_hz, car.slot_duration_s
    lam = 3e8 / cfg.carrier_freq_hz
    k = min(fb.k_interferers, lay.n_cells - 1)

    # --- power normalisation: everything in units of the noise per RE ---
    n0_mw = 10 ** ((-174 + 10 * np.log10(scs) + cfg.ue_noise_figure_db) / 10)
    p_re_mw = 10 ** (cfg.bs_tx_power_dbm / 10) / (12 * n_rb)
    cells = _links(d, k)                                  # (U, 1+K)
    sites = lay.cell_site[cells]
    uu = np.repeat(np.arange(n_ue)[:, None], k + 1, axis=1)
    loss_db = (d.pathloss_db + d.shadow_fading_db + d.penetration_db)[sites, uu]
    amp = np.sqrt(p_re_mw / n0_mw * 10 ** (-loss_db / 10))  # (U, 1+K)
    in_set = np.zeros((lay.n_cells, n_ue), bool)
    in_set[cells, uu] = True
    rest = np.sum(np.where(in_set, 0.0, p_re_mw * 10 ** (d.coupling_gain_db / 10)),
                  axis=0) / n0_mw                          # (U,)

    # --- clusters of every explicit link, in flat order l = u (1+K) + j ---
    flat_sites, flat_ues = sites.reshape(-1), uu.reshape(-1)
    parts, pos = [], np.empty(flat_sites.size, int)
    start = 0
    for s in range(lay.n_sites):
        m = np.nonzero(flat_sites == s)[0]
        if m.size:
            parts.append(subset_clusters(d.clusters[s], flat_ues[m]))
            pos[m] = start + np.arange(m.size)
            start += m.size
    cl_all = concat_clusters(parts)
    d.clusters = None                                     # free the rest
    bearing = lay.cell_bearing_deg[cells].reshape(-1)
    d3d = d.d3d_m[flat_sites, flat_ues]
    phi = rng.uniform(0, 2 * np.pi, n_ue)
    v = cfg.ue_speed_kmh / 3.6 * np.stack([np.cos(phi), np.sin(phi),
                                           np.zeros(n_ue)], -1)
    vel = v[flat_ues]

    # --- frequency grid, RBGs, sub-bands ---
    first_rb = np.arange(0, n_rb, fb.rb_step)
    nrb_f = np.minimum(fb.rb_step, n_rb - first_rb)
    f_hz = (first_rb + (nrb_f - 1) / 2 - (n_rb - 1) / 2) * 12 * scs
    rbg_f = first_rb // fb.rbg_size
    n_rbg = int(np.ceil(n_rb / fb.rbg_size))
    rb_per_rbg = np.bincount(np.arange(n_rb) // fb.rbg_size, minlength=n_rbg)
    n_f = len(f_hz)

    rbg_mask = rbg_f[None, :] == np.arange(n_rbg)[:, None]      # (n_rbg, F)
    bs, ue_ant = cfg.bs_antenna, cfg.ue_antenna
    n_s, n_u = bs.n_ports, ue_ant.n_ports

    def channels(t):
        h = np.empty((cl_all.valid.shape[0], n_f, n_u, n_s), np.complex64)
        for a in range(0, len(pos), fb.link_batch):
            idx = pos[a:a + fb.link_batch]
            sub = subset_clusters(cl_all, idx)
            flat = np.arange(a, min(a + fb.link_batch, len(pos)))
            h[flat] = channel_batch(sub, bearing[flat], bs, ue_ant, f_hz, t,
                                    vel[flat], lam, d3d[flat])
        h *= amp.reshape(-1)[:, None, None, None]
        return h.reshape(n_ue, k + 1, n_f, n_u, n_s)

    # --- PHY / MAC state ---
    pdsch = PDSCHConfig(num_rb=n_rb)
    n_re = tbs_mod.re_per_rb(pdsch.num_symbols, rg.dmrs_re_per_rb(pdsch), pdsch.n_oh)
    la = LinkAdaptation(n_ue, fb.mcs_table, fb.target_bler, n_re, fb.olla_step_db)
    proc = CSIProcessor(bs.Np, bs.Mp, 4, 4 if bs.Mp > 1 else 1,
                        codebook=fb.codebook,
                        max_rank=min(fb.max_rank, n_u), mcs_table=fb.mcs_table,
                        target_bler=fb.target_bler, n_re_per_rb=n_re,
                        n_beams=fb.n_beams, score_step=fb.pmi_score_step,
                        etype2_combo=fb.etype2_combo,
                        pmi_subband=fb.type1_subband_pmi)
    pending = [[] for _ in range(n_ue)]                   # (avail, report, sinr_sb)
    current = [None] * n_ue
    pf_avg = np.full(n_ue, 1.0)
    harq = []                                             # pending retransmissions
    bits = np.zeros(n_ue)
    n_first = n_nack = 0
    rank_log, mcs_log, bits_log = [], [], []
    ue_of_cell = [np.nonzero(d.serving_cell == c)[0] for c in range(lay.n_cells)]
    h = None

    for slot in range(fb.n_slots):
        if slot % fb.channel_update_slots == 0:
            h = channels(slot * t_slot)
        for u in range(n_ue):                             # CSI becoming usable
            while pending[u] and pending[u][0][0] <= slot:
                current[u] = pending[u].pop(0)[1:]

        # 1. scheduling
        w_cell = np.zeros((lay.n_cells, n_f, n_s, 4), np.complex64)
        txs = []
        due = [tb for tb in harq if tb["due"] <= slot]
        harq = [tb for tb in harq if tb["due"] > slot]
        for c in range(lay.n_cells):
            free = np.ones(n_rbg, bool)
            busy = set()
            for tb in [t for t in due if t["cell"] == c]:
                if free[tb["rbgs"]].all():
                    free[tb["rbgs"]] = False
                    busy.add(tb["ue"])
                    txs.append(tb)
                else:
                    tb["due"] = slot + 1
                    harq.append(tb)
            cand = [u for u in ue_of_cell[c] if current[u] is not None and u not in busy]
            if cand and free.any():
                met = np.array([current[u][0].rank * np.log2(1 + 10 ** (current[u][1] / 10))
                                / pf_avg[u] for u in cand])        # (n_cand, n_rbg)
                owner = np.where(free, np.argmax(met, axis=0), -1)
                for i, u in enumerate(cand):
                    rbgs = np.nonzero(owner == i)[0]
                    if rbgs.size == 0:
                        continue
                    rep, sinr_sb = current[u]
                    txs.append(new_tb(la, u, c, rep, sinr_sb, rbgs, rb_per_rbg,
                                      n_re, fb.mcs_table, slot))
            elif not any(t["cell"] == c for t in txs) and ue_of_cell[c].size:
                g = rng.normal(size=(n_s,)) + 1j * rng.normal(size=(n_s,))
                w_cell[c, :, :, 0] = g / np.linalg.norm(g)
        for tb in txs:
            fm = rbg_mask[tb["rbgs"]].any(axis=0)
            w_cell[tb["cell"], fm, :, :tb["rank"]] = tb_precoder(tb, fm, rbg_f)

        # 2. interference covariance and whitening, per UT and frequency
        gi = h[:, 1:] @ w_cell[cells[:, 1:]]               # (U, K, F, Ua, 4)
        x = np.moveaxis(gi, 1, 3).reshape(n_ue, n_f, n_u, -1)   # (U, F, Ua, 4K)
        r_cov = (x @ np.conj(np.swapaxes(x, -1, -2))
                 + (1.0 + rest)[:, None, None, None] * np.eye(n_u))
        lw = whitening(r_cov.astype(np.complex128))       # (U, F, Ua, Ua)
        hw = lw @ h[:, 0]                                 # (U, F, Ua, S)

        # 3. decode
        for tb in txs:
            u = tb["ue"]
            fm = rbg_mask[tb["rbgs"]].any(axis=0)
            first = tb["ntx"] == 0
            ok = decode_tb(tb, hw[u], fm, rbg_f, nrb_f, rng)
            if first:
                la.update(u, ok)
                pf_avg[u] += tb["bits"] / fb.pf_window_slots
                if slot >= fb.warmup_slots:
                    n_first += 1
                    n_nack += int(not ok)
                    rank_log.append(tb["rank"])
                    mcs_log.append(tb["info"].index)
            if ok:
                if slot >= fb.warmup_slots:
                    bits[u] += tb["bits"]
            elif tb["ntx"] < fb.harq_max_tx:
                tb["due"] = slot + fb.harq_rtt_slots
                harq.append(tb)
        pf_avg *= 1 - 1 / fb.pf_window_slots

        # 4. CSI reports
        if slot % fb.csi_period_slots == 0:
            for u in range(n_ue):
                rep = proc.select(hw[u], rbg_f, fb.rb_step, slot)
                bits_log.append(rep.pmi_bits)
                sinr_sb = la.cqi_sinr_db(rep.cqi_sb, rep.rank, fb.rbg_size)
                pending[u].append((slot + fb.csi_delay_slots, rep, sinr_sb))

    t_meas = (fb.n_slots - fb.warmup_slots) * t_slot
    bw = n_rb * 12 * scs
    tput = bits / t_meas
    return FullBufferResult(
        ue_throughput_bps=tput, ue_se=tput / bw,
        cell_se=float(tput.sum() / (lay.n_cells * bw)),
        bler_first=n_nack / max(n_first, 1),
        mean_rank=float(np.mean(rank_log)) if rank_log else 0.0,
        mean_mcs=float(np.mean(mcs_log)) if mcs_log else 0.0,
        mean_pmi_bits=float(np.mean(bits_log)) if bits_log else 0.0,
        serving_cell=d.serving_cell, geometry_db=d.geometry_db,
        bandwidth_hz=bw, n_cells=lay.n_cells)


def _fb_worker(args):
    cfg, fb, seed, i = args
    return run_full_buffer_drop(cfg, fb, np.random.default_rng([seed, i]))


def run_full_buffer(cfg: ScenarioConfig, fb: FullBufferConfig, n_drops: int,
                    seed: int = 1, n_jobs: int = 1) -> dict:
    """Several independent drops; UT statistics pooled over drops."""
    from .simulator import parallel_map
    res = parallel_map(_fb_worker, [(cfg, fb, seed, i) for i in range(n_drops)],
                       n_jobs)
    ue_se = np.concatenate([r.ue_se for r in res])
    return {
        "drops": res,
        "ue_se": ue_se,
        "cell_se": float(np.mean([r.cell_se for r in res])),
        "ue_se_p5": float(np.percentile(ue_se, 5)),
        "ue_se_p50": float(np.percentile(ue_se, 50)),
        "bler_first": float(np.mean([r.bler_first for r in res])),
        "mean_rank": float(np.mean([r.mean_rank for r in res])),
        "mean_mcs": float(np.mean([r.mean_mcs for r in res])),
        "mean_pmi_bits": float(np.mean([r.mean_pmi_bits for r in res])),
    }

