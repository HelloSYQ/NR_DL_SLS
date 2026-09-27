"""CSI report: RI, PMI (Type-I or SVD) and wideband / sub-band CQI.

The UT evaluates its (ideally estimated) serving channel together with the
interference it measures on CSI-IM, i.e. the whitened channel
H~ = L^-1 sqrt(P_RE) H_serving with R = L L^H the interference-plus-noise
covariance of the measurement slot (TS 38.214 clause 5.2.2.1).

  * eType-II (``codebook='etype2'``): the Rel-16 precoder per PMI sub-band
    derived from the whitened channel (see ``codebook/etype2.py``).
  * PMI, per rank (Type-I): two-stage search.  (1) The DFT beams v_{l,m} are ranked by
    their wideband whitened power summed over both polarisations; (2) every
    codeword built on the best ``n_beams`` beams is scored by its wideband
    rate sum_f log2 det(I + G^H G), G = H~ W.  ``codebook='svd'`` instead
    uses the wideband dominant right singular vectors (an ideal-CSI bound).
  * CQI: MIESM over the layer SINRs of each sub-band (and the whole band);
    the highest CQI whose BLER-target SINR is met (nrdlsim CQI tables).
  * RI: the rank that maximises rank x spectral efficiency of the wideband
    CQI (one codeword up to rank 4).
"""

from __future__ import annotations

from dataclasses import dataclass
from functools import lru_cache

import numpy as np

from nrdlsim import mcs_tables
from nrdlsim.csi import cqi_required_sinr_db
from nrdlsim.link_abstraction import effective_sinr_miesm

from math import ceil, log2

from .codebook.etype2 import ETypeIICodebook
from .codebook.type1 import TypeICodebook, _v
from .sinr import capacity, mmse_sinr


@dataclass
class CSIReport:
    rank: int
    w: np.ndarray                 # (S, rank) wideband or (N3, S, rank) per sub-band
    pmi: tuple                    # codebook indices (or () for SVD)
    cqi_wb: int
    cqi_sb: np.ndarray            # (n_subbands,)
    slot: int
    pmi_bits: int = 0             # PMI payload (UCI bits)


@lru_cache(maxsize=None)
def _codebook_tables(n1, n2, o1, o2, rank):
    cb = TypeICodebook(n1, n2, o1, o2)
    idx, w = cb.precoders(rank)
    return idx, w


@lru_cache(maxsize=None)
def _beams(n1, n2, o1, o2, half):
    lm = [(l, m) for l in range(n1 * o1 // (2 if half else 1))
          for m in range(n2 * o2)]
    return lm, np.array([_v(l, m, n1, n2, o1, o2, half) for l, m in lm]).T


@lru_cache(maxsize=None)
def _beam_of_codeword(n1, n2, o1, o2, rank):
    """Index into :func:`_beams` of the (first) beam of every codeword."""
    idx, _ = _codebook_tables(n1, n2, o1, o2, rank)
    return idx[:, 0] * (n2 * o2) + idx[:, 1]


class CSIProcessor:
    def __init__(self, n1: int, n2: int, o1: int = 4, o2: int = 4,
                 codebook: str = "type1", max_rank: int = 4,
                 mcs_table: int = 2, target_bler: float = 0.1,
                 n_re_per_rb: int = 144, n_beams: int = 4,
                 score_step: int = 1, etype2_combo: int = 6):
        self.n1, self.n2, self.o1, self.o2 = n1, n2, o1, o2
        self.codebook = codebook
        self.max_rank = max_rank
        self.cqi_table = mcs_tables.MCS_TO_CQI_TABLE[mcs_table]
        self.target_bler = target_bler
        self.n_re_per_rb = n_re_per_rb
        self.n_beams = n_beams
        self.score_step = score_step      # frequency subsampling of PMI scoring
        self.etype2_combo = etype2_combo
        self._et2 = None
        self.qms = sorted({mcs_tables.get_cqi(i, self.cqi_table)[0]
                           for i in range(1, 16)})

    # --- CQI ---------------------------------------------------------------
    def _cqi(self, sinr_lin, rank, n_rb):
        eff = {q: effective_sinr_miesm(sinr_lin, q) for q in self.qms}
        reqs = cqi_required_sinr_db(self.cqi_table, rank, self.target_bler,
                                    self.n_re_per_rb, max(int(n_rb), 1))
        for i in range(15, 0, -1):
            if eff[mcs_tables.get_cqi(i, self.cqi_table)[0]] >= reqs[i - 1]:
                return i
        return 0

    # --- PMI ---------------------------------------------------------------
    def _candidates(self, hw, rank):
        """Codewords to score for this rank (two-stage Type-I search)."""
        n1, n2, o1, o2 = self.n1, self.n2, self.o1, self.o2
        half = rank >= 3 and 2 * n1 * n2 >= 16
        lm, vb = _beams(n1, n2, o1, o2, half)
        k = vb.shape[0]
        # wideband power of each beam over both polarisations (and, for the
        # half beams, both halves of the horizontal dimension)
        hs = hw[::self.score_step]
        blocks = hs.reshape(hs.shape[:-1] + (-1, k))       # (F, U, blocks, k)
        pw = np.sum(np.abs(blocks @ vb) ** 2, axis=(0, 1, 2))
        best = np.argsort(pw)[::-1][: self.n_beams]
        idx, w = _codebook_tables(n1, n2, o1, o2, rank)
        keep = np.isin(_beam_of_codeword(n1, n2, o1, o2, rank), best)
        return idx[keep], w[keep]

    def _type1_bits(self, rank):
        n1, n2, o1, o2 = self.n1, self.n2, self.o1, self.o2
        i1 = ceil(log2(n1 * o1)) + (ceil(log2(n2 * o2)) if n2 * o2 > 1 else 0)
        i13 = 2 if rank >= 2 else 0
        return i1 + i13 + (2 if rank == 1 else 1)

    def select(self, hw: np.ndarray, subband_of_f: np.ndarray, rb_per_f: int,
               slot: int) -> CSIReport:
        """CSI from whitened serving channels hw (F, U, S)."""
        n_f = hw.shape[0]
        best = None
        if self.codebook == "etype2" and self._et2 is None:
            self._et2 = ETypeIICodebook(self.n1, self.n2, self.o1, self.o2,
                                        self.etype2_combo,
                                        int(subband_of_f.max()) + 1)
        for rank in range(1, min(self.max_rank, hw.shape[1]) + 1):
            bits = 0
            if self.codebook == "etype2":
                if not self._et2.supports(rank):
                    continue
                w, knz = self._et2.derive(hw, subband_of_f, rank)
                sinr = mmse_sinr(hw @ w[subband_of_f])
                pmi, bits = (), self._et2.payload_bits(rank, knz)
                cqi_wb = self._cqi(sinr, rank, n_f * rb_per_f)
                se = mcs_tables.get_cqi(cqi_wb, self.cqi_table)[2]
                if best is None or rank * se > best[0]:
                    best = (rank * se, rank, w, pmi, sinr, cqi_wb, bits)
                continue
            if self.codebook == "svd":
                cov = np.einsum("fus,fut->st", np.conj(hw), hw)
                _, vec = np.linalg.eigh(cov)
                w = vec[:, ::-1][:, :rank] / np.sqrt(rank)
                pmi = ()
            else:
                idx, ws = self._candidates(hw, rank)
                hs = hw[::self.score_step]
                rate = capacity(hs[None] @ ws[:, None]).sum(axis=1)   # (C,)
                i = int(np.argmax(rate))
                w, pmi = ws[i], tuple(int(x) for x in idx[i])
                bits = self._type1_bits(rank)
            sinr = mmse_sinr(hw @ w)                                   # (F, r)
            cqi_wb = self._cqi(sinr, rank, n_f * rb_per_f)
            se = mcs_tables.get_cqi(cqi_wb, self.cqi_table)[2]
            if best is None or rank * se > best[0]:
                best = (rank * se, rank, w, pmi, sinr, cqi_wb, bits)
        _, rank, w, pmi, sinr, cqi_wb, bits = best
        n_sb = int(subband_of_f.max()) + 1
        cqi_sb = np.array([self._cqi(sinr[subband_of_f == b], rank,
                                     np.sum(subband_of_f == b) * rb_per_f)
                           for b in range(n_sb)])
        return CSIReport(rank=rank, w=w, pmi=pmi, cqi_wb=cqi_wb,
                         cqi_sb=cqi_sb, slot=slot, pmi_bits=bits)
