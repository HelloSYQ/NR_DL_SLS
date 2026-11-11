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

Codeword-to-layer mapping (``cw_mapping``, SU-MIMO): 'alt1' is NR, one
codeword up to rank 4; 'alt2' allows up to 2 codewords and 'alt3' one per
layer (``nrdlsim.layer_mapping.layer_groups``).  With more than one
codeword the report carries per-codeword CQIs, RI maximises the sum over
codewords, every codeword is its own TB with its own MCS, OLLA loop
(``olla_per_rank``: also per rank) and HARQ process, and the PF metric sums
the codewords' rates; see ``engine/link.py`` for retransmissions
(``harq_refill``: whether a retransmission refills its decoded codewords).
``ri_olla`` and ``ri_sic_propagation`` couple the UT's rank selection to
OLLA and to SIC error propagation (``phy/csi.py``).  Two
references for comparing mappings: ``receiver='sic'`` (codeword-level
MMSE-SIC: the codewords are decoded in index order, each one that decodes
is cancelled, and the CQIs are reported for it) and ``ideal_la`` (each new
TB's MCS is the highest meeting the BLER target on the SINR it actually
gets; with SIC, on its SINR once the earlier codewords are cancelled).

KPIs after ``warmup_slots``: UT throughput, UT spectral efficiency
(throughput / ``channel_bandwidth_hz``, or the occupied bandwidth if that is
None), cell spectral efficiency (sum throughput / (cells x the same
bandwidth)), first-transmission BLER, rank and MCS statistics.
"""

from __future__ import annotations

from dataclasses import dataclass, field

import numpy as np

from nrdlsim import mcs_tables
from nrdlsim import resource_grid as rg
from nrdlsim import tbs as tbs_mod
from nrdlsim.config import PDSCHConfig

from ..config.scenario import ScenarioConfig
from ..mac.link_adaptation import LinkAdaptation
from ..phy.csi import CSIProcessor
from ..phy.sinr import whitening
from ..propagation.fast_fading import channel_batch, concat_clusters, subset_clusters
from .drop import generate_drop
from ..mac.mu_mimo import greedy_pairing, unit_columns
from ..phy.sinr import evm_limited, mmse_sinr
from .link import (decode_tb, harq_units, ideal_mcs, make_tb, new_txs, retransmission,
                   sic_layer_sinr, tb_precoder)


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
    codebook: str = "type1"           # 'type1', 'etype2', 'svd', 'svd_sb', 'svd_rb'
    etype2_combo: int = 6             # Table 5.2.2.2.5-1 parameter combination
    n_beams: int = 4                  # Type-I beams kept after stage 1
    type1_subband_pmi: bool = True    # Type-I i2 per sub-band (else wideband)
    pmi_score_step: int = 4           # frequency subsampling of PMI scoring
    max_rank: int = 4
    # 1: 64QAM, 2: 256QAM, 4: 1024QAM (TS 38.214 Table 5.1.3.1-4, the Rel-17
    # table of mac/mcs_table4.py), each with its CQI table
    mcs_table: int = 2
    # error-vector magnitude [%] of the link (transmitter and receiver
    # impairments together): every post-equaliser SINR, in the CSI and in the
    # decoding, becomes 1 / (1 / SINR + EVM^2), at most 1 / EVM^2.  0: none,
    # SINRs are unbounded.  TS 38.104 lets a BS have 3.5 % with 256QAM and
    # 2.5 % with 1024QAM (ceilings of 29.1 and 32.0 dB); 1024QAM needs 28 to
    # 32 dB, so evaluate it with an EVM
    evm_percent: float = 0.0
    target_bler: float = 0.1
    olla_step_db: float = 0.5
    # OLLA fast start (mac/link_adaptation.py): the first olla_fast_samples
    # ACK/NACKs of a loop (since the UT arrived, or the drop began) move it
    # olla_fast_gain times the normal steps, same ratio and so same target,
    # for codewords >= olla_fast_min_cw (0: every loop, NR's included; 1: all
    # but codeword 0, which carries the strongest layer)
    olla_fast_gain: float = 1.0
    olla_fast_samples: int = 0
    olla_fast_min_cw: int = 0
    # OLLA warm start (FTP model 1): a new UT's loops start from the mean
    # offset of the other UTs' loops (same codeword and rank) that have had at
    # least olla_warm_samples ACK/NACKs, instead of 0 dB (0: off)
    olla_warm_samples: int = 0
    harq_max_tx: int = 4
    harq_rtt_slots: int = 8
    pf_window_slots: float = 100.0
    link_batch: int = 128
    # overhead beyond DM-RS: PDCCH symbols at the slot start, and the average
    # CSI-RS / CSI-IM / TRS / SSB REs per PRB and slot (TBS N_oh)
    pdcch_symbols: int = 1            # PDSCH = symbols pdcch_symbols..13
    overhead_re_per_prb: int = 0
    # MU-MIMO (mac/mu_mimo.py): greedy pairing per RBG, ZF on the reports
    mu_mimo: bool = False
    mu_max_ues: int = 6               # co-scheduled UTs per RBG
    # total layers per RBG: up to 8 with type-1, up to 12 with type-2
    # double-symbol DM-RS, both at 24 REs/PRB
    mu_max_layers: int = 12
    mu_max_rank: int = 2              # layers per co-scheduled UT
    # > 4 layers on an RBG need DM-RS ports 4-7 (type 1, double symbol).  With
    # a double-symbol front-loaded DM-RS and no additional position (the
    # low-mobility configuration) that costs the same 24 REs/PRB as the
    # single-symbol + 1 additional DM-RS of <= 4 layers, so no extra overhead
    # by default; True charges double-symbol + 1 additional pair (48 REs)
    mu_dmrs_overhead: bool = False
    mu_precoder: str = "rzf"          # 'rzf' or 'zf' on the reports
    # codeword-to-layer mapping (SU-MIMO): 'alt1' = 'nr' (1 CW up to rank 4),
    # 'alt2' = 'lte' (<= 2 CW, TS 36.211 Table 6.3.3.2-1), 'alt3' =
    # 'per_layer' (one CW per layer)
    cw_mapping: str = "alt1"
    olla_per_rank: bool = False       # OLLA loop per UT, rank and codeword
    # SU retransmissions: False keeps the first transmission's precoder (and
    # a refilled codeword its first-transmission CQI); True re-precodes the
    # PDSCH with the UT's current report if its rank matches
    harq_adaptive: bool = False
    # multi-codeword retransmissions: 'fresh' refills a decoded codeword's
    # layers with a new TB only if the UT's current report has the
    # transmission's rank and the UT has data left (FTP), else disables the
    # codeword and retransmits the rest alone (engine/link.py
    # retransmission); 'always' refills every decoded codeword, even with
    # stale CSI or padding only, which can keep a transmission in HARQ for
    # hundreds of slots (the behaviour before 2026-11-06)
    harq_refill: str = "fresh"
    # SU retransmission timing and resources: 'sync' sends a due
    # retransmission one round trip (harq_rtt_slots) after the failed
    # transmission, before new data, on the RBGs of its first transmission
    # (a slot later if they are taken); 'async' (asynchronous, adaptive in
    # frequency) gives a due retransmission priority but lets it take any free
    # RBGs: as many as before, the best ones for the UT's current report
    # (its own RBGs if the report's rank differs), and waits a slot when not
    # enough are free.  MCS, TBS and rank stay, so chase combining continues
    harq_mode: str = "sync"
    # rank adaptation (phy/csi.py): ri_olla makes the UT's RI metric use its
    # CQIs after the gNB's OLLA offsets (per rank with olla_per_rank), an
    # idealised coupling of rank adaptation and OLLA; ri_sic_propagation
    # weights codeword k of a SIC receiver by (1 - target_bler)^k, the
    # chance that the codewords before it decode
    ri_olla: bool = False
    ri_sic_propagation: bool = False
    # SU receiver: 'irc' (MMSE-IRC) or 'sic' (codeword-level MMSE-SIC, ideal
    # cancellation of the codewords that decode, decoded in index order; the
    # UT reports each codeword's CQI after the earlier ones are cancelled).
    # With one codeword both are MMSE-IRC
    receiver: str = "irc"
    # SIC: the OLLA loop of a codeword skips the transmissions in which an
    # earlier codeword failed (its NACK is then error propagation, not CQI
    # error); the gNB sees every codeword's ACK/NACK
    olla_sic_conditional: bool = False
    # ideal link adaptation (a reference, SU): every new TB takes the highest
    # MCS meeting target_bler on the SINR it actually gets (OLLA unused)
    ideal_la: bool = False
    # traffic (SU): 'full_buffer', or 'ftp3', FTP model 3 (TR 36.814 A.2.1.3.2,
    # TR 38.802): files of ftp_file_bytes arrive at every UT as a Poisson
    # process of ftp_rate_per_ue files/s; see run_full_buffer_drop
    traffic: str = "full_buffer"
    ftp_file_bytes: float = 0.5e6
    ftp_rate_per_ue: float = 0.0
    # FTP: files arriving in the last ftp_drain_slots are served, not counted
    ftp_drain_slots: int = 0
    # 'ftp1', FTP model 1 (TR 36.814 A.2.1.3.1): UTs arrive as a Poisson process
    # of ftp1_rate_per_cell per cell, at uniformly random places, each
    # downloads one file of ftp_file_bytes and leaves.  An arrival takes an
    # idle UT of the drop (a pool of ue_per_cell per cell, which should be
    # well above the number of UTs active at once) and starts it with fresh
    # OLLA and an aperiodic CSI report
    ftp1_rate_per_cell: float = 0.0


# maximum codewords per transmission.  Up to rank 4 the three splits are
#   'nr'        one codeword on all layers (TS 38.211 Table 7.3.1.3-1);
#   'lte'       {1} / {1,1} / {1,2} / {2,2} for ranks 1-4, the LTE mapping of
#               TS 36.211 Table 6.3.3.2-1 (and the NR split of ranks 5-8);
#   'lte_twisted' as 'lte' but {1,3} at rank 4: codeword 0 on layer 0 (the
#               strongest), codeword 1 on layers 1-3;
#   'per_layer' one codeword per layer.
CW_MAPPINGS = {"alt1": 1, "alt2": 2, "alt3": 4, "nr": 1, "lte": 2, "per_layer": 4,
               "lte_twisted": 2, "alt2t": 2}


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
    mean_ues_per_rbg: float = 1.0     # co-scheduled UTs per used RBG
    mean_layers_per_rbg: float = 0.0  # layers per used RBG
    mu_tb_fraction: float = 0.0       # first transmissions with co-scheduling
    retx_rbg_fraction: float = 0.0    # RBG-slots carrying retransmissions
    retx_moved_fraction: float = 0.0  # retransmissions sent on other RBGs (async HARQ)
    mu_sinr_error_db: float = 0.0     # gNB MU SINR estimate - actual (mean)
    mean_codewords: float = 1.0       # codewords per new transmission
    rank_hist: tuple = ()             # share of new transmissions at rank 1..4
    bler_first_cw: tuple = ()         # first-transmission BLER per codeword index
    # share of first-transmission TBs with QPSK / 16QAM / 64QAM / 256QAM / 1024QAM
    modulation_share: tuple = ()
    # FTP: used RBG-slots / all RBG-slots after warm-up (1 with full buffer),
    # the UPT (size / (completion - arrival)) and UT of every file that
    # arrived in the measurement window and completed, and how many arrived
    resource_utilization: float = 1.0
    file_upt_bps: np.ndarray = field(default_factory=lambda: np.zeros(0))
    file_ue: np.ndarray = field(default_factory=lambda: np.zeros(0, int))
    files_counted: int = 0
    # FTP: counted files still open at the end, as an upper bound on their
    # UPT (size / (end of run - arrival)), and their UTs
    file_upt_open_bps: np.ndarray = field(default_factory=lambda: np.zeros(0))
    file_ue_open: np.ndarray = field(default_factory=lambda: np.zeros(0, int))
    # FTP: arrival time [s] of each completed and each open counted file (a
    # drain can then be applied afterwards: keep files that arrived early enough)
    file_arrival_s: np.ndarray = field(default_factory=lambda: np.zeros(0))
    file_arrival_open_s: np.ndarray = field(default_factory=lambda: np.zeros(0))
    # FTP: UTs with data per cell, averaged over the slots after warm-up; FTP
    # model 1: arrivals that found no idle UT in the pool (queued behind one)
    mean_active_ues: float = 0.0
    arrivals_blocked: int = 0


def _links(d, k):
    """(cells (U, 1+K), rest interference per RE in mW / received power)."""
    cg = d.coupling_gain_db                              # (C, U)
    order = np.argsort(-cg, axis=0)
    u = np.arange(d.ues.n)
    serving = d.serving_cell
    others = np.array([[c for c in order[:, i] if c != serving[i]][:k] for i in u])
    return np.column_stack([serving, others])


def _pf_rate(cur):
    """Rate proxy per RBG of a UT's report for the PF metric: rank x
    log2(1 + SINR_sb), summed over the codewords' layers with several."""
    rep, s = cur[0], cur[1]
    if s.ndim == 1:
        return rep.rank * np.log2(1 + 10 ** (s / 10))
    return sum(len(g) * np.log2(1 + 10 ** (s[k] / 10)) for k, g in enumerate(rep.groups))


def _async_rbgs(unit: list, free: np.ndarray, cur, rbg_sig: list):
    """RBGs of an asynchronous retransmission (harq_mode 'async'): as many as
    the unit had, the free ones with the highest PF rate for the UT's current
    report ``cur`` when the report has the unit's rank (so its per-codeword
    sub-band SINRs fit the TBs) and the RBGs have the same RB pattern as the
    old ones; else the unit's own RBGs if they are free; None if neither
    fits (the retransmission waits a slot)."""
    rb = unit[0]["rbgs"]
    n = len(rb)
    if cur is not None and cur[0].rank == unit[0]["rank"] and free.sum() >= n:
        cand = np.flatnonzero(free)
        rate = _pf_rate(cur)[cand]
        pick = np.sort(cand[np.argsort(-rate, kind="stable")[:n]])
        if [rbg_sig[b] for b in pick] == [rbg_sig[b] for b in rb]:
            return pick
    return rb if free[rb].all() else None


def _rbg_bits(cur, rb_per_rbg, n_re, se_max=7.4):
    """Bits per RBG a UT's report would carry, for buffer-aware scheduling:
    Shannon on the CQI SINR of each layer, capped at ``se_max`` bit/RE (7.4
    with 256QAM, 9.26 with 1024QAM)."""
    rep, s = cur[0], cur[1]
    se = lambda x: np.minimum(np.log2(1 + 10 ** (x / 10)), se_max)
    if s.ndim == 1:
        per_re = rep.rank * se(s)
    else:
        per_re = sum(len(g) * se(s[k]) for k, g in enumerate(rep.groups))
    return per_re * n_re * rb_per_rbg


def _report_vectors(rep, n_rbg, first_f):
    """Unit-column reported precoder per RBG (n_rbg, S, r) for pairing."""
    w = rep.w
    if rep.w_per_f:
        w = w[first_f]
    elif w.ndim == 2:
        w = np.broadcast_to(w, (n_rbg,) + w.shape)
    return unit_columns(np.asarray(w, np.complex128))


def _mu_schedule_cell(c, cand, free, forced, current, pf_avg, la, la_mu, fb,
                      rbg_mask, rbg_f, rb_per_rbg, n_re, n_re_dd, n_f, n_s, slot,
                      stats):
    """MU-MIMO TBs of cell ``c`` on its free RBGs (see mac/mu_mimo.py).

    ``forced[b]`` lists the HARQ retransmissions due on RBG b.  They open the
    RBG's co-scheduled set (otherwise the PF owner does), other UTs are paired
    around them, and their precoder on b is recomputed for the new set; the
    TB, rank and MCS stay those of the first transmission.

    Every TB carries a per-frequency-point precoder (F, S, r) and, per RBG,
    the column offset ``col`` of its layers among the cell's layers.  A new
    TB sharing an RBG with more than 4 layers in total needs DM-RS ports 4-7,
    i.e. double-symbol DM-RS, and gets ``n_re_dd`` data REs per RB."""
    n_rbg = len(free)
    pool = [u for u in cand if current[u][0].rank <= fb.mu_max_rank]
    rank = {u: current[u][0].rank for u in cand}
    pf = {u: pf_avg[u] for u in cand}
    retx = {}
    for b in range(n_rbg):
        for tb in forced[b]:
            u = tb["ue"]
            retx[u], rank[u], pf[u] = tb, tb["rank"], pf_avg[u]
    if cand:
        met = np.array([rank[u] * np.log2(1 + 10 ** (current[u][1] / 10)) / pf_avg[u]
                        for u in cand])                         # (n_cand, n_rbg)
        best = np.argmax(met, axis=0)

    def vectors(u, b):
        if u in retx:
            r, rep = rank[u], current[u][0]
            if rep.rank >= r:
                return current[u][2][b][:, :r]
            return unit_columns(retx[u]["w"][np.argmax(rbg_mask[b])])
        return current[u][2][b]

    per_ue = {}
    for b in np.nonzero(free)[0]:
        start = [tb["ue"] for tb in forced[b]]
        if not start:
            if not cand:
                continue
            start = [cand[best[b]]]
        if fb.mu_max_ues < 2 or any(rank[u] > fb.mu_max_rank for u in start):
            group, w, est, uid = start, None, None, None
        else:
            v = {u: vectors(u, b) for u in set(pool) | set(start)}
            s_lin = {u: 10 ** (current[u][1][b] / 10) for u in v}
            s_mu = {u: s_lin[u] * 10 ** (-(la_mu.offset[u] - la.offset[u]) / 10)
                    for u in v}
            group, w, est, uid = greedy_pairing(
                start, pool, v, s_lin, rank, pf, fb.mu_max_ues, fb.mu_max_layers, s_mu,
                dd_factor=n_re_dd / n_re if fb.mu_dmrs_overhead else 1.0,
                method=fb.mu_precoder)
            if len(group) == 1:
                w = v[group[0]]
        stats["ues"].append(len(group))
        stats["layers"].append(sum(rank[u] for u in group))
        for u in group:
            per_ue.setdefault(u, []).append((b, group, w, est, uid))

    # retransmissions: new precoder and layer columns on their RBGs
    for u, tb in retx.items():
        for b, group, w, est, uid in per_ue.get(u, []):
            fm = rbg_mask[b]
            if len(group) == 1:
                ww = w if w is not None else vectors(u, b)
                tb["w"][fm] = ww / np.sqrt(ww.shape[1])
                tb["col"][b] = 0
            else:
                mine = np.nonzero(uid == u)[0]
                tb["w"][fm] = w[:, mine] / np.sqrt(len(uid))
                tb["col"][b] = mine[0]

    txs = []
    for u in cand:                        # same TB (and random draw) order as SU
        if u not in per_ue:
            continue
        alloc = per_ue[u]
        rep, sinr_sb = current[u][:2]
        r = rep.rank
        w_f = np.zeros((n_f, n_s, r), np.complex128)
        col = np.zeros(n_rbg, int)
        sinr_db, mu, dd = [], False, False
        for b, group, w, est, uid in alloc:
            dd |= sum(rank[x] for x in group) > 4
            fm = rbg_mask[b]
            if len(group) == 1:
                w_f[fm] = tb_precoder({"w": rep.w, "w_per_f": rep.w_per_f}, fm, rbg_f)
                sinr_db.append(sinr_sb[b])
            else:
                mu = True
                mine = np.nonzero(uid == u)[0]
                w_f[fm] = w[:, mine] / np.sqrt(len(uid))
                col[b] = mine[0]
                # raw estimate: the MU OLLA back-off is applied by la_mu
                raw = est[mine] * 10 ** ((la_mu.offset[u] - la.offset[u]) / 10)
                se = np.mean(np.log2(1 + raw))
                sinr_db.append(10 * np.log10(max(2 ** se - 1, 1e-6)))
        rbgs = np.array([a[0] for a in alloc])
        est_db = 10 * np.log10(max(2 ** np.mean(np.log2(1 + 10 ** (np.array(sinr_db) / 10)))
                                   - 1, 1e-6))
        txs.append(make_tb(la_mu if mu else la, u, c, r, w_f, True,
                           np.array(sinr_db), rbgs, rb_per_rbg,
                           n_re_dd if dd and fb.mu_dmrs_overhead else n_re,
                           fb.mcs_table, slot, col=col, mu=mu, est_db=est_db))
    return txs


def run_full_buffer_drop(cfg: ScenarioConfig, fb: FullBufferConfig, rng
                         ) -> FullBufferResult:
    if fb.cw_mapping not in CW_MAPPINGS:
        raise ValueError(f"cw_mapping must be one of {sorted(CW_MAPPINGS)}")
    max_cw = CW_MAPPINGS[fb.cw_mapping]
    if fb.receiver not in ("irc", "sic"):
        raise ValueError("receiver must be 'irc' or 'sic'")
    if fb.mu_mimo and (max_cw > 1 or fb.olla_per_rank or fb.harq_adaptive
                       or fb.receiver != "irc" or fb.ideal_la or fb.olla_sic_conditional
                       or fb.ri_olla):
        raise ValueError("multi-codeword mappings, per-rank OLLA, adaptive HARQ, SIC, "
                         "OLLA-corrected RI and ideal link adaptation are SU-MIMO only")
    sic = fb.receiver == "sic" and max_cw > 1
    if fb.harq_refill not in ("fresh", "always"):
        raise ValueError("harq_refill must be 'fresh' or 'always'")
    if fb.harq_mode not in ("sync", "async"):
        raise ValueError("harq_mode must be 'sync' or 'async'")
    if fb.harq_mode == "async" and fb.mu_mimo:
        raise ValueError("asynchronous HARQ is SU-MIMO only")
    if (fb.olla_fast_gain <= 0 or fb.olla_fast_samples < 0 or fb.olla_fast_min_cw < 0
            or fb.olla_warm_samples < 0):
        raise ValueError("olla_fast_gain must be > 0, olla_fast_samples, olla_fast_min_cw "
                         "and olla_warm_samples >= 0")
    if fb.evm_percent < 0:
        raise ValueError("evm_percent must be >= 0")
    if fb.traffic not in ("full_buffer", "ftp3", "ftp1"):
        raise ValueError("traffic must be 'full_buffer', 'ftp3' or 'ftp1'")
    ftp = fb.traffic in ("ftp3", "ftp1")
    ftp1 = fb.traffic == "ftp1"
    if ftp and fb.mu_mimo:
        raise ValueError("FTP traffic is SU-MIMO only")
    # FTP arrivals from a child stream: the same files for every scheme, and
    # the drop itself unchanged (spawning does not advance rng)
    trng = rng.spawn(1)[0] if ftp else None
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
    speed = np.full(n_ue, cfg.ue_speed_kmh / 3.6)
    if cfg.in_car_speed_kmh is not None:
        speed[d.ues.in_car] = cfg.in_car_speed_kmh / 3.6
    v = speed[:, None] * np.stack([np.cos(phi), np.sin(phi), np.zeros(n_ue)], -1)
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
    # RBs per channel point of each RBG: a retransmission may move only to
    # RBGs with the same pattern, so that chase combining adds like with like
    rbg_sig = [tuple(nrb_f[rbg_mask[b]]) for b in range(n_rbg)]
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

    def channels_for(t, ues):
        """channels(t) of the UTs ``ues`` only: (len(ues), 1+K, F, Ua, S)."""
        links = (ues[:, None] * (k + 1) + np.arange(k + 1)).reshape(-1)
        out = np.empty((links.size, n_f, n_u, n_s), np.complex64)
        for a in range(0, links.size, fb.link_batch):
            fl = links[a:a + fb.link_batch]
            out[a:a + fl.size] = channel_batch(subset_clusters(cl_all, pos[fl]), bearing[fl],
                                               bs, ue_ant, f_hz, t, vel[fl], lam, d3d[fl])
        out *= amp.reshape(-1)[links][:, None, None, None]
        return out.reshape(ues.size, k + 1, n_f, n_u, n_s)

    # --- PHY / MAC state ---
    pdsch = PDSCHConfig(num_rb=n_rb, start_symbol=fb.pdcch_symbols,
                        num_symbols=14 - fb.pdcch_symbols, n_oh=fb.overhead_re_per_prb)
    n_re = tbs_mod.re_per_rb(pdsch.num_symbols, rg.dmrs_re_per_rb(pdsch), pdsch.n_oh)
    fast = dict(fast_gain=fb.olla_fast_gain, fast_samples=fb.olla_fast_samples,
                fast_min_cw=fb.olla_fast_min_cw, warm_samples=fb.olla_warm_samples)
    la = LinkAdaptation(n_ue, fb.mcs_table, fb.target_bler, n_re, fb.olla_step_db,
                        n_cw=max_cw, per_rank=fb.olla_per_rank, max_rank=4, **fast)
    la_mu = LinkAdaptation(n_ue, fb.mcs_table, fb.target_bler, n_re, fb.olla_step_db,
                           **fast)
    # mu_dmrs_overhead: type-1 double-symbol DM-RS (ports 0-7), front-loaded
    # + 1 additional pair, 2 CDM groups without data -> 4 x 12 REs per RB
    # pair, 2 CDM groups without data -> 4 x 12 DM-RS REs per RB
    n_re_dd = tbs_mod.re_per_rb(pdsch.num_symbols, 4 * 12, pdsch.n_oh)
    # highest spectral efficiency per layer of the MCS table (buffer estimate);
    # 7.4 for the tables up to 256QAM, as before 1024QAM was added
    se_max = max(7.4, mcs_tables.get_mcs(mcs_tables.num_mcs(fb.mcs_table) - 1,
                                         fb.mcs_table).spectral_efficiency)
    n_lay = max(4, fb.mu_max_layers) if fb.mu_mimo else 4
    first_f = np.argmax(rbg_mask, axis=1)                   # first point of each RBG
    mu_stats = {"ues": [], "layers": []}
    n_mu_first = 0
    diag = {"retx_rbg": 0, "rbg": 0, "err": [], "retx_units": 0, "retx_moved": 0}
    proc = CSIProcessor(bs.Np, bs.Mp, 4, 4 if bs.Mp > 1 else 1,
                        codebook=fb.codebook,
                        max_rank=min(fb.max_rank, n_u), mcs_table=fb.mcs_table,
                        target_bler=fb.target_bler, n_re_per_rb=n_re,
                        n_beams=fb.n_beams, score_step=fb.pmi_score_step,
                        etype2_combo=fb.etype2_combo,
                        pmi_subband=fb.type1_subband_pmi,
                        max_codewords=max_cw, sic=sic, cw_mapping=fb.cw_mapping,
                        ri_sic_propagation=fb.ri_sic_propagation,
                        evm_percent=fb.evm_percent)
    pending = [[] for _ in range(n_ue)]                   # (avail, report, sinr_sb)
    current = [None] * n_ue
    pf_avg = np.full(n_ue, 1.0)
    harq = []                                             # pending retransmissions
    bits = np.zeros(n_ue)
    n_first = n_nack = 0
    rank_log, mcs_log, bits_log, ncw_log = [], [], [], []
    qm_count = np.zeros(11, int)                          # first-transmission TBs by Qm
    cw_first, cw_nack = np.zeros(4, int), np.zeros(4, int)
    n_tx = 0                                              # transmission ids
    ue_of_cell = [np.nonzero(d.serving_cell == c)[0] for c in range(lay.n_cells)]
    h = None
    if ftp:
        # files: Poisson arrivals per UT over the run; a file arriving in
        # [t_lo, t_hi) is counted.  Channels are computed only for the UTs
        # decoded in a slot, and for all at CSI occasions (h_block: the
        # channel-update block each UT's channel belongs to)
        t_end = fb.n_slots * t_slot
        size_bits = int(round(fb.ftp_file_bytes * 8))
        if ftp1:
            # UT arrivals over the network; each takes the first idle UT of
            # eight drawn at random (the same for every scheme)
            n_arr1 = int(trng.poisson(fb.ftp1_rate_per_cell * lay.n_cells * t_end))
            arr_t = np.sort(trng.uniform(0, t_end, n_arr1))
            arr_cand = trng.integers(0, n_ue, (n_arr1, 8))
            arr_u = arr_cand[:, 0]
        else:
            n_arr = trng.poisson(fb.ftp_rate_per_ue * t_end, n_ue)
            arr_t = trng.uniform(0, t_end, int(n_arr.sum()))
            arr_u = np.repeat(np.arange(n_ue), n_arr)
            order = np.argsort(arr_t, kind="stable")
            arr_t, arr_u = arr_t[order], arr_u[order]
        active = np.zeros(n_ue, bool)         # FTP model 1: UTs in the system
        acsi = []                             # FTP model 1: aperiodic CSI this slot
        n_blocked = n_with_data = 0
        t_lo, t_hi = fb.warmup_slots * t_slot, (fb.n_slots - fb.ftp_drain_slots) * t_slot
        files = [[] for _ in range(n_ue)]     # per UT, first in first out
        unsched = np.zeros(n_ue, np.int64)    # bits not yet in a TB
        n_arrived, files_counted, upt, upt_ue, upt_t = 0, 0, [], [], []
        h_all = np.empty((n_ue, k + 1, n_f, n_u, n_s), np.complex64)
        h_block = np.full(n_ue, -1)
        hw_all = np.zeros((n_ue, n_f, n_u, n_s), np.complex128)
        ru_used = ru_all = 0

    for slot in range(fb.n_slots):
        if not ftp and slot % fb.channel_update_slots == 0:
            h = channels(slot * t_slot)
        if ftp:                               # files that arrived in the last slot
            while n_arrived < arr_t.size and arr_t[n_arrived] < slot * t_slot:
                t_a, u = arr_t[n_arrived], arr_u[n_arrived]
                if ftp1:
                    idle = [int(c) for c in arr_cand[n_arrived] if not active[c]]
                    if idle:
                        u = idle[0]
                    else:
                        free_ues = np.flatnonzero(~active)
                        if free_ues.size:
                            u = int(free_ues[n_arrived % free_ues.size])
                        else:                 # pool exhausted: queue behind a UT
                            u = int(arr_cand[n_arrived, 0])
                            n_blocked += 1
                    if not active[u]:         # a new UT enters the system
                        active[u] = True
                        la.reset(u)
                        current[u], pending[u] = None, []
                        pf_avg[u] = 1.0
                        acsi.append(u)
                counted = bool(t_lo <= t_a < t_hi)
                files[u].append({"t": t_a, "unsched": size_bits, "left": size_bits,
                                 "counted": counted})
                unsched[u] += size_bits
                files_counted += counted
                n_arrived += 1
        for u in range(n_ue):                             # CSI becoming usable
            while pending[u] and pending[u][0][0] <= slot:
                current[u] = pending[u].pop(0)[1:]
        if ftp and slot >= fb.warmup_slots:
            n_with_data += sum(1 for f in files if f)

        # 1. scheduling
        w_cell = np.zeros((lay.n_cells, n_f, n_s, n_lay), np.complex64)
        txs = []
        due = [tb for tb in harq if tb["due"] <= slot]
        harq = [tb for tb in harq if tb["due"] > slot]
        for c in range(lay.n_cells):
            free = np.ones(n_rbg, bool)
            busy = set()
            forced = [[] for _ in range(n_rbg)]      # MU: co-scheduled retx
            for unit in harq_units([t for t in due if t["cell"] == c]):
                tb = unit[0]                  # all TBs of a unit share RBGs, rank, w
                rb = tb["rbgs"]
                if fb.harq_mode == "async":
                    cur = current[tb["ue"]]
                    rb = _async_rbgs(unit, free, cur, rbg_sig)
                    if rb is None:            # not enough free RBGs: next slot
                        for t in unit:
                            t["due"] = slot + 1
                            harq.append(t)
                        continue
                    moved = not np.array_equal(rb, tb["rbgs"])
                    if moved:
                        for t in unit:
                            t["rbgs"] = rb
                            if "cw_sinr" in t:          # the report has the unit's rank
                                t["cw_sinr"] = cur[1][:, rb]
                    if slot >= fb.warmup_slots:
                        diag["retx_units"] += 1
                        diag["retx_moved"] += int(moved)
                # MU: a retransmission joins its RBGs' co-scheduled sets (one
                # per UT and slot); otherwise it takes its RBGs alone
                if (fb.mu_mimo and fb.mu_max_ues > 1 and tb["ue"] not in busy
                        and tb["rank"] <= fb.mu_max_rank and free[rb].all() and all(
                        len(forced[b]) < fb.mu_max_ues
                        and sum(t["rank"] for t in forced[b]) + tb["rank"]
                        <= fb.mu_max_layers for b in rb)):
                    for b in rb:
                        forced[b].append(tb)
                    busy.add(tb["ue"])
                    tb["col"] = np.zeros(n_rbg, int)
                    if slot >= fb.warmup_slots:
                        diag["retx_rbg"] += len(rb)
                    txs.append(tb)
                elif free[rb].all() and not any(forced[b] for b in rb):
                    free[tb["rbgs"]] = False
                    busy.add(tb["ue"])
                    if slot >= fb.warmup_slots:
                        diag["retx_rbg"] += len(tb["rbgs"])
                    if fb.mu_mimo:            # retransmitted alone, full power
                        tb["col"] = np.zeros(n_rbg, int)
                        nrm = np.linalg.norm(tb["w"], axis=(1, 2), keepdims=True)
                        tb["w"] = np.where(nrm > 0, tb["w"] / np.maximum(nrm, 1e-12), 0)
                    cur = current[tb["ue"]]
                    if fb.harq_refill == "always":
                        refill, budget = True, None
                    else:
                        refill = (cur is not None and cur[0].rank == tb["rank"]
                                  and not tb.get("reduced", False))
                        budget = int(unsched[tb["ue"]]) if ftp else None
                    txs += retransmission(la, unit, rb_per_rbg, n_re, fb.mcs_table, slot,
                                          cur if fb.harq_adaptive else None, refill, budget)
                else:
                    for t in unit:
                        t["due"] = slot + 1
                        harq.append(t)
            if slot >= fb.warmup_slots and ue_of_cell[c].size:
                diag["rbg"] += n_rbg
            cand = [u for u in ue_of_cell[c] if current[u] is not None and u not in busy
                    and (not ftp or unsched[u] > 0)]
            if fb.mu_mimo and free.any() and (cand or any(forced)):
                stats = mu_stats if slot >= fb.warmup_slots else {"ues": [], "layers": []}
                txs += _mu_schedule_cell(c, cand, free, forced, current, pf_avg, la,
                                         la_mu, fb, rbg_mask, rbg_f, rb_per_rbg, n_re,
                                         n_re_dd, n_f, n_s, slot, stats)
            elif cand and free.any():
                met = np.array([_pf_rate(current[u])
                                / pf_avg[u] for u in cand])        # (n_cand, n_rbg)
                if ftp:
                    # PF per RBG among the UTs whose buffer the RBGs given
                    # so far do not yet cover (report-based estimate)
                    need = unsched[cand].astype(float)
                    est = np.array([_rbg_bits(current[u], rb_per_rbg, n_re, se_max)
                                    for u in cand])
                    owner = np.full(n_rbg, -1)
                    for b in np.nonzero(free)[0]:
                        if not (need > 0).any():
                            break
                        i = int(np.argmax(np.where(need > 0, met[:, b], -np.inf)))
                        owner[b] = i
                        need[i] -= est[i, b]
                else:
                    owner = np.where(free, np.argmax(met, axis=0), -1)
                for i, u in enumerate(cand):
                    rbgs = np.nonzero(owner == i)[0]
                    if rbgs.size == 0:
                        continue
                    rep, sinr_sb = current[u][:2]
                    txs += new_txs(la, u, c, rep, sinr_sb, rbgs, rb_per_rbg,
                                   n_re, fb.mcs_table, slot, n_tx)
                    n_tx += 1
            elif not ftp and not any(t["cell"] == c for t in txs) and ue_of_cell[c].size:
                g = rng.normal(size=(n_s,)) + 1j * rng.normal(size=(n_s,))
                w_cell[c, :, :, 0] = g / np.linalg.norm(g)
        placed = set()                        # multi-codeword transmissions
        for tb in txs:
            if fb.mu_mimo:
                for b in tb["rbgs"]:
                    fm, o = rbg_mask[b], tb["col"][b]
                    w_cell[tb["cell"], fm, :, o:o + tb["rank"]] = tb["w"][fm]
            elif tb.get("tx") not in placed:  # codewords share the precoder
                if "tx" in tb:
                    placed.add(tb["tx"])
                fm = rbg_mask[tb["rbgs"]].any(axis=0)
                w_cell[tb["cell"], fm, :, :tb["rank"]] = tb_precoder(tb, fm, rbg_f)

        if ftp:
            # new TBs take data from the buffer (a TB larger than the buffer
            # is padded); the share of cells using each RBG scales the
            # interference of the cells beyond the explicit ones
            used = np.zeros((lay.n_cells, n_rbg), bool)
            for tb in txs:
                used[tb["cell"], tb["rbgs"]] = True
                if "seg" not in tb:
                    u, want, seg = tb["ue"], int(tb["bits"]), []
                    for f in files[u]:
                        if want <= 0:
                            break
                        m = min(want, f["unsched"])
                        if m > 0:
                            f["unsched"] -= m
                            want -= m
                            seg.append((f, m))
                    tb["seg"], tb["payload"] = seg, sum(m for _, m in seg)
                    unsched[u] -= tb["payload"]
            util_f = used.mean(axis=0)[rbg_f]                 # (F,)
            if slot >= fb.warmup_slots:
                ru_used += int(used.sum())
                ru_all += used.size

        # 2. interference covariance and whitening, per UT and frequency
        if ftp:
            # CSI: every UT at the periodic occasions (FTP model 1: the UTs in
            # the system) and FTP model 1's new UTs; channels for those and
            # the UTs decoded in this slot
            csi_now = slot % fb.csi_period_slots == 0
            if ftp1:
                rep_ues = np.unique(np.concatenate(
                    [np.flatnonzero(active) if csi_now else np.zeros(0, int),
                     np.array(acsi, int)]))
            else:
                rep_ues = np.arange(n_ue) if csi_now else np.zeros(0, int)
            need_ue = np.unique(np.concatenate(
                [rep_ues, np.array([tb["ue"] for tb in txs], int)]))
            blk = slot // fb.channel_update_slots * fb.channel_update_slots
            stale = need_ue[h_block[need_ue] != blk]
            if stale.size:
                h_all[stale] = channels_for(blk * t_slot, stale)
                h_block[stale] = blk
            if need_ue.size:
                gi = h_all[need_ue, 1:] @ w_cell[cells[need_ue, 1:]]    # (n, K, F, Ua, 4)
                x = np.moveaxis(gi, 1, 3).reshape(need_ue.size, n_f, n_u, -1)
                noise = 1.0 + rest[need_ue, None] * util_f[None, :]     # (n, F)
                r_cov = (x @ np.conj(np.swapaxes(x, -1, -2))
                         + noise[:, :, None, None] * np.eye(n_u))
                hw_all[need_ue] = whitening(r_cov.astype(np.complex128)) @ h_all[need_ue, 0]
            hw = hw_all
        elif fb.mu_mimo:
            # one interferer at a time: w_cell[cells] with 8 layers would
            # copy ~1.3 GB for the default system
            r_cov = np.broadcast_to((1.0 + rest)[:, None, None, None] * np.eye(n_u),
                                    (n_ue, n_f, n_u, n_u)).astype(np.complex64)
            for j in range(1, k + 1):
                gi = h[:, j] @ w_cell[cells[:, j]]         # (U, F, Ua, Lc)
                r_cov += gi @ np.conj(np.swapaxes(gi, -1, -2))
        else:
            gi = h[:, 1:] @ w_cell[cells[:, 1:]]           # (U, K, F, Ua, 4)
            x = np.moveaxis(gi, 1, 3).reshape(n_ue, n_f, n_u, -1)   # (U, F, Ua, 4K)
            r_cov = (x @ np.conj(np.swapaxes(x, -1, -2))
                     + (1.0 + rest)[:, None, None, None] * np.eye(n_u))
        if not ftp:
            lw = whitening(r_cov.astype(np.complex128))   # (U, F, Ua, Ua)
            hw = lw @ h[:, 0]                             # (U, F, Ua, S)

        # 3. decode
        tx_sinr = {}                  # per-layer SINR of each multi-codeword transmission
        # SIC: (effective channel, layers of the earlier codewords that
        # decoded, layers of all earlier codewords)
        tx_sic = {}
        for tb in txs:
            u = tb["ue"]
            fm = rbg_mask[tb["rbgs"]].any(axis=0)
            first = tb["ntx"] == 0
            sinr = None
            if "tx" in tb and sic:
                # codewords in index order (their TBs are listed in that
                # order); the layers of those that decoded are cancelled
                if tb["tx"] not in tx_sic:
                    tx_sic[tb["tx"]] = (hw[u, fm] @ tb_precoder(tb, fm, rbg_f), [], [])
                g, cancelled, _ = tx_sic[tb["tx"]]
                sinr = sic_layer_sinr(g, tb["layers"], cancelled)
            elif "tx" in tb:
                # MMSE over all layers of the transmission (the other
                # codewords are interference), this codeword's layers
                if tb["tx"] not in tx_sinr:
                    tx_sinr[tb["tx"]] = mmse_sinr(hw[u, fm] @ tb_precoder(tb, fm, rbg_f))
                sinr = tx_sinr[tb["tx"]][:, tb["layers"]]
            elif fb.mu_mimo:
                # MMSE over all layers of the serving cell: co-scheduled
                # layers are interference the UT knows (DM-RS)
                g = hw[u, fm] @ w_cell[tb["cell"], fm]            # (Fsel, Ua, Lc)
                cols = tb["col"][rbg_f[fm]][:, None] + np.arange(tb["rank"])
                sinr = np.take_along_axis(mmse_sinr(g), cols, axis=1)
                if first and tb.get("mu") and slot >= fb.warmup_slots:
                    act = 10 * np.log10(max(2 ** np.mean(np.log2(1 + sinr)) - 1, 1e-6))
                    diag["err"].append(tb["est_db"] - act)
            if fb.evm_percent > 0:
                if sinr is None:
                    sinr = mmse_sinr(hw[u, fm] @ tb_precoder(tb, fm, rbg_f))
                sinr = evm_limited(sinr, fb.evm_percent)
            if fb.ideal_la and first:
                if sinr is None:
                    sinr = mmse_sinr(hw[u, fm] @ tb_precoder(tb, fm, rbg_f))
                plan = sinr
                if "tx" in tb and sic:
                    # the MCS assumes the earlier codewords are cancelled: the
                    # transmitter cannot know whether they decode, so error
                    # propagation hits this reference too
                    g, cancelled, earlier = tx_sic[tb["tx"]]
                    if len(cancelled) < len(earlier):
                        plan = evm_limited(sic_layer_sinr(g, tb["layers"], earlier),
                                           fb.evm_percent)
                ideal_mcs(tb, plan, nrb_f[fm], rb_per_rbg, n_re, fb.mcs_table,
                          fb.target_bler)
            propagated = ("tx" in tb and sic
                          and len(tx_sic[tb["tx"]][1]) < len(tx_sic[tb["tx"]][2]))
            ok = decode_tb(tb, hw[u], fm, rbg_f, nrb_f, rng, sinr)
            if "tx" in tb and sic:
                tx_sic[tb["tx"]][2].extend(tb["layers"])
                if ok:
                    tx_sic[tb["tx"]][1].extend(tb["layers"])
            if first:
                cw = tb.get("cw", 0)
                if not (propagated and fb.olla_sic_conditional):
                    (la_mu if tb.get("mu") else la).update(u, ok, cw=cw, tx_rank=tb["rank"])
                if slot >= fb.warmup_slots:
                    n_mu_first += int(bool(tb.get("mu")))
                pf_avg[u] += tb.get("payload", tb["bits"]) / fb.pf_window_slots
                if slot >= fb.warmup_slots:
                    n_first += 1
                    n_nack += int(not ok)
                    cw_first[cw] += 1
                    cw_nack[cw] += int(not ok)
                    if tb.get("lead", True):      # once per new transmission
                        rank_log.append(tb["rank"])
                        ncw_log.append(len(tb.get("groups", (0,))))
                    mcs_log.append(tb["info"].index)
                    qm_count[tb["info"].modulation_order] += 1
            if ok:
                if slot >= fb.warmup_slots:
                    bits[u] += tb.get("payload", tb["bits"])
                if ftp:
                    for f, m in tb["seg"]:
                        f["left"] -= m
                        if f["left"] == 0:            # last bits delivered
                            files[u] = [g for g in files[u] if g is not f]
                            if f["counted"]:
                                upt.append(size_bits / ((slot + 1) * t_slot - f["t"]))
                                upt_ue.append(u)
                                upt_t.append(f["t"])
                            if ftp1 and not files[u]:     # the UT leaves
                                active[u] = False
                                current[u], pending[u] = None, []
                                harq = [t for t in harq if t["ue"] != u]
            elif ftp1 and not active[u]:
                pass                      # a departed UT's padding: not resent
            elif tb["ntx"] < fb.harq_max_tx:
                tb["due"] = slot + fb.harq_rtt_slots
                harq.append(tb)
            elif ftp:                     # dropped: its data goes back (RLC ARQ)
                for f, m in tb["seg"]:
                    f["unsched"] += m
                unsched[u] += tb["payload"]
        pf_avg *= 1 - 1 / fb.pf_window_slots

        # 4. CSI reports
        if ftp1:
            report, acsi = rep_ues, []
        else:
            report = range(n_ue) if slot % fb.csi_period_slots == 0 else ()
        for u in report:
            rep = proc.select(hw[u], rbg_f, fb.rb_step, slot,
                              la.offset_table(u) if fb.ri_olla else None)
            bits_log.append(rep.pmi_bits)
            if max_cw == 1:
                sinr_sb = la.cqi_sinr_db(rep.cqi_sb, rep.rank, fb.rbg_size)
            else:                                         # (n_cw, n_rbg)
                sinr_sb = np.array([la.cqi_sinr_db(q, len(g), fb.rbg_size)
                                    for q, g in zip(rep.cqi_cw_sb, rep.groups)])
            vec = _report_vectors(rep, n_rbg, first_f) if fb.mu_mimo else None
            pending[u].append((slot + fb.csi_delay_slots, rep, sinr_sb, vec))

    t_meas = (fb.n_slots - fb.warmup_slots) * t_slot
    bw = cfg.channel_bandwidth_hz or n_rb * 12 * scs
    if ftp:
        still = [(size_bits / (t_end - f["t"]), u, f["t"]) for u in range(n_ue)
                 for f in files[u] if f["counted"]]
    tput = bits / t_meas
    return FullBufferResult(
        ue_throughput_bps=tput, ue_se=tput / bw,
        cell_se=float(tput.sum() / (lay.n_cells * bw)),
        bler_first=n_nack / max(n_first, 1),
        mean_rank=float(np.mean(rank_log)) if rank_log else 0.0,
        mean_mcs=float(np.mean(mcs_log)) if mcs_log else 0.0,
        mean_pmi_bits=float(np.mean(bits_log)) if bits_log else 0.0,
        serving_cell=d.serving_cell, geometry_db=d.geometry_db,
        bandwidth_hz=bw, n_cells=lay.n_cells,
        mean_ues_per_rbg=float(np.mean(mu_stats["ues"])) if mu_stats["ues"] else 1.0,
        mean_layers_per_rbg=(float(np.mean(mu_stats["layers"])) if mu_stats["layers"]
                             else float(np.mean(rank_log)) if rank_log else 0.0),
        mu_tb_fraction=n_mu_first / max(n_first, 1),
        retx_rbg_fraction=diag["retx_rbg"] / max(diag["rbg"], 1),
        retx_moved_fraction=diag["retx_moved"] / max(diag["retx_units"], 1),
        mu_sinr_error_db=float(np.mean(diag["err"])) if diag["err"] else 0.0,
        mean_codewords=float(np.mean(ncw_log)) if ncw_log else 0.0,
        rank_hist=tuple(float(np.mean(np.array(rank_log) == r)) if rank_log else 0.0
                        for r in range(1, 5)),
        bler_first_cw=tuple(float(n / f) for n, f in zip(cw_nack, cw_first) if f),
        modulation_share=tuple(float(qm_count[q] / max(qm_count.sum(), 1))
                               for q in (2, 4, 6, 8, 10)),
        resource_utilization=ru_used / max(ru_all, 1) if ftp else 1.0,
        file_upt_bps=np.array(upt) if ftp else np.zeros(0),
        file_ue=np.array(upt_ue, int) if ftp else np.zeros(0, int),
        files_counted=files_counted if ftp else 0,
        file_upt_open_bps=np.array([x for x, _, _ in still]) if ftp else np.zeros(0),
        file_ue_open=np.array([u for _, u, _ in still], int) if ftp else np.zeros(0, int),
        file_arrival_s=np.array(upt_t) if ftp else np.zeros(0),
        file_arrival_open_s=np.array([t for _, _, t in still]) if ftp else np.zeros(0),
        mean_active_ues=(n_with_data / max(fb.n_slots - fb.warmup_slots, 1) / lay.n_cells
                         if ftp else 0.0),
        arrivals_blocked=n_blocked if ftp else 0)


def _fb_worker(args):
    cfg, fb, seed, i = args
    return run_full_buffer_drop(cfg, fb, np.random.default_rng([seed, i]))


def run_full_buffer(cfg: ScenarioConfig, fb: FullBufferConfig, n_drops: int,
                    seed: int = 1, n_jobs: int = 1) -> dict:
    """Several independent drops; UT statistics pooled over drops."""
    from .simulator import parallel_map
    res = parallel_map(_fb_worker, [(cfg, fb, seed, i) for i in range(n_drops)],
                       n_jobs)
    return aggregate_drops(res)


def aggregate_drops(res: list) -> dict:
    """KPIs of several ``FullBufferResult`` drops: cell SE and per-drop
    means averaged, UT SE samples pooled for the percentiles."""
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
        "mean_ues_per_rbg": float(np.mean([r.mean_ues_per_rbg for r in res])),
        "mean_layers_per_rbg": float(np.mean([r.mean_layers_per_rbg for r in res])),
        "mu_tb_fraction": float(np.mean([r.mu_tb_fraction for r in res])),
        "retx_rbg_fraction": float(np.mean([r.retx_rbg_fraction for r in res])),
        "retx_moved_fraction": float(np.mean([r.retx_moved_fraction for r in res])),
        "mu_sinr_error_db": float(np.mean([r.mu_sinr_error_db for r in res])),
        "mean_codewords": float(np.mean([r.mean_codewords for r in res])),
        "rank_hist": np.mean([r.rank_hist for r in res], axis=0).tolist(),
        # per codeword index: averaged over the drops where it occurred
        "bler_first_cw": [float(np.mean([r.bler_first_cw[k] for r in res
                                         if len(r.bler_first_cw) > k]))
                          for k in range(max(len(r.bler_first_cw) for r in res))],
    }

