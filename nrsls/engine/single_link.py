"""One SLS link in isolation: a single UT, no interference, white noise.

This runs the per-UT part of the full-buffer loop (``fullbuffer.py``) on an
externally supplied channel sequence.  CSI (``CSIProcessor``), link
adaptation / OLLA (``LinkAdaptation``) and the TB steps (``link.py``:
MCS/TBS, precoder, MMSE SINR, chase combining, MIESM BLER) are the same code
objects the system loop uses.  It is the SLS side of the LLS <-> SLS
regression (``nrsls.validation.lls``, module plan section 5).

With one UT and no other cell, proportional fair gives the UT every RBG
that no due retransmission occupies, and whitening is the identity (the
channel is already normalised to the noise power per RE).
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Callable

import numpy as np

from nrdlsim import resource_grid as rg
from nrdlsim import tbs as tbs_mod
from nrdlsim.config import PDSCHConfig

from ..mac.link_adaptation import LinkAdaptation
from ..phy.csi import CSIProcessor
from .fullbuffer import FullBufferConfig
from .link import decode_tb, new_tb


@dataclass
class SingleLinkResult:
    spectral_efficiency: float    # bit/s/Hz over the carrier
    bler_first: float
    residual_bler: float
    mean_rank: float
    mean_mcs: float
    mean_pmi_bits: float


def run_single_link(h_at: Callable[[int], np.ndarray], n_rb: int, scs_hz: float,
                    n1: int, n2: int, fb: FullBufferConfig, rng,
                    o1: int = 4, o2: int | None = None) -> SingleLinkResult:
    """``h_at(slot)`` -> H (F, U, S): the channel of frequency points of
    ``fb.rb_step`` RBs, in units of the noise per RE, S ordered as the SLS
    ports (s = p N1 N2 + n N2 + m)."""
    o2 = (4 if n2 > 1 else 1) if o2 is None else o2
    t_slot = 1e-3 / (scs_hz / 15e3)
    first_rb = np.arange(0, n_rb, fb.rb_step)
    nrb_f = np.minimum(fb.rb_step, n_rb - first_rb)
    rbg_f = first_rb // fb.rbg_size
    n_rbg = int(np.ceil(n_rb / fb.rbg_size))
    rb_per_rbg = np.bincount(np.arange(n_rb) // fb.rbg_size, minlength=n_rbg)
    rbg_mask = rbg_f[None, :] == np.arange(n_rbg)[:, None]

    pdsch = PDSCHConfig(num_rb=n_rb)
    n_re = tbs_mod.re_per_rb(pdsch.num_symbols, rg.dmrs_re_per_rb(pdsch), pdsch.n_oh)
    la = LinkAdaptation(1, fb.mcs_table, fb.target_bler, n_re, fb.olla_step_db)
    proc = None

    pending, current, harq = [], None, []
    bits = 0
    n_first = n_nack = n_done = n_lost = 0
    rank_log, mcs_log, bits_log = [], [], []
    h = None
    for slot in range(fb.n_slots):
        if slot % fb.channel_update_slots == 0:
            h = h_at(slot)
            if proc is None:
                proc = CSIProcessor(n1, n2, o1, o2, codebook=fb.codebook,
                                    max_rank=min(fb.max_rank, h.shape[1]),
                                    mcs_table=fb.mcs_table,
                                    target_bler=fb.target_bler, n_re_per_rb=n_re,
                                    n_beams=fb.n_beams, score_step=fb.pmi_score_step,
                                    etype2_combo=fb.etype2_combo,
                                    pmi_subband=fb.type1_subband_pmi)
        while pending and pending[0][0] <= slot:
            current = pending.pop(0)[1:]

        # scheduling: due retransmissions first, the rest of the band new
        txs = []
        free = np.ones(n_rbg, bool)
        for tb in [t for t in harq if t["due"] <= slot]:
            harq.remove(tb)
            if free[tb["rbgs"]].all():
                free[tb["rbgs"]] = False
                txs.append(tb)
            else:
                tb["due"] = slot + 1
                harq.append(tb)
        if current is not None and not txs and free.any():
            rep, sinr_sb = current
            txs.append(new_tb(la, 0, 0, rep, sinr_sb, np.nonzero(free)[0],
                              rb_per_rbg, n_re, fb.mcs_table, slot))

        for tb in txs:
            fm = rbg_mask[tb["rbgs"]].any(axis=0)
            first = tb["ntx"] == 0
            ok = decode_tb(tb, h, fm, rbg_f, nrb_f, rng)
            count = slot >= fb.warmup_slots
            if first:
                la.update(0, ok)
                if count:
                    n_first += 1
                    n_nack += int(not ok)
                    rank_log.append(tb["rank"])
                    mcs_log.append(tb["info"].index)
            if ok:
                if count:
                    bits += tb["bits"]
                    n_done += 1
            elif tb["ntx"] < fb.harq_max_tx:
                tb["due"] = slot + fb.harq_rtt_slots
                harq.append(tb)
            elif count:
                n_done += 1
                n_lost += 1

        if slot % fb.csi_period_slots == 0:
            rep = proc.select(h, rbg_f, fb.rb_step, slot)
            bits_log.append(rep.pmi_bits)
            sinr_sb = la.cqi_sinr_db(rep.cqi_sb, rep.rank, fb.rbg_size)
            pending.append((slot + fb.csi_delay_slots, rep, sinr_sb))

    t_meas = (fb.n_slots - fb.warmup_slots) * t_slot
    return SingleLinkResult(
        spectral_efficiency=bits / t_meas / (n_rb * 12 * scs_hz),
        bler_first=n_nack / max(n_first, 1),
        residual_bler=n_lost / max(n_done, 1),
        mean_rank=float(np.mean(rank_log)) if rank_log else 0.0,
        mean_mcs=float(np.mean(mcs_log)) if mcs_log else 0.0,
        mean_pmi_bits=float(np.mean(bits_log)) if bits_log else 0.0)
