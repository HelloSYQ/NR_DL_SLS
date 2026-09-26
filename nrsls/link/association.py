"""Serving-cell selection.

UTs attach to the cell with the strongest port-0 RSRP (TR 38.901 Table 7.8-1,
0 dB handover margin).  Every cell transmits the same power per RE, so this
is the cell with the largest coupling gain.
"""

from __future__ import annotations

import numpy as np


def associate(coupling_gain_db: np.ndarray) -> np.ndarray:
    """Serving cell of each UT from the (C, U) coupling gains."""
    return np.argmax(coupling_gain_db, axis=0)


def cell_load(serving: np.ndarray, n_cells: int) -> np.ndarray:
    """Number of UTs served by each cell."""
    return np.bincount(serving, minlength=n_cells)
