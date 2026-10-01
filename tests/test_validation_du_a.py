"""Dense Urban-eMBB A validation case against TR 37.910 (nrsls.validation.du_a).

The full case takes ~20 min on 4 cores and runs only with NRSLS_SLOW=1:

    NRSLS_SLOW=1 python -m pytest tests/test_validation_du_a.py -s
"""

import os

import pytest

from nrsls.validation import du_a


def _kpis(avg, p5, bler=0.10, ues=5.0):
    return {"cell_se": avg, "ue_se_p5": p5, "ue_se_p50": 0.8, "bler_first": bler,
            "mean_ues_per_rbg": ues, "mean_layers_per_rbg": 2 * ues}


def test_case_definition_matches_the_reference_set_up():
    cfg, fb = du_a.case("etype2")
    assert cfg.isd_m == 200 and cfg.carrier_freq_hz == 4e9
    assert cfg.carrier.n_size_grid == 52 and cfg.carrier.mu == 0
    assert cfg.channel_bandwidth_hz == 10e6 and cfg.bs_tx_power_dbm == 41
    a = cfg.bs_antenna
    assert (a.M, a.N, a.P, a.Mp, a.Np) == (8, 8, 2, 2, 8) and a.n_ports == 32
    assert cfg.ue_antenna.n_ports == 4 and cfg.ue_per_cell == 10
    assert cfg.indoor_ratio == 0.8 and cfg.in_car_speed_kmh == 30
    assert fb.mu_mimo and fb.codebook == "etype2" and fb.max_rank == 2


def test_criteria_logic():
    good = {"etype2": _kpis(9.8, 0.36), "svd_sb": _kpis(12.5, 0.44),
            "_meta": {"n_drops": 1, "n_slots": 1, "warmup_slots": 0, "seed": 1,
                      "runtime_s": 0}}
    assert all(c.passed for c in du_a.evaluate(good))
    assert "PASS" in du_a.report(good, du_a.evaluate(good))
    bad = dict(good, etype2=_kpis(8.9, 0.36))             # -19 %: V1 fails
    assert [c.id for c in du_a.evaluate(bad) if not c.passed] == ["V1"]
    bad = dict(good, svd_sb=_kpis(9.0, 0.30))             # bound below ref, below eType-II
    assert {c.id for c in du_a.evaluate(bad) if not c.passed} == {"V3", "V4"}
    bad = dict(good, etype2=_kpis(9.8, 0.36, bler=0.2))   # link adaptation off target
    assert [c.id for c in du_a.evaluate(bad) if not c.passed] == ["V6"]


@pytest.mark.skipif(os.environ.get("NRSLS_SLOW") != "1",
                    reason="full system-level case (~20 min); set NRSLS_SLOW=1")
def test_dense_urban_a_against_tr37910():
    r = du_a.run(n_drops=2, n_slots=200, warmup_slots=40, seed=1, n_jobs=4)
    checks = du_a.evaluate(r)
    print("\n" + du_a.report(r, checks))
    assert all(c.passed for c in checks), [c for c in checks if not c.passed]
