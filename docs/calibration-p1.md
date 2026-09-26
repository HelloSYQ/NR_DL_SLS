# Phase 1: large-scale geometry, verification and calibration status

Phase 1 of the [module plan](module-plan.md) is implemented. It covers
the deployment, UT drop, large-scale propagation, association, coupling gain
and geometry. It does not include fast fading, which comes in phase 2.

**Status of the exit criterion.** The plan's exit criterion is "coupling-loss /
geometry CDFs within ~1 dB of the TR 38.901 §7.8 calibration". That comparison
is **not done yet**. The industry reference curves are published in the 3GPP
RAN1 calibration-summary contributions, not in the TR text, and 3gpp.org is
blocked by this environment's network policy. Everything that can be checked
without those curves has been checked (see [Verification](#verification)). The
simulator already accepts reference CDFs as CSV and reports the percentile gaps
(see [Comparing against reference curves](#comparing-against-reference-curves)).

Reproduce everything here with:

```bash
pip install -r requirements.txt && pip install -e .
python -m pytest                      # 57 tests, ~10 s
python examples/plot_large_scale.py   # figures + results/p1_summary.json, ~10 s
```

---

## What a drop computes

TR 38.901 §7.5 steps 1–4, without fast fading:

| Step | Module | Spec |
|---|---|---|
| 19 sites × 3 sectors (30°/150°/270°), or the InH hall with 12 TRPs | `topology/layout.py` | TR 38.901 Tables 7.2-1…7.2-3 |
| Wrap-around: each UT sees the closest of 7 copies of every site | `topology/layout.py` | TR 36.814 A.2.1.1 |
| UT drop: per-sector rhombus, minimum 2-D distance, 80 % indoor, floors n_fl ~ U{1..N_fl} with N_fl ~ U{4..8}, h_UT = 3(n_fl−1)+1.5, d2D-in = min of two U(0, 25) | `topology/ue_drop.py` | 7.2, 7.4.3; TR 36.873 |
| LOS state per (site, UT). O2I UTs use d2D-out. | `propagation/los.py` | Table 7.4.2-1 |
| Basic pathloss, including UMa's random h_E breakpoint | `propagation/pathloss.py` | Table 7.4.1-1 |
| O2I loss: low/high/mixed, UT-specific σ_P; legacy 20 dB, link-specific d2D-in; in-car N(9, 5²) | `propagation/o2i.py` | 7.4.3, Tables 7.4.3-1/2/3 |
| Shadow fading: exact exponential spatial correlation on the UT positions, separate LOS/NLOS/O2I fields, independent across sites, shared by co-sited sectors, independent across floors | `propagation/lsp.py` | 7.5 step 4, Table 7.5-6 |
| Port-0 gain toward the LOS direction: element pattern × K-element vertical sub-array with electrical tilt | `antenna/array.py` (reuses `nrdlsim` pattern + rotation) | Table 7.3-1, TR 36.897 5.2.2 |
| Coupling gain; serving cell = strongest RSRP (0 dB margin); geometry = S / (ΣI + N) | `link/`, `engine/drop.py` | Table 7.8-1 |

"Coupling gain" in this code and in the figures is the negative of the 3GPP
coupling loss: CG = G_BS + G_UT − PL_b − SF − L_O2I − L_car.

---

## Verification

| What is checked | How | Test |
|---|---|---|
| Pathloss formulas, all scenarios and branches (PL1/PL2, NLOS, upper floors, RMa) | 11 spot values computed independently from the spec formulas | `test_propagation.py` |
| Breakpoint continuity | UMa/UMi continuous; RMa has a 7 mdB step that is inherent to the spec formula (switch on d2D, evaluation at d3D) | `test_propagation.py` |
| NLOS ≥ LOS everywhere | 400 distances per scenario | `test_propagation.py` |
| UMa h_E | P(h_E = 1 m) = 1/(1+C) = 0.4103 at h_UT = 22.5 m, d2D = 150 m; the rest uniform on {12, 15, 18, 21} | `test_propagation.py` |
| LOS probability | 11 spot values, including the UMa h_UT > 13 m term and both InH variants | `test_propagation.py` |
| O2I | wall losses at 3.5/6/28 GHz; low/high σ_P = 4.4/6.5 dB (Monte Carlo); legacy 20 dB + 0.5 d2D-in | `test_propagation.py`, `test_drop.py` |
| SF fields | unit variance; correlation exp(−d/d_cor) at 20 m and 50 m; 0 across floors; per-condition σ = 4/6/7 dB (UMa) | `test_propagation.py` |
| Layout | ISD spacing, 1/6/12 sites per ring; the 7 cluster copies tile the plane (no overlap, the hex ball of radius 4 is covered); virtual distances equal those of a 49-copy tiling; the sector rhombi tile the site hexagon within ±60° of boresight | `test_layout_antenna.py` |
| UT drop | counts per cell, min distance, indoor share, h_UT formula, E[d2D-in] = 25/3 m, high-loss share | `test_layout_antenna.py` |
| Antenna | peak = G_E,max + 10 log10 K; −3 dB at ±32.5°; 30 dB back-lobe cap; first null of the 10 × 0.8λ sub-array; a panel tilted 90° points down | `test_layout_antenna.py` |
| Association and geometry | serving = argmax; geometry recomputed from received powers; co-sited sectors share link losses; O2I loss is UT-specific (link-specific for legacy) | `test_drop.py` |
| **Wrap-around** | UTs dropped in the centre site and in the outer ring have the same geometry distribution (KS test at 1 %). Without wrap-around the outer ring is > 1 dB better. | `test_drop.py` |
| Reproducibility | fixed seed → identical drops; serial and 2-process runs agree (to 1e-9 dB, BLAS rounding) | `test_drop.py` |

The formulas and parameter tables were also cross-read against an independent
implementation, NVIDIA Sionna 2.1 (`sionna.phy.channel.tr38901`). Pathloss,
LOS probability, h_E, O2I and the SF σ / correlation distances agree. One
interpretation matches Sionna too: O2I links keep the LOS state of their
outdoor part for PL_b.

---

## Results (50 drops)

![Calibration CDFs](../results/p1_calibration_6ghz.png)

![System CDFs](../results/p1_system_uma35.png)

![Layout](../results/p1_layout_uma35.png)

| Run | UTs | CG p5 | CG p50 | CG p95 | Geom p5 | Geom p50 | Geom p95 | LOS (serving) |
|---|---:|---:|---:|---:|---:|---:|---:|---:|
| `calib-uma` (6 GHz) | 28500 | −154.1 | −123.4 | −89.6 | −18.2 | 2.4 | 22.4 | 0.46 |
| `calib-umi` (6 GHz) | 28500 | −141.6 | −112.8 | −78.5 | −7.0 | 3.5 | 21.1 | 0.72 |
| `calib-inh` (6 GHz) | 6000 | −90.7 | −72.0 | −52.1 | −3.3 | 4.8 | 27.6 | 0.98 |
| `system`, O2I 80/20 low/high (default) | 28500 | −129.7 | −105.4 | −79.2 | −3.3 | 5.0 | 22.6 | 0.46 |
| `system`, O2I low loss only | 28500 | −124.5 | −104.0 | −78.8 | −3.0 | 5.0 | 22.7 | 0.46 |
| `system`, O2I legacy 20 dB | 28500 | −131.4 | −111.6 | −82.8 | −3.3 | 4.9 | 22.7 | 0.45 |

All values in dB. `system` is UMa, 3.5 GHz, 100 MHz (273 PRB at 30 kHz),
53 dBm, 32T4R: (M, N, P) = (8, 8, 2) elements, (Mp, Np) = (2, 8) TXRUs of 4
elements tilted to 102°.

### Observations

- **UMa at 6 GHz is noise-limited in its lower tail.** 26 % of the UTs have a
  serving SNR below 0 dB, and 12 % have geometry below −10 dB. 92 % of those
  UTs sit in high-loss buildings: at 6 GHz the high-loss wall (70 % IRR
  glass, 30 % concrete) costs 30.7 dB, against 13.4 dB for the low-loss wall, plus 0.5 d2D-in and σ_P = 6.5 dB, on every link. How
  deep this tail goes depends directly on the O2I mix assumed for the
  calibration (see below).
- **At 3.5 GHz / 53 dBm the system is interference-limited.** O2I loss is
  UT-specific, so it shifts the serving and the interfering powers equally.
  Switching the O2I model moves coupling gain by up to ~6 dB but geometry by
  less than 0.3 dB.
- **Geometry saturates near 27 dB** in the sectorised scenarios. A UT on
  boresight still receives its two co-sited sectors 30 dB down (the element's
  A_max), so SIR ≤ 30 − 10 log10 2 ≈ 27 dB.
- **Some UTs are served by distant sites.** The serving 2-D distance has a
  95th percentile of ~880 m at ISD 500 m. The UMa LOS probability decays only
  like 18/d, so a LOS site 800 m away (≈ 105 dB at 3.5 GHz) can beat an NLOS
  site at 250 m (≈ 118 dB). This follows from the TR 38.901 model, not from a
  bug: association uses the true per-link LOS state.
- **The calibration antenna has a pattern null near the horizon.** Its
  sub-array is 10 elements at 0.8λ, so its first null sits at a zenith of
  ~94.8°. UTs 150–300 m from the site fall near it, which widens the
  coupling-gain spread.

---

## Assumptions to confirm

The TR 38.901 formulas above are verified. The calibration *set-up* values
below come from my recollection of TR 38.901 Table 7.8-1 and related
evaluation assumptions. They could not be checked against the spec text here.

| Item | Used | Confidence |
|---|---|---|
| Calibration BS antenna: one TXRU, M = 10, dV = 0.8λ | as stated | medium |
| Electrical downtilt 102° (UMa, UMi), 110° (InH) | as stated | medium (InH low) |
| InH TRP orientation: all TRPs face +x (bearing 0°), no mechanical tilt | as stated | **low**. Table 7.8-1 says "no sectorisation" for InH; the orientation of the directional element is unverified. |
| BS power 44 dBm (UMa/UMi, 6 GHz), 24 dBm (InH); 20 MHz; UT NF 9 dB | as stated | medium–high |
| **O2I mix for the calibration: 50 % low / 50 % high loss** | as stated | **low**. This controls the depth of the 6 GHz UMa/UMi tails. |
| System O2I mix: 80 % low / 20 % high loss (TR 38.802 / M.2412 style) | as stated | medium |
| System BS power: 46 dBm per 20 MHz → 53 dBm for 100 MHz | as stated | medium |
| Handover margin 0 dB; RSRP from port 0; isotropic UT | as stated | high |

Each item is a single field of `ScenarioConfig` / `BSAntennaConfig`, and the
calibration presets are built in one place (`calibration_38901` in
`nrsls/config/scenario.py`).

---

## Comparing against reference curves

Put two-column CSV files (`x, cdf`, with cdf in 0…1) into a directory, named
`<preset>_coupling.csv` and `<preset>_geometry.csv`, then run:

```bash
python run_sls.py --preset calib-uma calib-umi calib-inh --drops 50 \
    --reference-dir refs/ --json results/p1_calibration.json
```

For each available curve the runner prints and stores the gap (simulated minus
reference) at the 5/10/20/50/80/90/95th percentiles. `metrics/calibration.py`
has the same functions for notebooks. The plan's "within ~1 dB" criterion is
evaluated as `max_abs_gap`.
