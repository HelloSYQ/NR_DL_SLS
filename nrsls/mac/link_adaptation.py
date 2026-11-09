"""Link adaptation: CQI -> SINR, OLLA and MCS selection (TS 38.214).

The gNB turns each reported (sub-band) CQI back into the effective SINR at
which that CQI meets the BLER target on the CSI reference resource, combines
the sub-bands of an allocation in the capacity domain, subtracts the UT's
OLLA offset and picks the highest MCS whose own target-BLER SINR fits (the
``nrdlsim`` link-level procedure, per UT).  OLLA moves +step after a
first-transmission NACK and -step p/(1-p) after an ACK.

With several codewords (``n_cw`` > 1) each codeword index has its own OLLA
loop per UT, and with ``per_rank`` also per transmission rank (OLLA per CW
per rank).  With one codeword and no ``per_rank`` there is one loop per UT.

Fast start (``fast_gain``, ``fast_samples``, ``fast_min_cw``): the first
``fast_samples`` ACK/NACKs of a loop (since its UT arrived, see ``reset``)
move it ``fast_gain`` times the normal steps, keeping their ratio and so the
BLER target, for the codewords from index ``fast_min_cw`` on.  A loop that
starts at 0 dB and must climb X dB pays X / (step + step p/(1-p)) NACKs
above the target; the fast start divides that by ``fast_gain``, which
matters most for a loop with few samples, e.g. the codeword of the weakest
layer, used only at full rank.

Warm start (``warm_samples`` > 0): a new UT's loops (``reset``) start from the
mean offset of the other UTs' loops of the same codeword (and rank, with
``per_rank``) that have had at least ``warm_samples`` ACK/NACKs, instead of
0 dB: an initial offset learned from the converged loops, so that a new UT
does not pay the climb.  Loops without such peers start from 0 dB.
"""

from __future__ import annotations

from functools import lru_cache

import numpy as np

from nrdlsim import mcs_tables
from nrdlsim import tbs as tbs_mod
from nrdlsim.csi import cqi_required_sinr_db
from nrdlsim.link_abstraction import required_eff_sinr_db


@lru_cache(maxsize=None)
def mcs_required_sinr_db(mcs_table: int, rank: int, target_bler: float,
                         n_re_per_rb: int, n_rb: int) -> np.ndarray:
    reqs = []
    for i in range(mcs_tables.num_mcs(mcs_table)):
        info = mcs_tables.get_mcs(i, mcs_table)
        tb = tbs_mod.compute_tbs(n_re_per_rb, n_rb, info.modulation_order,
                                 info.target_code_rate, rank)
        reqs.append(required_eff_sinr_db(info.modulation_order,
                                         info.target_code_rate, tb, target_bler))
    return np.array(reqs)


class LinkAdaptation:
    def __init__(self, n_ue: int, mcs_table: int = 2, target_bler: float = 0.1,
                 n_re_per_rb: int = 132, step_db: float = 0.5,
                 limit_db: float = 10.0, n_cw: int = 1, per_rank: bool = False,
                 max_rank: int = 4, fast_gain: float = 1.0, fast_samples: int = 0,
                 fast_min_cw: int = 0, warm_samples: int = 0):
        self.mcs_table = mcs_table
        self.cqi_table = mcs_tables.MCS_TO_CQI_TABLE[mcs_table]
        self.target = target_bler
        self.n_re = n_re_per_rb
        self.per_rank = per_rank
        # (n_ue,) for one loop per UT, else (n_ue, ranks, codewords)
        self.offset = (np.zeros(n_ue) if n_cw == 1 and not per_rank else
                       np.zeros((n_ue, max_rank + 1 if per_rank else 1, n_cw)))
        self.step_nack = step_db
        self.step_ack = step_db * target_bler / (1 - target_bler)
        self.limit = limit_db
        self.fast_gain = float(fast_gain)
        self.fast_samples = int(fast_samples)
        self.fast_min_cw = int(fast_min_cw)
        self.warm_samples = int(warm_samples)
        self.n_updates = np.zeros(self.offset.shape, int)     # per loop, since reset

    def _key(self, ue: int, cw: int, tx_rank: int | None):
        if self.offset.ndim == 1:
            return ue
        if self.per_rank and tx_rank is None:
            raise ValueError("per-rank OLLA needs the transmission rank")
        return ue, tx_rank if self.per_rank else 0, cw

    def cqi_sinr_db(self, cqi, rank: int, n_rb: int) -> np.ndarray:
        """Effective SINR implied by CQI values (CQI 0 -> -10 dB)."""
        reqs = cqi_required_sinr_db(self.cqi_table, rank, self.target,
                                    self.n_re, max(int(n_rb), 1))
        cqi = np.asarray(cqi)
        return np.where(cqi > 0, reqs[np.maximum(cqi, 1) - 1], -10.0)

    def select_mcs(self, ue: int, sinr_db_sb: np.ndarray, rank: int,
                   n_rb: int, cw: int = 0, tx_rank: int | None = None) -> int:
        """MCS for an allocation whose sub-bands imply ``sinr_db_sb``.
        ``rank`` is the number of layers of the codeword (TBS), ``cw`` and
        ``tx_rank`` select the OLLA loop."""
        se = np.mean(np.log2(1 + 10 ** (np.asarray(sinr_db_sb) / 10)))
        eff = 10 * np.log10(max(2 ** se - 1, 1e-6)) - self.offset[self._key(ue, cw, tx_rank)]
        reqs = mcs_required_sinr_db(self.mcs_table, rank, self.target, self.n_re,
                                    max(int(n_rb), 1))
        ok = np.nonzero(reqs <= eff + 1e-9)[0]
        return int(ok[-1]) if ok.size else 0

    def reset(self, ue: int) -> None:
        """A new UT (FTP model 1): its loops start from zero, or with a warm
        start from the mean of the other UTs' loops that have had at least
        ``warm_samples`` ACK/NACKs (per codeword and rank); with a fast start
        they are fast again."""
        self.offset[ue] = 0.0
        self.n_updates[ue] = 0
        if self.warm_samples > 0:
            peers = self.n_updates >= self.warm_samples       # ue's own count is 0
            n = peers.sum(axis=0)
            total = np.where(peers, self.offset, 0.0).sum(axis=0)
            self.offset[ue] = np.where(n > 0, total / np.maximum(n, 1), 0.0)

    def offset_table(self, ue: int, max_rank: int = 4) -> np.ndarray:
        """The UT's OLLA offsets [dB] as (max_rank + 1, n_cw), indexed by
        transmission rank and codeword (the same for every rank without
        ``per_rank``)."""
        o = self.offset[ue]
        if self.offset.ndim == 1:
            return np.full((max_rank + 1, 1), float(o))
        if self.per_rank:
            return np.asarray(o, float)
        return np.broadcast_to(o[0], (max_rank + 1, o.shape[1]))

    def update(self, ue: int, ack: bool, cw: int = 0, tx_rank: int | None = None):
        k = self._key(ue, cw, tx_rank)
        step = -self.step_ack if ack else self.step_nack
        if cw >= self.fast_min_cw and self.n_updates[k] < self.fast_samples:
            step *= self.fast_gain
        self.n_updates[k] += 1
        self.offset[k] += step
        self.offset[k] = float(np.clip(self.offset[k], -self.limit, self.limit))
