"""LLS <-> SLS single-link regression (module plan section 5).

Both simulators see the same ``nrdlsim`` CDL channel realisation (same
seed, same time evolution, H per RB at the RB centres).  The SLS side gets
it through ``NRDownlinkSimulator._make_channel`` / ``_channel_response``,
the private methods ``run_point`` itself uses; the pinned ``nrdlsim`` commit
keeps them stable, and the regression test fails if they change.

  * LLS: ``NRDownlinkSimulator.run_point(snr_db)`` with ideal channel
    estimation, per-RB SVD precoding, CSI every slot with a 4-slot delay,
    OLLA, one HARQ process (retransmission in the next slot);
  * SLS: ``run_single_link`` with the SLS CSI / link adaptation / L2S code.

Normalisation: the LLS channel has unit average power per port and noise
variance 10^(-SNR/10) with the transmit power split over the layers
(W / sqrt(rank)); the SLS works in units of the noise per RE with unit-norm
precoders, so H_SLS = 10^(SNR/20) H_LLS.  Transmit ports are re-ordered from
the LLS panel order (row, column, polarisation) to the SLS order
s = p N1 N2 + n N2 + m (TS 38.214 CSI-RS port order, N1 horizontal).

In the *matched* set-up (``matched_fb``) the SLS mimics the LLS: per-RB SVD
precoder (``svd_rb``), one CSI sub-band over the whole allocation
(wideband CQI), CSI period 1 slot, HARQ RTT 1 slot, channel updated every
slot.  The two must then agree to within Monte-Carlo noise.  The remaining
differences are bookkeeping: the LLS sends MCS-16 rank-1 TBs in the first
slots before its first report arrives, and re-uses the newest report's
precoder for a retransmission; the SLS waits for the first report and keeps
the TB's precoder.
"""

from __future__ import annotations

import numpy as np

from nrdlsim.config import (AntennaConfig, CarrierConfig, ChannelConfig,
                            PDSCHConfig, SimConfig)
from nrdlsim.link_simulator import NRDownlinkSimulator

from ..engine.fullbuffer import FullBufferConfig
from ..engine.single_link import SingleLinkResult, run_single_link


def lls_config(n1: int = 4, n2: int = 1, n_rx: int = 4, n_rb: int = 24,
               model: str = "CDL-C", delay_spread_ns: float = 300.0,
               speed_kmh: float = 3.0, n_slots: int = 200, seed: int = 7
               ) -> SimConfig:
    """LLS link: 2 N1 N2 cross-polarised gNB ports on an (N2 rows, N1
    columns) panel, ``n_rx`` cross-polarised UT ports in one row."""
    return SimConfig(
        carrier=CarrierConfig(mu=1, n_size_grid=n_rb),
        pdsch=PDSCHConfig(num_rb=n_rb, mcs_table=2),
        antenna=AntennaConfig(n_tx=2 * n1 * n2, n_rx=n_rx, tx_pol=2, rx_pol=2,
                              tx_layout=(n2, n1), rx_layout=(1, n_rx // 2),
                              tx_pattern="38.901", rx_pattern="omni"),
        channel=ChannelConfig(model=model, delay_spread_ns=delay_spread_ns,
                              carrier_freq_hz=3.5e9, ue_speed_kmh=speed_kmh),
        num_slots=n_slots, csi_feedback_delay_slots=4, link_adaptation=True,
        fec_mode="miesm", ideal_channel_estimation=True, precoding="svd",
        seed=seed)


def matched_fb(cfg: SimConfig, **kw) -> FullBufferConfig:
    """SLS link settings that reproduce the LLS procedure."""
    n_rb = cfg.pdsch.num_rb
    base = dict(n_slots=cfg.num_slots, warmup_slots=0, rb_step=1,
                channel_update_slots=1, csi_period_slots=1,
                csi_delay_slots=cfg.csi_feedback_delay_slots, rbg_size=n_rb,
                codebook="svd_rb", max_rank=min(cfg.antenna.n_tx, cfg.antenna.n_rx),
                mcs_table=cfg.pdsch.mcs_table, target_bler=cfg.pdsch.target_bler,
                harq_max_tx=cfg.harq.max_transmissions, harq_rtt_slots=1,
                pmi_score_step=1)
    base.update(kw)
    return FullBufferConfig(**base)


def sls_port_order(n1: int, n2: int) -> np.ndarray:
    """LLS port index of every SLS port s = p N1 N2 + n N2 + m."""
    p, n, m = np.meshgrid(np.arange(2), np.arange(n1), np.arange(n2), indexing="ij")
    return ((m * n1 + n) * 2 + p).reshape(-1)


def lls_point(cfg: SimConfig, snr_db: float, snr_seed: int = 0):
    return NRDownlinkSimulator(cfg).run_point(snr_db, snr_seed)


def sls_point(cfg: SimConfig, snr_db: float, fb: FullBufferConfig,
              snr_seed: int = 0, rng_seed: int = 1) -> SingleLinkResult:
    """The SLS single link on the channel ``lls_point`` would see."""
    n1, n2 = cfg.antenna.tx_layout[1], cfg.antenna.tx_layout[0]
    sim = NRDownlinkSimulator(cfg)
    chan, _ = sim._make_channel(snr_seed)          # same realisation as the LLS
    n_rb = cfg.pdsch.num_rb
    perm = sls_port_order(n1, n2)
    gain = 10 ** (snr_db / 20)
    t_slot = cfg.carrier.slot_duration_s

    def h_at(slot):
        h = sim._channel_response(chan, slot * t_slot, n_rb)[..., perm] * gain
        if fb.rb_step > 1:        # centre RB of every group of rb_step RBs
            idx = np.minimum(np.arange(0, n_rb, fb.rb_step) + fb.rb_step // 2,
                             n_rb - 1)
            h = h[idx]
        return h

    return run_single_link(h_at, n_rb, cfg.carrier.subcarrier_spacing_hz, n1, n2,
                           fb, np.random.default_rng(rng_seed))


def _point_worker(args):
    cfg, snr_db, seed, fb = args
    if fb is None:
        r = lls_point(cfg, snr_db, seed)
        return dict(se=r.spectral_efficiency, bler=r.bler, rank=r.avg_rank,
                    mcs=r.avg_mcs, pmi_bits=0.0)
    r = sls_point(cfg, snr_db, fb, seed, rng_seed=100 + seed)
    return dict(se=r.spectral_efficiency, bler=r.bler_first, rank=r.mean_rank,
                mcs=r.mean_mcs, pmi_bits=r.mean_pmi_bits)


def sweep(cfg: SimConfig, snrs, variants: dict, n_seeds: int = 1,
          n_jobs: int = 1) -> dict:
    """SE / first-transmission BLER / rank / MCS / PMI bits per SNR for every
    variant, averaged over ``n_seeds`` channel realisations (the same ones
    for every variant).  ``variants`` maps a name to a ``FullBufferConfig``
    (SLS single link) or to ``None`` (the LLS).  LLS rank and MCS are
    averaged over all transmissions, SLS ones over first transmissions."""
    from ..engine.simulator import parallel_map
    snrs = [float(x) for x in snrs]
    names = list(variants)
    jobs = [(cfg, s, k, variants[n]) for n in names for s in snrs
            for k in range(n_seeds)]
    res = iter(parallel_map(_point_worker, jobs, n_jobs))
    out = {}
    for n in names:
        rows = []
        for s in snrs:
            pts = [next(res) for _ in range(n_seeds)]
            rows.append(dict(snr_db=s, **{k: float(np.mean([p[k] for p in pts]))
                                          for k in pts[0]}))
        out[n] = rows
    return out
