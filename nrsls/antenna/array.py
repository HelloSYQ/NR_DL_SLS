"""gNB antenna panel with TXRU virtualisation.

The element pattern (TR 38.901 Table 7.3-1) and the panel orientation
(bearing, mechanical downtilt; clause 7.1.3) come from ``nrdlsim``.  Each
TXRU drives K = M / Mp vertically stacked co-polarised elements with the
TR 36.897 clause 5.2.2 weights w_k = exp(-j 2 pi (k-1) dV cos(theta_etilt))
/ sqrt(K), so the port power pattern toward LCS angles (theta', phi') is

    G(theta', phi') = A_E(theta', phi') + 10 log10 | sum_k w_k
                      exp(j 2 pi (k-1) dV cos theta') |^2        [dBi],

peaking at G_E,max + 10 log10 K on the electrical tilt.  All TXRUs of a
panel share this power pattern; they differ only in phase centre, which
matters once the fast-fading channel is added (phase 2).
"""

from __future__ import annotations

import numpy as np

from nrdlsim.channel_models import (local_element_gain, rotation_matrix,
                                    to_local_angles)

from ..config.scenario import BSAntennaConfig


class BSAntenna:
    def __init__(self, cfg: BSAntennaConfig):
        self.cfg = cfg
        k = np.arange(cfg.elements_per_txru)
        # sub-array steering toward the electrical tilt
        self._z = cfg.dV * k                       # element heights [lambda]
        self._w = (np.exp(-2j * np.pi * self._z
                          * np.cos(np.deg2rad(cfg.electrical_tilt_deg)))
                   / np.sqrt(len(k)))

    def element_gain_db(self, az_l, zen_l):
        c = self.cfg
        if c.pattern == "omni":
            return np.zeros(np.broadcast(az_l, zen_l).shape)
        return 10.0 * np.log10(local_element_gain(
            az_l, zen_l, c.max_gain_dbi, c.hpbw_deg, c.front_back_db))

    def subarray_gain_db(self, zen_l):
        """Array factor of one TXRU toward LCS zenith angles [dB]."""
        cz = np.cos(np.deg2rad(np.asarray(zen_l, float)))[..., None]
        af = np.abs(np.sum(self._w * np.exp(2j * np.pi * self._z * cz),
                           axis=-1)) ** 2
        return 10.0 * np.log10(np.maximum(af, 1e-12))

    def port_gain_db(self, az_deg, zen_deg, bearing_deg: float,
                     downtilt_deg: float | None = None):
        """Power gain [dBi] of a TXRU toward GCS angles (az, zen)."""
        tilt = (self.cfg.mechanical_downtilt_deg if downtilt_deg is None
                else downtilt_deg)
        R = rotation_matrix(bearing_deg, tilt, 0.0)
        az_l, zen_l = to_local_angles(az_deg, zen_deg, R)
        return self.element_gain_db(az_l, zen_l) + self.subarray_gain_db(zen_l)

    @property
    def peak_gain_dbi(self) -> float:
        g = 0.0 if self.cfg.pattern == "omni" else self.cfg.max_gain_dbi
        return g + 10.0 * np.log10(self.cfg.elements_per_txru)
