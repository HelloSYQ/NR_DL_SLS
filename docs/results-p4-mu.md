# MU-MIMO — full buffer, Type-I / eType-II / SVD reports

This is the first P5 extension of the [module plan](module-plan.md): multi-user MIMO on the phase-3 full-buffer system, UMa 3.5 GHz, 100 MHz, 32T4R, 10 UTs per cell (see [results-p3.md](results-p3.md) for the rest of the set-up).

Reproduce with:

```bash
python examples/run_full_buffer.py --mu --max-rank 2 --tag p4_mu            # MU, defaults
python examples/run_full_buffer.py --mu --max-rank 2 --mu-max-ues 4 \
    --mu-max-layers 8 --codebooks etype2 --tag p4_mu48                      # sensitivity
python examples/run_full_buffer.py --tag p3                                 # SU reference
python examples/plot_su_vs_mu.py
```

> **Status:** the 4-drop system runs are in progress; the results section follows.

## Method

The gNB knows only what the UTs report: the SU CSI (RI, PMI, sub-band CQI) of TS 38.214, measured with CSI-IM on the inter-cell interference only. The UTs are not told about MU scheduling.

| Item | Model |
|---|---|
| Co-scheduling | Per RBG, greedy. The PF owner of the RBG (or its HARQ retransmission) opens the set. UTs are added while the PF metric Σ log2(1 + SINR) / R̄ of the set grows. Limits: ≤ 2 UTs, ≤ 4 layers per RBG (default; see the sensitivity case) and rank ≤ 2 per co-scheduled UT. |
| CSI | RI restricted to ≤ 2 (`--max-rank 2`) so that every UT can be paired. Type-I (sub-band i2), Rel-16 eType-II combination 6, or SVD (unquantised wideband eigenvectors, the ideal-CSI reference). |
| Precoder | Zero forcing on the stacked reported precoders: W = V (VᴴV + δI)⁻¹ with unit-norm columns, δ = 10⁻³. Each layer gets power 1/L, so the total transmit power is fixed. A UT alone on an RBG keeps its reported precoder at full power. |
| gNB MU-SINR estimate | SU CQI SINR × power split (r_u / L) × ZF projection loss ρ = \|vᴴw\|². This gives the pairing metric and the MCS. |
| MU link adaptation | A separate OLLA per UT for MU transmissions (0.5 dB, 10 % BLER target). The MU back-off relative to the SU one also scales the SINRs in the pairing metric, so UTs whose MU transmissions fail get paired less. |
| UT receiver | MMSE over all layers of the serving cell. The co-scheduled layers are known interference (their effective channels come from DM-RS), and the inter-cell interference is whitened as in SU. |
| HARQ | A retransmission joins the co-scheduled sets of its RBGs as a forced member. Its precoder is recomputed for the new set, and chase combining adds the SINRs. It keeps its TB, rank and MCS. |
| DM-RS | Up to 4 layers: type-1 single-symbol DM-RS (132 data REs per RB). A TB sharing an RBG with more than 4 layers needs ports 4–7, i.e. double-symbol DM-RS (4 × 12 DM-RS REs, 108 data REs per RB). The pairing metric pays that cost. |
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
- **More co-scheduled layers do not pay off here.** The gNB's MU-SINR estimate becomes more optimistic with every added layer (+0.9 dB at 2 UTs, +1.6 dB at 4). The per-UT MU OLLA corrects the MCS but not the pairing decisions. Above 4 layers, the double-symbol DM-RS also costs 18 % of the data REs. With 4-antenna UTs, rank-2 reports and ZF on the reports, 2 UTs × 2 layers is the best setting. The default is ≤ 2 UTs / ≤ 4 layers, with the 4 UTs / 8 layers case kept as a sensitivity run.
