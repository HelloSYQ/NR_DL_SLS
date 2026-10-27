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
                 max_rank: int = 4):
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

    def update(self, ue: int, ack: bool, cw: int = 0, tx_rank: int | None = None):
        k = self._key(ue, cw, tx_rank)
        self.offset[k] += -self.step_ack if ack else self.step_nack
        self.offset[k] = float(np.clip(self.offset[k], -self.limit, self.limit))
