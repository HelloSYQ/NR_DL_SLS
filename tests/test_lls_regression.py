"""LLS <-> SLS single-link regression (module plan section 5)."""

import numpy as np
import pytest

from nrsls.validation.lls import (lls_config, matched_fb, sls_point,
                                  sls_port_order, sweep)

SE_TOL = 0.04          # relative; Monte-Carlo spread of one run is ~1 %


@pytest.fixture(scope="module")
def cfg():
    return lls_config(n1=4, n2=1, n_rx=4, n_rb=24, model="CDL-C",
                      delay_spread_ns=300.0, n_slots=200)


@pytest.fixture(scope="module")
def matched(cfg):
    return sweep(cfg, [0.0, 10.0, 20.0], {"lls": None, "sls": matched_fb(cfg)})


def test_matched_sls_link_reproduces_the_lls(matched):
    for l, s in zip(matched["lls"], matched["sls"]):
        assert abs(s["se"] / l["se"] - 1) < SE_TOL, (l, s)
        assert abs(s["bler"] - l["bler"]) < 0.03
        assert abs(s["rank"] - l["rank"]) < 0.15
        assert abs(s["mcs"] - l["mcs"]) < 0.6


def test_a_1db_power_error_would_be_caught(cfg, matched):
    """The tolerance is tight enough to see a 1 dB normalisation error."""
    fb = matched_fb(cfg)
    lls = matched["lls"][1]["se"]
    for d in (-1.0, 1.0):
        se = sls_point(cfg, 10.0 + d, fb).spectral_efficiency
        assert abs(se / lls - 1) > SE_TOL


def test_port_order_lls_to_sls():
    # SLS s = p N1 N2 + n N2 + m  <-  LLS (row m, column n, polarisation p)
    assert list(sls_port_order(2, 2)) == [0, 4, 2, 6, 1, 5, 3, 7]
    assert sorted(sls_port_order(8, 2)) == list(range(32))


def test_codebooks_run_on_the_lls_channel(cfg):
    """Type-I (sub-band i2) and eType-II links run on the LLS channel and
    stay below the ideal per-RB SVD link."""
    base = matched_fb(cfg, rbg_size=4)
    ideal = sls_point(cfg, 10.0, base).spectral_efficiency
    t1 = sls_point(cfg, 10.0, matched_fb(cfg, rbg_size=4, codebook="type1"))
    et2 = sls_point(cfg, 10.0, matched_fb(cfg, rbg_size=4, codebook="etype2",
                                          etype2_combo=4))
    assert 0.5 * ideal < t1.spectral_efficiency < 1.02 * ideal
    assert 0.8 * ideal < et2.spectral_efficiency < 1.02 * ideal
    assert t1.mean_pmi_bits > 0 and et2.mean_pmi_bits > t1.mean_pmi_bits
    assert np.isfinite(t1.mean_rank) and 1 <= et2.mean_rank <= 4
