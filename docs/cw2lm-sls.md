# Codeword-to-layer mapping in the system simulator

The full-buffer SU-MIMO loop can carry more than one codeword per UT (`FullBufferConfig.cw_mapping`). Each codeword has its own CQI, MCS, OLLA loop and HARQ process. The CSI-stage probe ([cw2lm-sls-probe.md](cw2lm-sls-probe.md)) only estimated what more codewords could gain; this runs them end to end.

| `cw_mapping` | Codewords | Ranks 1 / 2 / 3 / 4 |
|---|---|---|
| `alt1` (default) | NR: one codeword up to rank 4 | {1} / {2} / {3} / {4} |
| `alt2` | up to 2, split as NR does for ranks 5–8 (TS 38.211 Table 7.3.1.3-1), smaller group first | {1} / {1,1} / {1,2} / {2,2} |
| `alt3` | one per layer | {1} / {1,1} / {1,1,1} / {1,1,1,1} |

The split is `nrdlsim.layer_mapping.layer_groups`. Layers are in precoder-column order, which for the SVD precoders is strongest first.

```bash
python examples/run_full_buffer.py --cw-mapping alt3 [--olla-per-rank] [--harq-adaptive]
python examples/cw2lm_sls.py --drops 2 --slots 160 --jobs 4     # the study below, ~2 h
python -m pytest tests/test_cw_mapping.py
```

## Model

**CSI** (`phy/csi.py`). For each candidate rank the UT computes the per-layer MMSE-IRC SINR with the candidate precoder, as before. With several codewords it then gives each codeword a wideband and a sub-band CQI from the SINRs of its own layers (MIESM, highest CQI meeting the BLER target), as TS 38.214 reports for two codewords; for three or four codewords this is an extension. The rank maximises Σ_CW layers(CW) × SE(CQI_CW), which is the old rank × SE(CQI) with one codeword. So the rank choice knows the codeword split ("codeword-aware RI").

**Transmission** (`engine/link.py`). A new transmission is one TB per codeword on the same RBGs, rank and precoder:
- MCS from the codeword's sub-band CQIs on the allocated RBGs, minus the codeword's OLLA offset;
- TBS from TS 38.214 §5.1.3.2 with the codeword's number of layers;
- per-layer SINR from one MMSE-IRC over all layers of the transmission (the other codewords' layers are interference), then each TB's own layers, chase combining and MIESM → BLER per TB.

The PF metric sums the codewords' rates, Σ_CW layers × log2(1 + SINR_sb,CW), which is the old rank × log2(1 + SINR_sb) with one codeword.

**OLLA** (`mac/link_adaptation.py`). One loop per UT and codeword index, and with `olla_per_rank` also per transmission rank (Nokia's "OLLA per CW per rank"). Each loop follows its own first-transmission ACK/NACKs.

**HARQ.** Every TB is its own HARQ process. When some codewords of a transmission fail, the retransmission slot carries the failed TBs again, chase-combined on their layers, and refills every other codeword with a new TB. In NR each TB has its own NDI. The retransmission keeps the RBGs and rank, and the retransmitted TBs keep their MCS. Two policies for the rest (`harq_adaptive`):
- **fixed** (default): the first transmission's precoder; refills use the first transmission's CQI with the current OLLA offset. This is the existing single-codeword behaviour, extended to refills, and it is Apple R1-2608231's assumption ("HARQ refills an ACKed codeword").
- **adaptive**: if the UT's current report has the same rank, the whole PDSCH takes the current precoder (DM-RS makes precoding transparent to the UT), and refills take the current per-codeword CQIs.

A transmission whose codewords all decode, or that runs out of transmissions, ends; a codeword dropped after the last transmission is refilled like a decoded one while the others are still retransmitted.

**KPIs** (`FullBufferResult`): besides the existing ones, `mean_codewords` (codewords per new transmission), `rank_hist` (rank 1–4 shares of new transmissions) and `bler_first_cw` (first-transmission BLER per codeword index). `bler_first` and `mean_mcs` are per TB, `mean_rank` per new transmission.

**Scope.** SU-MIMO only: `cw_mapping` other than `alt1`, `olla_per_rank` and `harq_adaptive` raise an error with `mu_mimo`. The receiver is MMSE-IRC; SIC is the next step (WP4). Full-buffer traffic. UCI/DCI overhead for more codewords is not modelled.

## Verification

- **Alt 1 is bit-identical.** Every field of `FullBufferResult` is unchanged for Type-I, eType-II, SVD, sub-band SVD, per-RB SVD and MU-MIMO on a fixed-seed drop.
- **The multi-codeword path reproduces NR where it must.** With `max_rank = 1` every mapping has one codeword, and `alt3` gives exactly the `alt1` result through the multi-codeword code (per-codeword SINR arrays, TBs, OLLA array, HARQ groups). Up to rank 2, `alt2` and `alt3` split the layers the same way and give identical results. Both are tests.
- `tests/test_cw_mapping.py` also checks the per-codeword CQIs against each codeword's own layers, the codeword-aware rank, the OLLA loops, the TB split, the retransmission refill and the adaptive re-precoding.

## Study: Dense Urban A, full buffer

`examples/cw2lm_sls.py` runs the three mappings on the scenario of the CSI-stage probe, so the end-to-end result can be set against the probe's potential:

- Dense Urban-eMBB A preset: 19 sites × 3, ISD 200 m, 4 GHz, 10 MHz at 15 kHz, 32T (8,8,2;2,8), UT (1,2,2), 10 UTs per cell (570 UTs), 80 % indoor at 3 km/h and 20 % in car at 30 km/h.
- SU-MIMO up to rank 4, MMSE-IRC, RBG = sub-band = 4 PRB, 2 PDCCH symbols and 9 overhead REs per PRB, OLLA per UT and codeword.
- Two CSI cases: eType-II every 20 ms with a 4 ms delay (Apple-like) and unquantised wideband SVD every 2 ms without delay (Nokia-like).
- Both retransmission policies, fixed and adaptive.
- 2 drops × 160 slots, 40 of them warm-up. All configurations run on the same drops.

Gain over Alt 1 in cell SE / 5th-percentile UT SE / median UT SE:

| CSI | HARQ | Alt 1 cell SE (bit/s/Hz) | Alt 2 | Alt 3 |
|---|---|---|---|---|
| eType-II, 20 ms / 4 ms | adaptive | 4.62 | −2.4 / −1.8 / −3.3 % | −3.5 / −3.3 / −4.2 % |
| | fixed | 4.60 | −4.5 / −5.4 / −5.0 % | −7.1 / −9.4 / −8.1 % |
| SVD, 2 ms / 0 | adaptive | 5.06 | −1.5 / −2.4 / −1.6 % | −3.1 / −6.2 / −4.0 % |
| | fixed | 5.06 | −3.3 / −7.7 / −4.3 % | −6.4 / −11.5 / −8.5 % |

Each drop on its own gives the same cell-SE gains to within 0.6 points. For comparison, the probe's CSI-stage potential with codeword-aware RI is +0.8 / +1.2 % (eType-II) and +0.3 / +0.5 % (SVD) for Alt 2 / Alt 3.

Where the difference goes, with adaptive HARQ:

| CSI | Mapping | First-tx BLER per codeword | RBGs carrying retransmissions | Rank 2 / 3 / 4 |
|---|---|---|---|---|
| eType-II | Alt 1 | 0.16 | 16 % | 75 / 22 / 2 % |
| | Alt 2 | 0.18, 0.17 | 29 % | 75 / 20 / 5 % |
| | Alt 3 | 0.19, 0.18, 0.24, 0.26 | 33 % | 74 / 22 / 3 % |
| SVD | Alt 1 | 0.15 | 13 % | 50 / 42 / 7 % |
| | Alt 2 | 0.15, 0.16 | 23 % | 53 / 36 / 10 % |
| | Alt 3 | 0.16, 0.16, 0.20, 0.25 | 30 % | 52 / 39 / 8 % |

## Observations

- **More codewords lose here, where the CSI stage promised +0.3 to +1.2 %.** In the 160-slot runs every combination of CSI and HARQ policy loses 1.5–7 % of cell SE, and also loses at the median and the 5th percentile (up to −11.5 %); Alt 3 loses 1.5–2 times as much as Alt 2. Part of this is OLLA convergence; with the loops settled, Alt 3 still loses 1–2 % of cell SE and 2.5–4 % at the median and the 5th percentile (next section).
- **Per-codeword link adaptation costs more than it gains.** The first-transmission BLER rises with the codeword index; the codewords on the weakest layers run at 20–30 % instead of 10 % in the 160-slot runs, and still at 14–16 % in the longer ones. The probe found per-layer SINR predictions off by 3–4 dB (standard deviation) and optimistic by 2–4 dB on average. A single codeword averages that error over its layers and has one OLLA loop that sees every transmission. A per-layer codeword sees its layer's error in full, and the loop of codeword 3 or 4 only moves at ranks 3–4, a quarter (eType-II) to a half (SVD) of the transmissions, so it also takes longer to converge.
- **Per-codeword HARQ ties up resources.** A transmission needs a retransmission slot whenever any of its codewords fails, so the share of RBGs carrying retransmissions doubles (13–16 % → 23–39 %). Those RBGs keep the old allocation and rank, and their refills use older CSI. With the first transmission's precoder (fixed) the loss is about twice that with re-precoding (adaptive).
- **Rank adaptation barely moves.** With Alt 2, codeword-aware RI moves 2–6 % of the transmissions out of rank 3, to ranks 2 and 4. The system runs rank 2 most of the time (three quarters of the eType-II transmissions), where Alt 2 and Alt 3 are the same mapping.
- **Apple's system-level result is reproduced in sign and order.** Apple R1-2608231 reports −4 to −12 % (Alt 2) and −8 to −18 % (Alt 3) user SE with FTP 1 at 30 % and 50 % load, with HARQ refills. The Apple-like case here with fixed HARQ gives −4.5 / −7.1 % cell SE and −5.4 / −9.4 % at the 5th percentile. Nokia's +12 to +28 % assumes SIC, ideal CSI and interference estimation, and directive UTs with blockage, none of which is in this run.

## Longer runs: how much of the loss is OLLA convergence?

In 160-slot runs even Alt 1 runs above the 10 % BLER target (0.15–0.16), so the OLLA loops have not settled. One drop of 480 slots (160 of them warm-up), adaptive HARQ, Alt 1 against Alt 3 (`python examples/cw2lm_sls.py --drops 1 --slots 480 --warmup 160 --harq adaptive --mappings alt1,alt3 --out results/cw2lm_sls_long.json`, about 1 h):

| CSI | Alt 1 cell SE | Alt 3: cell / 5th pct / median | Same drop, 160 slots (cell) | First-tx BLER: Alt 1; Alt 3 per codeword | RBGs carrying retransmissions, Alt 1 / Alt 3 |
|---|---|---|---|---|---|
| eType-II, 20 ms / 4 ms | 4.66 | −1.2 / −3.4 / −3.7 % | −3.5 % | 0.10; 0.11, 0.11, 0.14, 0.16 | 9 / 18 % |
| SVD, 2 ms / 0 | 5.09 | −1.8 / −4.1 / −2.5 % | −3.2 % | 0.10; 0.10, 0.10, 0.12, 0.16 | 8 / 19 % |

Half to two-thirds of the short-run cell-SE loss is OLLA convergence. With 320 measured slots, Alt 1 and the first two or three codewords of Alt 3 are near the target, and only the loop of codeword 4, which moves at rank 4 only, is still above it. What remains once the loops have settled is a loss of 1–2 % in cell SE and 2.5–4 % at the median and the 5th percentile, with twice the RBGs carrying retransmissions.

## Limitations

- **Short runs.** The main table uses 120 measured slots per drop, where the OLLA loops have not settled; the 480-slot check covers one drop and adaptive HARQ only.
- **Link abstraction.** BLER comes from MIESM and a formula waterfall (`nrdlsim.link_abstraction`), not from NR LDPC link-level curves, and MIESM has no per-MCS calibration factor. How MIESM scores one codeword over unequal layers is exactly what decides Alt 1 against Alt 3.
- **Receiver and UT.** MMSE-IRC only (SIC is WP4); isotropic UT elements without blockage.
- **HARQ.** Retransmissions keep their RBGs and rank. A fully adaptive scheduler that moves a retransmission to new RBGs or a new rank is not modelled; the fixed and adaptive policies bracket the precoder question only.
- **Traffic.** Full buffer, where resources lost to retransmissions are lost to the cell. With FTP traffic at low load they would cost delay rather than throughput.
