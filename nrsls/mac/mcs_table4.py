"""MCS index table 4 for PDSCH (1024QAM), TS 38.214 Table 5.1.3.1-4 (Rel-17).

``nrdlsim`` ships an *illustrative* table 4: its 256QAM table with six 1024QAM
rows appended, 34 indices, more than the 5-bit MCS field can address.  This
module replaces it, in ``nrdlsim``'s table registry, with the Rel-17 table:
the 256QAM table without five of its QPSK / 16QAM rows, plus four 1024QAM
rows, 27 indices (0-26; 27-31 are the reserved retransmission indices).
Importing ``nrsls`` does this, so ``mcs_table=4`` means the Rel-17 table
everywhere, in ``nrdlsim``'s own functions too.

The matching CQI table 4 (TS 38.214 Table 5.2.2.1-5) in ``nrdlsim`` already
has the Rel-17 values and is checked here.

Source of the values: the four 1024QAM rows (R x 1024 = 805.5, 853, 900.5,
948) are those agreed in RAN1 #104-e; rows 0-22 are rows of MCS table 2, and
which five of table 2's rows are dropped was entered from memory of the
specification.  Check against TS 38.214 before quoting absolute numbers.

1024QAM needs about 27 dB of post-equaliser SINR and more than 32 dB for its
highest rate, where transmitter and receiver impairments matter: see
``FullBufferConfig.evm_percent``.
"""

from __future__ import annotations

from nrdlsim import mcs_tables

# index -> (Qm, R x 1024)
MCS_TABLE_4 = [
    (2, 120), (2, 193), (2, 449),
    (4, 378), (4, 490), (4, 616),
    (6, 466), (6, 517), (6, 567), (6, 616), (6, 666), (6, 719), (6, 772),
    (6, 822), (6, 873),
    (8, 682.5), (8, 711), (8, 754), (8, 797), (8, 841), (8, 885), (8, 916.5),
    (8, 948),
    (10, 805.5), (10, 853), (10, 900.5), (10, 948),
]

# index -> (Qm, R x 1024, spectral efficiency); index 0 is "out of range"
CQI_TABLE_4 = [
    (0, 0, 0.0),
    (2, 78, 0.1523), (2, 193, 0.3770), (2, 449, 0.8770), (4, 378, 1.4766),
    (4, 616, 2.4063), (6, 567, 3.3223), (6, 666, 3.9023), (6, 772, 4.5234),
    (6, 873, 5.1152), (8, 711, 5.5547), (8, 797, 6.2266), (8, 885, 6.9141),
    (8, 948, 7.4063), (10, 853, 8.3301), (10, 948, 9.2578),
]


def register() -> None:
    """Make ``mcs_table=4`` the Rel-17 table in ``nrdlsim`` (idempotent)."""
    if mcs_tables._MCS_TABLES.get(4) == MCS_TABLE_4 and \
            mcs_tables._CQI_TABLES.get(4) == CQI_TABLE_4:
        return
    mcs_tables._MCS_TABLES[4] = list(MCS_TABLE_4)
    mcs_tables._CQI_TABLES[4] = list(CQI_TABLE_4)
    mcs_tables.MCS_TO_CQI_TABLE[4] = 4
    # per-table caches that may hold the table registered before
    from nrdlsim import csi, link_abstraction
    from . import link_adaptation
    link_abstraction._amc_table.cache_clear()
    csi.cqi_required_sinr_db.cache_clear()
    link_adaptation.mcs_required_sinr_db.cache_clear()


register()
