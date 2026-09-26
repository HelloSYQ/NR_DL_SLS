"""Outdoor-to-indoor and in-car penetration loss, TR 38.901 clause 7.4.3.

Building penetration (clause 7.4.3.1):

    PL = PL_b + PL_tw + PL_in + N(0, sigma_P^2)

  * material losses (Table 7.4.3-1, f in GHz): standard glass 2 + 0.2 f,
    IRR glass 23 + 0.3 f, concrete 5 + 4 f;
  * low-loss model (Table 7.4.3-2): PL_tw = 5 - 10 log10(0.3 10^(-L_glass/10)
    + 0.7 10^(-L_concrete/10)), sigma_P = 4.4 dB;
  * high-loss model: PL_tw = 5 - 10 log10(0.7 10^(-L_IRRglass/10)
    + 0.3 10^(-L_concrete/10)), sigma_P = 6.5 dB;
  * PL_in = 0.5 d2D-in.  The O2I loss is UT-specific: the same for the UT's
    links to all BSs.
  * legacy model (Table 7.4.3-3, UMa/UMi below 6 GHz, backward compatible
    with TR 36.873): PL_tw = 20 dB, sigma_P = 0 and a link-specific
    d2D-in ~ U(0, 25) m.

In-car penetration (clause 7.4.3.2): N(9, 5^2) dB for an ordinary car.
"""

from __future__ import annotations

import numpy as np


def glass_loss_db(fc_ghz):
    return 2.0 + 0.2 * fc_ghz


def irr_glass_loss_db(fc_ghz):
    return 23.0 + 0.3 * fc_ghz


def concrete_loss_db(fc_ghz):
    return 5.0 + 4.0 * fc_ghz


def wall_loss_db(fc_ghz, high_loss):
    """PL_tw [dB] of the low-loss (False) or high-loss (True) model."""
    low = 5.0 - 10.0 * np.log10(0.3 * 10 ** (-glass_loss_db(fc_ghz) / 10.0)
                                + 0.7 * 10 ** (-concrete_loss_db(fc_ghz) / 10.0))
    high = 5.0 - 10.0 * np.log10(0.7 * 10 ** (-irr_glass_loss_db(fc_ghz) / 10.0)
                                 + 0.3 * 10 ** (-concrete_loss_db(fc_ghz) / 10.0))
    return np.where(high_loss, high, low)


def o2i_loss_db(fc_ghz, o2i, high_loss, d2d_in_m, rng):
    """UT-specific O2I loss [dB] (0 for outdoor UTs), new model."""
    o2i = np.asarray(o2i, bool)
    sigma_p = np.where(high_loss, 6.5, 4.4)
    loss = (wall_loss_db(fc_ghz, high_loss) + 0.5 * np.asarray(d2d_in_m)
            + sigma_p * rng.standard_normal(o2i.shape))
    return np.where(o2i, loss, 0.0)


def legacy_o2i_loss_db(o2i, d2d_in_link_m):
    """Link-specific legacy O2I loss [dB] (Table 7.4.3-3), shape of d2d_in."""
    return np.where(o2i, 20.0 + 0.5 * np.asarray(d2d_in_link_m), 0.0)


def in_car_loss_db(in_car, rng, mean_db=9.0, std_db=5.0):
    in_car = np.asarray(in_car, bool)
    return np.where(in_car, mean_db + std_db * rng.standard_normal(in_car.shape),
                    0.0)
