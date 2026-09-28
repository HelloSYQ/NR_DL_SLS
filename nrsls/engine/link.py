"""Per-transport-block link steps shared by the full-buffer system loop and
the single-link LLS regression harness.

A TB is a dict with the UT, cell, RBGs, rank, precoder, MCS info, TBS,
number of transmissions and the chase-combined per-frequency-point SINR.
"""

from __future__ import annotations

import numpy as np

from nrdlsim import mcs_tables
from nrdlsim import tbs as tbs_mod
from nrdlsim.link_abstraction import bler_from_effective_sinr, effective_sinr_miesm

from ..phy.sinr import mmse_sinr


def tb_precoder(tb: dict, fm: np.ndarray, rbg_f: np.ndarray) -> np.ndarray:
    """Precoder (S, r) or (Fsel, S, r) of a TB on the frequency points ``fm``.

    The report's precoder is wideband (S, r), per sub-band (N_sb, S, r) or,
    for ``svd_rb``, per frequency point (F, S, r)."""
    w = tb["w"]
    if tb["w_per_f"]:
        return w[fm]
    return w if w.ndim == 2 else w[rbg_f[fm]]


def make_tb(la, u: int, cell: int, rank: int, w: np.ndarray, w_per_f: bool,
            sinr_db: np.ndarray, rbgs: np.ndarray, rb_per_rbg: np.ndarray,
            n_re: int, mcs_table: int, slot: int, **extra) -> dict:
    """First transmission of a TB on ``rbgs`` whose RBGs imply the (effective
    per-layer) SINRs ``sinr_db``: MCS from them and the UT's OLLA offset in
    ``la``, TBS from TS 38.214."""
    n_alloc = int(rb_per_rbg[rbgs].sum())
    mcs = la.select_mcs(u, sinr_db, rank, n_alloc)
    info = mcs_tables.get_mcs(mcs, mcs_table)
    bits = tbs_mod.compute_tbs(n_re, n_alloc, info.modulation_order,
                               info.target_code_rate, rank)
    return dict(ue=u, cell=cell, rbgs=rbgs, rank=rank, w=w, w_per_f=w_per_f,
                info=info, bits=bits, ntx=0, acc=None, due=slot, **extra)


def new_tb(la, u: int, cell: int, rep, sinr_sb: np.ndarray, rbgs: np.ndarray,
           rb_per_rbg: np.ndarray, n_re: int, mcs_table: int, slot: int) -> dict:
    """SU TB with the reported precoder and the sub-band CQIs of ``rbgs``."""
    return make_tb(la, u, cell, rep.rank, rep.w, rep.w_per_f, sinr_sb[rbgs], rbgs,
                   rb_per_rbg, n_re, mcs_table, slot)


def decode_tb(tb: dict, hw_u: np.ndarray, fm: np.ndarray, rbg_f: np.ndarray,
              nrb_f: np.ndarray, rng, sinr: np.ndarray | None = None) -> bool:
    """One (re)transmission: MMSE-IRC SINR on the whitened channel hw_u
    (F, U, S) (or the given per-layer ``sinr`` (Fsel, r), e.g. from an MMSE
    over all co-scheduled layers), chase combining with earlier
    transmissions, MIESM -> BLER -> ACK/NACK."""
    if sinr is None:
        sinr = mmse_sinr(hw_u[fm] @ tb_precoder(tb, fm, rbg_f))  # (Fsel, r)
    tb["acc"] = sinr if tb["acc"] is None else tb["acc"] + sinr
    re_sinr = np.repeat(tb["acc"], nrb_f[fm], axis=0)
    qm, rate = tb["info"].modulation_order, tb["info"].target_code_rate
    eff = effective_sinr_miesm(re_sinr, qm)
    ok = rng.random() > bler_from_effective_sinr(eff, qm, rate, tb["bits"])
    tb["ntx"] += 1
    return bool(ok)
