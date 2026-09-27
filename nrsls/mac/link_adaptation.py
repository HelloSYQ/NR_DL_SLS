"""Link adaptation: CQI -> SINR, OLLA and MCS selection (TS 38.214).

The gNB turns each reported (sub-band) CQI back into the effective SINR at
which that CQI meets the BLER target on the CSI reference resource, combines
the sub-bands of an allocation in the capacity domain, subtracts the UT's
OLLA offset and picks the highest MCS whose own target-BLER SINR fits (the
``nrdlsim`` link-level procedure, per UT).  OLLA moves +step after a
first-transmission NACK and -step p/(1-p) after an ACK.
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
                 limit_db: float = 10.0):
        self.mcs_table = mcs_table
        self.cqi_table = mcs_tables.MCS_TO_CQI_TABLE[mcs_table]
        self.target = target_bler
        self.n_re = n_re_per_rb
        self.offset = np.zeros(n_ue)
        self.step_nack = step_db
        self.step_ack = step_db * target_bler / (1 - target_bler)
        self.limit = limit_db

    def cqi_sinr_db(self, cqi, rank: int, n_rb: int) -> np.ndarray:
        """Effective SINR implied by CQI values (CQI 0 -> -10 dB)."""
        reqs = cqi_required_sinr_db(self.cqi_table, rank, self.target,
                                    self.n_re, max(int(n_rb), 1))
        cqi = np.asarray(cqi)
        return np.where(cqi > 0, reqs[np.maximum(cqi, 1) - 1], -10.0)

    def select_mcs(self, ue: int, sinr_db_sb: np.ndarray, rank: int,
                   n_rb: int) -> int:
        """MCS for an allocation whose sub-bands imply ``sinr_db_sb``."""
        se = np.mean(np.log2(1 + 10 ** (np.asarray(sinr_db_sb) / 10)))
        eff = 10 * np.log10(max(2 ** se - 1, 1e-6)) - self.offset[ue]
        reqs = mcs_required_sinr_db(self.mcs_table, rank, self.target, self.n_re,
                                    max(int(n_rb), 1))
        ok = np.nonzero(reqs <= eff + 1e-9)[0]
        return int(ok[-1]) if ok.size else 0

    def update(self, ue: int, ack: bool):
        self.offset[ue] += -self.step_ack if ack else self.step_nack
        self.offset[ue] = float(np.clip(self.offset[ue], -self.limit, self.limit))
