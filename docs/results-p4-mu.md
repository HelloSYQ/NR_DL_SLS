# MU-MIMO — full buffer, Type-I / eType-II / SVD reports

This is the first P5 extension of the [module plan](module-plan.md): multi-user MIMO on the phase-3 full-buffer system, UMa 3.5 GHz, 100 MHz, 32T4R, 10 UTs per cell (see [results-p3.md](results-p3.md) for the rest of the set-up).

Reproduce with:

```bash
python examples/run_full_buffer.py --mu --max-rank 2 --tag p4_mu   # MU, <= 4 UTs / 8 layers
python examples/run_full_buffer.py --tag p3                        # SU reference
python examples/plot_su_vs_mu.py
```

The same MU pipeline is benchmarked against the TR 37.910 Dense Urban self-evaluation in [benchmark-tr37910.md](benchmark-tr37910.md). There, with ideal sub-band CSI, it reproduces the 3GPP companies' average of 11.04 bit/s/Hz/TRxP.

## Results

4 drops × 200 slots (40 warm-up), 2280 UTs per configuration, same drops and seeds for SU and MU. SU is the phase-3 run (RI ≤ 4, re-run with per-UT samples saved: bit-identical). MU uses RI ≤ 2, ≤ 4 UTs and ≤ 8 layers per RBG.

| Reports | Mode | Cell SE [bit/s/Hz] | 5 %-ile UT SE | Median UT SE | 1st-tx BLER | Mean MCS | UTs / layers per RBG | MU SINR estimate − actual |
|---|---|---|---|---|---|---|---|---|
| Type-I (sub-band i2) | SU | 5.83 | 0.192 | 0.508 | 0.117 | 15.1 | 1 / 2.18 | – |
| | MU | **7.69 (+32 %)** | **0.220 (+15 %)** | 0.595 (+17 %) | 0.125 | 7.2 | 3.32 / 6.11 | +2.5 dB |
| eType-II (combination 6) | SU | 6.13 | 0.213 | 0.531 | 0.116 | 15.6 | 1 / 2.18 | – |
| | MU | **9.48 (+55 %)** | **0.288 (+36 %)** | 0.755 (+42 %) | 0.097 | 7.2 | 3.76 / 7.18 | +1.6 dB |
| SVD (ideal, wideband) | SU | 6.27 | 0.209 | 0.542 | 0.115 | 14.5 | 1 / 2.44 | – |
| | MU | **9.64 (+54 %)** | **0.269 (+29 %)** | 0.747 (+38 %) | 0.100 | 7.5 | 3.67 / 7.00 | +1.5 dB |

An earlier version limited MU to ≤ 2 UTs / 4 layers, because it charged 4 DM-RS symbols above 4 layers (see below). It gave 7.24 / 8.11 / 8.27 cell SE.

![SU vs MU](../results/p4_su_vs_mu_cdf.png)

### Observations

- **MU-MIMO gains 32–55 % in cell SE and 15–36 % at the cell edge** over SU with the same reports, at 3.3–3.8 co-scheduled UTs and 6–7 layers per RBG. Per-layer SINR drops (mean MCS 15 → 7), but three to four times the layers share each RBG.
- **eType-II's advantage over Type-I grows in MU**, as expected: +23 % cell SE and +31 % at the 5th percentile in MU, against +5 % / +11 % in SU. eType-II reaches 98 % of the *wideband* unquantised-SVD MU cell SE and beats it at the edge, because its per-sub-band precoder follows the frequency selectivity. The per-sub-band ideal-CSI bound (`svd_sb`), evaluated in Dense Urban, is 23 % above eType-II.
- **Type-I pairs less and worse.** Its coarse single-beam PMI hides the leakage between co-scheduled UTs: the gNB's MU-SINR estimate is 2.5 dB optimistic, against 1.5–1.6 dB for eType-II / SVD, and OLLA runs a higher BLER (12.5 %).
- **Link adaptation holds the target**, at 10–12.5 % first-transmission BLER with the separate MU OLLA.

## Simplifications (to revisit)

- **SU CSI only.** There is no MU-CQI and no rank adaptation for MU: RI is restricted to ≤ 2 for all UTs. A UT reporting rank > 2 would only be scheduled alone (not exercised with RI ≤ 2).
- **Linear precoding on the reports only.** RZF (or ZF) on the reported vectors with equal power per layer; no SLNR, no per-layer power allocation, and no model of the CSI error (the MU OLLA learns it).
- **Greedy pairing is myopic** (see above); no user grouping or angular pre-selection.
- **Ideal DM-RS channel estimation** of the co-scheduled layers at the UT.
- **No overhead beyond 2 DM-RS symbols and 1 PDCCH symbol** in this UMa run, as in phase 3. The Dense Urban benchmark includes PDCCH, CSI-RS, SSB and TRS overhead.

## Method

The gNB knows only what the UTs report: the SU CSI (RI, PMI, sub-band CQI) of TS 38.214, measured with CSI-IM on the inter-cell interference only. The UTs are not told about MU scheduling.

| Item | Model |
|---|---|
| Co-scheduling | Per RBG, greedy. The PF owner of the RBG (or its HARQ retransmission) opens the set. UTs are added while the PF metric Σ log2(1 + SINR) / R̄ of the set grows. Limits: ≤ 6 UTs, ≤ 12 layers per RBG (default) and rank ≤ 2 per co-scheduled UT. |
| CSI | RI restricted to ≤ 2 (`--max-rank 2`) so that every UT can be paired. Type-I (sub-band i2), Rel-16 eType-II combination 6, or SVD (unquantised wideband eigenvectors, the ideal-CSI reference). |
| Precoder | Regularised ZF (MMSE precoder, default) on the gNB's model of each reported layer, g_l = √(s_l r_l) v_l: W = Gᴴ(GGᴴ + L·I)⁻¹. Here s_l is the SU CQI SINR per layer and r_l the UT's rank, in units of the noise-plus-inter-cell interference. This tends to ZF at high SINR and to matched filtering at the cell edge. `mu_precoder='zf'` gives W = V(VᴴV + δI)⁻¹ with δ = 10⁻³. Columns have unit norm, and each layer gets power 1/L, so the total transmit power is fixed. A UT alone on an RBG keeps its reported precoder at full power. |
| gNB MU-SINR estimate | From the same model: SINR_l = (\|g_lᴴw_l\|²/L) / (1 + Σ_{j≠l} \|g_lᴴw_j\|²/L). For ZF this is SU CQI SINR × power split (r_u / L) × projection loss ρ = \|vᴴw\|². This gives the pairing metric and the MCS. |
| MU link adaptation | A separate OLLA per UT for MU transmissions (0.5 dB, 10 % BLER target). The MU back-off relative to the SU one also scales the SINRs in the pairing metric, so UTs whose MU transmissions fail get paired less. |
| UT receiver | MMSE over all layers of the serving cell. The co-scheduled layers are known interference (their effective channels come from DM-RS), and the inter-cell interference is whitened as in SU. |
| HARQ | A retransmission joins the co-scheduled sets of its RBGs as a forced member. Its precoder is recomputed for the new set, and chase combining adds the SINRs. It keeps its TB, rank and MCS. |
| DM-RS | 24 REs per PRB for any layer count. Up to 4 layers use type-1 single-symbol DM-RS plus 1 additional position. Up to 8 layers use type-1 double-symbol front-loaded DM-RS without an additional position (the low-mobility configuration), and up to 12 layers use type-2 double-symbol DM-RS. Both cost the same. `mu_dmrs_overhead=True` instead charges double-symbol + 1 additional pair (48 REs) above 4 layers, and the pairing metric then pays that cost. |
| Inter-cell interference | The explicit interferers transmit their actual MU precoders (all co-scheduled layers). |

Checks (`tests/test_mu_mimo.py`):

- ZF nulls the other reported layers, and orthogonal reports lose nothing;
- the pairing takes orthogonal UTs, rejects aligned ones and respects the UT, layer and DM-RS limits;
- the MU path with pairing disabled reproduces the SU results exactly;
- the MU mode co-schedules and is reproducible.

SU mode is bit-identical to the phase-3 code.

## How the design got here

The first full-system MU run was *worse* than SU with every report type. That run allowed up to 4 UTs / 8 layers, and a retransmission took its RBGs alone. The engine's diagnostic KPIs showed why (one drop, eType-II, 120 slots):

| Variant | Cell SE | 5 %-ile | UTs / layers per RBG | RBG-slots with retransmissions | MU SINR estimate − actual |
|---|---|---|---|---|---|
| SU | 5.80 | 0.215 | 1 / 1.9 | 10.5 % | – |
| MU ≤ 4 UTs, exclusive retransmissions | 5.55 | 0.160 | 3.5 / 6.6 | 35.5 % | +2.1 dB |
| MU ≤ 4 UTs, co-scheduled retransmissions | 7.53 | 0.225 | 3.7 / 7.1 | 32.7 % | +1.6 dB |
| MU ≤ 3 UTs / 6 layers, co-scheduled retransmissions | 7.26 | 0.228 | 2.9 / 5.6 | 24.0 % | +1.5 dB |
| MU ≤ 2 UTs, co-scheduled retransmissions | **8.01** | **0.268** | 2.0 / 3.8 | 16.7 % | +0.9 dB |

Rows 3–5 were measured before the DM-RS term was added to the pairing metric. With it, the 4-UT case gives 7.15 / 0.246: the greedy search then stops at about 2.7 UTs, because it pays the DM-RS cost once a set passes 4 layers but never reaches the fourth UT that could justify it. The 2-UT case never passes 4 layers and is unaffected.

- **Exclusive MU retransmissions waste the band.** Every MU TB spans many RBGs and 10 % of them fail. When each failure takes its RBGs for a single UT, more than a third of the RBG-slots end up single-user. Co-scheduling the retransmissions fixed this.
- **The 4-symbol DM-RS charge was wrong, and it hid the value of larger sets.** These runs charged double-symbol DM-RS *plus* an additional double-symbol position (18 % of the data REs) above 4 layers, which made 2 UTs × 2 layers look best. The Dense Urban benchmark exposed this. The low-mobility DM-RS for ports 0–7 (double-symbol front-loaded, no additional position) costs the same 24 REs as the ≤ 4-layer DM-RS. Without the extra charge, ≤ 4 UTs / 8 layers wins: in UMa eType-II MU goes from 8.11 to 9.48, and in Dense Urban from 6.80 to 8.90 (one drop). The MU-SINR estimate still gets more optimistic with every added layer, but the multiplexing gain outweighs it.
