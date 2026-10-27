"""Per-transport-block link steps shared by the full-buffer system loop and
the single-link LLS regression harness.

A TB is a dict with the UT, cell, RBGs, rank, precoder, MCS info, TBS,
number of transmissions and the chase-combined per-frequency-point SINR.

With several codewords a transmission carries one TB per codeword (keys
``tx``, ``cw``, ``layers``, ``groups``): the TBs share the RBGs, rank and
precoder, and each has its own MCS, TBS (TS 38.214 5.1.3.2 with the
codeword's layers), OLLA loop and HARQ process.  A retransmission resends
the failed codewords on their layers and refills the decoded ones with new
TBs (each TB has its own NDI), on the same RBGs, rank and precoder.
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
    mcs = la.select_mcs(u, sinr_db, rank, n_alloc, tx_rank=rank)
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


def cw_tb(la, ref: dict, cw: int, rb_per_rbg: np.ndarray, n_re: int,
          mcs_table: int, slot: int, lead: bool = False) -> dict:
    """New TB of codeword ``cw`` in the transmission described by ``ref``
    (UT, cell, RBGs, rank, precoder, layer groups and the per-codeword
    sub-band SINRs ``cw_sinr`` (n_cw, n_alloc_rbg) its MCS is chosen from)."""
    layers = list(ref["groups"][cw])
    n_alloc = int(rb_per_rbg[ref["rbgs"]].sum())
    mcs = la.select_mcs(ref["ue"], ref["cw_sinr"][cw], len(layers), n_alloc,
                        cw=cw, tx_rank=ref["rank"])
    info = mcs_tables.get_mcs(mcs, mcs_table)
    bits = tbs_mod.compute_tbs(n_re, n_alloc, info.modulation_order,
                               info.target_code_rate, len(layers))
    keys = ("ue", "cell", "rbgs", "rank", "w", "w_per_f", "groups", "cw_sinr", "tx")
    return dict({k: ref[k] for k in keys}, info=info, bits=bits, ntx=0, acc=None,
                due=slot, cw=cw, layers=layers, lead=lead)


def new_txs(la, u: int, cell: int, rep, sinr_sb: np.ndarray, rbgs: np.ndarray,
            rb_per_rbg: np.ndarray, n_re: int, mcs_table: int, slot: int,
            tx_id: int) -> list:
    """TBs of a new SU transmission: one TB (``sinr_sb`` (n_rbg,)), or one
    per codeword of the report (``sinr_sb`` (n_cw, n_rbg))."""
    if sinr_sb.ndim == 1:
        return [new_tb(la, u, cell, rep, sinr_sb, rbgs, rb_per_rbg, n_re, mcs_table, slot)]
    ref = dict(ue=u, cell=cell, rbgs=rbgs, rank=rep.rank, w=rep.w, w_per_f=rep.w_per_f,
               groups=rep.groups, cw_sinr=sinr_sb[:, rbgs], tx=tx_id)
    return [cw_tb(la, ref, k, rb_per_rbg, n_re, mcs_table, slot, lead=k == 0)
            for k in range(len(rep.groups))]


def harq_units(tbs: list) -> list:
    """Due retransmissions grouped by transmission (first-seen order); a TB
    without codewords is a group of its own."""
    units, index = [], {}
    for tb in tbs:
        if "tx" not in tb:
            units.append([tb])
        elif tb["tx"] in index:
            units[index[tb["tx"]]].append(tb)
        else:
            index[tb["tx"]] = len(units)
            units.append([tb])
    return units


def retransmission(la, unit: list, rb_per_rbg: np.ndarray, n_re: int, mcs_table: int,
                   slot: int, cur=None) -> list:
    """TBs of a HARQ retransmission: the due TBs of ``unit`` again, and a new
    TB on every other codeword (decoded, or dropped after the last
    transmission) with the MCS from its first-transmission CQI.

    Adaptive HARQ (``cur`` = the UT's current (report, sub-band SINRs)): if
    the current report has the transmission's rank, the whole PDSCH takes
    its precoder (DM-RS makes precoding transparent to the UT) and the new
    TBs its per-codeword CQIs; RBGs, rank and the retransmitted TBs' MCS
    stay."""
    if cur is not None and cur[0].rank == unit[0]["rank"]:
        rep, sinr_sb = cur[0], cur[1]
        for tb in unit:
            tb["w"], tb["w_per_f"] = rep.w, rep.w_per_f
            if "tx" in tb:
                tb["cw_sinr"] = sinr_sb[:, tb["rbgs"]]
    if "tx" not in unit[0]:
        return unit
    due = {tb["cw"]: tb for tb in unit}
    return [due[k] if k in due else cw_tb(la, unit[0], k, rb_per_rbg, n_re, mcs_table, slot)
            for k in range(len(unit[0]["groups"]))]


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
