# NR Downlink System-Level Simulator (`nrsls`) — Module Plan

Status: **P1 implemented** (see [calibration-p1.md](calibration-p1.md));
P2 next. Decisions from §8 are confirmed: UMa 3.5 GHz / 100 MHz / 32T4R
first, Type-I + eType-II CSI, `nrdlsim` as a pinned git dependency, K = 8
explicit interferers.

Goal: a multi-cell, multi-UE NR downlink (PDSCH) system-level simulator (SLS)
that reuses the link-level simulator `nrdlsim`
(`HelloSYQ/Claude`, branch `claude/nr-downlink-simulator-erq2qt`) for the
link-to-system abstraction and the PHY building blocks. Output: the standard
3GPP / ITU-R KPIs (coupling loss, geometry SINR, UE throughput CDF, cell
average and 5 %-ile spectral efficiency).

Reference specs: TR 38.901 (§7.2–7.6 scenarios, pathloss, LOS, O2I, fast
fading, §7.8 calibration), TS 38.211/212/214 (numerology, MCS/TBS, CSI,
Type-I and Rel-16 enhanced Type-II codebooks), TR 38.802 / TR 36.814 (evaluation assumptions, traffic
models), ITU-R M.2412 (IMT-2020 test environments and KPIs).

---

## 1. What the SLS takes from the LLS

The LLS already provides these pieces. The SLS imports them as a pinned
dependency (`pip install git+…/Claude@<commit>`) and does not copy them.

| `nrdlsim` module | Reused as | Changes needed |
|---|---|---|
| `link_abstraction.py` | PHY abstraction: BICM MI, MIESM effective SINR, BLER waterfall, `required_eff_sinr_db` | none (optional: export per-MCS AWGN BLER tables) |
| `mcs_tables.py`, `tbs.py`, `resource_grid.py` | MCS/CQI tables, TBS, DM-RS overhead | none |
| `receiver.batch_mmse_sinr` | per-RB post-equaliser SINR | **extend** to MMSE-IRC with a coloured interference covariance `R_I` (today it assumes white noise only) |
| `csi.compute_csi`, `cqi_required_sinr_db` | RI/CQI selection logic | **extend**: interference-aware (CSI-IM), Type-I and eType-II codebook PMI, sub-band CQI |
| `scheduler.Scheduler` (OLLA, CQI→MCS) | per-UE link adaptation | wrap per UE; the resource allocation moves to the multi-UE scheduler |
| `channel_models`: `build_panel`, `rotation_matrix`, `element_field`, `_location_phase`, CDL ray machinery | antenna panels, element pattern, orientation, ray summation | reused inside the new 38.901 stochastic (UMa/UMi/InH/RMa) channel |
| `config.py` dataclasses | carrier / PDSCH / antenna / HARQ sub-configs | wrapped by the SLS scenario config |

The main gap: the LLS generates **one link with a fixed PDP (TDL/CDL) at a
given SNR**. The SLS needs **geometry-driven** links. Each link gets its own
pathloss, shadowing, LOS state, and large-scale parameters (LSPs: DS, ASD,
ASA, ZSD, ZSA, K, SF), and SINR is set by other-cell interference, not by an
SNR sweep.

---

## 2. Package layout

```
nrsls/
  config/            scenario.py        # ScenarioConfig: UMa/UMi/InH/RMa presets (TR 38.901 Table 7.2-1, M.2412)
  topology/          layout.py          # hex 19-site x 3-sector grid, InH 12-TRP layout, wrap-around
                     ue_drop.py         # UE dropping, indoor/outdoor, floor, min 2D distance, speed
  antenna/           array.py           # multi-panel array (Mg,Ng,M,N,P), TXRU virtualisation, electrical tilt
  propagation/       pathloss.py        # TR 38.901 Table 7.4.1-1 (PL, breakpoint, h_E)
                     los.py             # LOS probability Table 7.4.2-1
                     o2i.py             # O2I penetration Table 7.4.3-1/2 (low/high loss)
                     lsp.py             # LSPs + cross-correlation (Table 7.5-6), spatially consistent (7.5 step 4 / 7.6.3)
                     fast_fading.py     # TR 38.901 §7.5 steps 5-11: clusters, rays, XPR, H(f,t) per link
  link/              link_budget.py     # Tx power, noise (kTB + NF), coupling loss, RSRP
                     association.py     # serving-cell selection (RSRP / coupling loss incl. antenna gain)
                     interference.py    # per-UE interferer set: K strongest with full MIMO H, rest wideband
  phy/               sinr.py            # post-MMSE-IRC per-RB SINR with R_I (wraps nrdlsim receiver)
                     codebook/
                       common.py        # 2-D DFT beam grid (N1,N2,O1,O2), port layout, codebook config (shared)
                       type1.py         # TS 38.214 §5.2.2.2.1 Type-I single-panel: codebook + PMI search
                       etype2.py        # TS 38.214 §5.2.2.2.5 Rel-16 eType-II: SD beams, FD DFT basis, quantised coefficients
                       payload.py       # CSI report size (UCI bits) per codebook config
                     csi.py             # CSI-RS/CSI-IM: RI/PMI/CQI (wideband + sub-band), report delay
                     l2s.py             # adapter to nrdlsim MIESM + BLER (+ HARQ chase combining)
  mac/               scheduler.py       # PF / RR, per-RBG frequency-selective, SU-MIMO (MU-MIMO later)
                     link_adaptation.py # per-UE OLLA + CQI->MCS (reuses nrdlsim Scheduler logic)
                     harq.py            # multiple HARQ processes per UE, K1 timing, max Tx
  traffic/           models.py          # full buffer; FTP model 1/3 (TR 36.814 / 38.802), arrival rate -> RU
  engine/            drop.py            # one drop: geometry -> LSP -> channels -> TTI loop
                     simulator.py       # multi-drop driver, seeds, warm-up, parallel drops
  metrics/           kpi.py             # coupling loss, geometry, UE tput, cell SE, 5 %-ile, UPT, RU
                     calibration.py     # compare against TR 38.901 §7.8 / 38.802 calibration CDFs
  plots/             cdf.py
run_sls.py
tests/
docs/
```

---

## 3. Modules in detail

### 3.1 `config/scenario.py`: scenario configuration
- Presets: **UMa** (ISD 500 m, h_BS 25 m), **UMi-Street Canyon** (ISD 200 m,
  h_BS 10 m), **InH-Office** (120×50 m, 12 TRPs, open/mixed), **RMa**
  (ISD 1732 m, h_BS 35 m).
- Carrier: f_c, μ, N_RB (e.g. 3.5 GHz, 30 kHz, 100 MHz → 273 RB), BS total
  power (e.g. 46 dBm per 20 MHz, scaled with BW), UE NF 9 dB, BS NF 5 dB.
- UE: count per sector (e.g. 10), indoor ratio 80 %, speed 3 km/h (indoor) and
  30 km/h (in-car/outdoor, optional), UE antenna config.
- Simulation control: drops, TTIs per drop, warm-up TTIs, seed, number of
  full-MIMO interferers K, wrap-around on/off.
- Composes the `nrdlsim` `CarrierConfig`/`PDSCHConfig`/`HARQConfig`.

### 3.2 `topology/`: layout and UE drop
- Hex grid of 19 sites × 3 sectors (57 cells), sector boresights 30°/150°/270°.
- **Wrap-around**: each UE sees the closest of the 7 replicas of each site.
  Without it, edge cells see too little interference and the geometry is
  optimistic.
- UE drop: uniform per sector area, `d_2D ≥ d_min` (35 m UMa, 10 m UMi).
  Indoor UEs get a floor index (h_UT = 3(n_fl−1)+1.5 m) and `d_2D-in`.
- InH: 12 TRPs at 20 m spacing, ceiling-mounted.

### 3.3 `antenna/array.py`: BS/UE arrays
- TR 38.901 §7.3 multi-panel `(Mg, Ng, M, N, P)`, e.g. 32T: (1,1,8,8,2) elements
  virtualised to 32 TXRUs (sub-array of M/Mp vertical elements with
  electrical tilt weights). The TXRU ports are what the codebook sees.
- Reuses `nrdlsim.channel_models.build_panel`, `rotation_matrix` and
  `element_field` (38.901 pattern, pol ±45°). New code: TXRU virtualisation,
  so the port-domain channel is `H_port = H_elem · V_txru`.
- Mechanical downtilt + electrical tilt (UMa typically 12° total). UE: 2/4 Rx
  omni (0 dBi), dual-pol, random orientation (optional).

### 3.4 `propagation/`: large-scale model
- `pathloss.py`: PL_LOS / PL_NLOS per scenario, breakpoint distance d'_BP with
  effective heights (h_E per UMa rule), validity ranges.
- `los.py`: Pr_LOS(d_2D, h_UT) per scenario. The LOS state is drawn per link.
- `o2i.py`: building penetration (low-loss / high-loss mix, glass/concrete
  formula), indoor loss 0.5·d_2D-in, extra σ_P.
- `lsp.py`: log-normal LSPs {SF, K, DS, ASD, ASA, ZSD, ZSA} with the
  cross-correlation matrix (Cholesky) and ZSD/ZOD-offset formulas that depend
  on distance and height (Tables 7.5-7/8/9/10/11).
  **Spatial consistency**: the LSPs are drawn from 2-D correlated Gaussian
  maps (correlation distances from Table 7.5-6), one map per site, so nearby
  UEs have correlated shadowing. Links to the 3 sectors of one site share the
  same LSPs.

### 3.5 `propagation/fast_fading.py`: 38.901 stochastic channel
This generalises the LLS `CDLChannel`. The LLS draws cluster delays, powers
and angles from a CDL table. Here they are generated randomly from the link's
LSPs, following §7.5 steps 5–11:
- delays (r_τ scaling, K-dependent LOS scaling), cluster powers with
  per-cluster shadowing, dropping clusters < −25 dB;
- AoA/AoD/ZoA/ZoD via the wrapped-Gaussian / Laplacian construction with
  LOS-offset (C_φ, C_θ scaling), 20 rays per cluster with the Table 7.5-3
  offsets. The two strongest clusters are split into 3 sub-clusters;
- ray coupling, XPR per ray, random initial phases;
- `H[u,s](f,t)` built with the **same ray-summation kernel as the LLS CDL**
  (`element_field` + `_location_phase` + Doppler). The kernel is refactored in
  `nrdlsim` into a function shared by both simulators.
- Output per link: `H[t, rb, n_rx, n_port]` evaluated per RB (as in the LLS)
  and per slot (Doppler from the UE velocity).
- Cost control: full fast fading only for the serving cell + K strongest
  interferers (K ≈ 8). The other cells contribute wideband average power
  `P·G·PL⁻¹` to the noise-plus-interference term.

### 3.6 `link/`: link budget, association, interference
- `link_budget.py`: per link coupling loss = PL + O2I + SF − antenna gains
  (the wideband beam gain of the TXRU virtualisation toward the UE). Noise
  N = −174 + 10log10(BW) + NF. Tx PSD = P_tot / N_RB, spread evenly over RBs.
- `association.py`: serving cell = max RSRP, i.e. min coupling loss (fixed for
  the drop; optional handover margin).
- `interference.py`: per UE, sorts the cells by received power and keeps the
  K strongest for explicit MIMO modelling. Each slot it builds the
  interference covariance per RB:
  `R_I[rb] = Σ_k P_k H_k W_k W_kᴴ H_kᴴ + (σ²_residual + N₀)·I`, where `W_k` is
  the precoder that cell k actually scheduled in that RB/slot. Idle RBs of
  a cell contribute nothing (this is how the load model enters).

### 3.7 `phy/`: SINR, codebook, CSI, abstraction
- `sinr.py`: MMSE-IRC post-equaliser SINR per RB per layer. This is
  `batch_mmse_sinr` generalised from `noise_var·I` to `R_I`. Implemented by whitening, `H̃ = R_I^{-1/2} H_s W_s`, then calling
  the existing `nrdlsim.receiver.batch_mmse_sinr(H̃, 1.0)`. MMSE (non-IRC) is
  available as a baseline.
- `codebook/`: two codebooks built from the same 2-D DFT beam grid
  (`common.py`). This grid covers the port layout (N1, N2), the oversampling
  (O1, O2) and the dual-pol port ordering of the TXRU array in §3.3. Both
  codebooks replace the LLS SVD proxy, and both are selected with the same
  interface, `select_pmi(H_est, R_I, rank) -> (W[rb, n_port, rank], report)`.
  SVD stays as the "ideal / reciprocity" reference (TDD SRS).
  - `type1.py`: **Type-I single-panel** (§5.2.2.2.1, Tables 5.2.2.2.1-5…12).
    Ranks 1–8, codebook modes 1/2. The PMI is i1 = (i1,1, i1,2, i1,3) for the
    wideband beam (group) and the layer-2 beam offset. i2 is the co-phasing,
    wideband or per sub-band. The search is exhaustive over i1 and i2, and
    the metric is the post-IRC mutual information (capacity) summed over the
    band.
  - `etype2.py`: **Rel-16 enhanced Type-II** (§5.2.2.2.5), ranks 1–4.
    Each layer's precoder is `W = W1 · W̃2 · W_fᴴ`:
    - `W1`: L orthogonal spatial-domain (SD) beams per polarisation, from one
      rotated orthogonal group (q1, q2). L ∈ {2, 4, 6}.
    - `W_f`: Mv frequency-domain DFT basis vectors out of N3 PMI sub-bands.
      Mv = ⌈p_v · N3 / R⌉ with R ∈ {1, 2} sub-bands per CQI sub-band, and the
      window is fixed by M_initial when N3 > 19.
    - `W̃2`: 2L × Mv combining coefficients. At most K0 = ⌈β · 2L · M1⌉
      non-zero coefficients per layer (2K0 in total over all layers), marked
      in a bitmap. Each has a 3-bit differential amplitude (8 levels) and a
      16-PSK phase (4 bits). There is one reference amplitude per
      polarisation (4 bits, 16 levels), and the strongest-coefficient
      indicator (SCI) sets the strongest coefficient to 1.
    - Parameter combinations 1–8 of Table 5.2.2.2.5-1 give (L, p_v, β),
      with the rank-3/4 restrictions.
    - UE-side derivation:
      1. Take the dominant eigenvectors of the whitened channel per PMI
         sub-band.
      2. Pick the SD beams with the highest projected power.
      3. Project onto the FD DFT basis and keep the strongest Mv.
      4. Keep the K0 largest coefficients and quantise them.
      5. Normalise the result as in §5.2.2.2.5.
    - The quantisation loss is visible: `etype2` against unquantised SVD, at
      each parameter combination, is a built-in comparison.
  - `payload.py`: the CSI part-1/part-2 UCI size per report (§6.3.2.1.2 of
    TS 38.212 for field sizes). This gives SE against feedback overhead for
    Type-I and each eType-II combination.
- `csi.py`: CSI measured on the **delayed** channel (`CSIFeedbackChannel`
  reused). The interference is measured on CSI-IM, i.e. the interference seen
  in the measurement slot, which differs from the data slot and causes the
  flash-light effect. Output: RI, PMI (Type-I wideband/sub-band, or
  eType-II), wideband + sub-band CQI. The CQI is computed with the
  *quantised* precoder the gNB will use, so a coarse codebook shows up in the
  CQI and the MCS, not just in the precoder. The rank/CQI selection reuses
  `cqi_required_sinr_db`. The codebook type and its parameters are set per
  UE in the scenario config (`csi.codebook = 'type1' | 'etype2' | 'svd'`).
- `l2s.py`: thin adapter to `nrdlsim.link_abstraction`. It takes the per-RB
  SINRs of the allocated RBs and computes the MIESM effective SINR at the
  MCS modulation order, then BLER → ACK/NACK. HARQ chase combining adds the
  SINRs, as in the LLS. It is calibrated through the LLS (see §5).

### 3.8 `mac/`: scheduling, link adaptation, HARQ
- `scheduler.py`: per cell per slot:
  1. HARQ retransmissions first (same RBs/MCS/rank);
  2. **Proportional fair** in time and frequency on RBG granularity
     (TS 38.214 RBG size from BWP). Metric: `r_u(rbg) / R̄_u`, with `r_u`
     from the sub-band CQI and `R̄_u` an EWMA with window t_c. Round-robin
     and max-C/I are options;
  3. SU-MIMO with the reported RI/PMI. MU-MIMO (co-scheduled PMI pairing
     with power split) comes in a later phase.
- `link_adaptation.py`: one `nrdlsim.scheduler.Scheduler` instance per UE,
  kept for the OLLA state and the CQI→MCS mapping. Resource allocation comes
  from `scheduler.py`, not from this instance.
- `harq.py`: N HARQ processes per UE (e.g. 16), feedback delay K1, max 4
  transmissions, residual-BLER accounting. This extends the single-process
  loop in the LLS.

### 3.9 `traffic/models.py`
- **Full buffer**: all cells fully loaded (worst-case interference; used for
  the ITU SE KPIs).
- **FTP model 1 / 3**: Poisson packet arrivals (0.5 MB packets, λ tuned to a
  target resource utilisation). Needed for user-perceived throughput and
  realistic interference with lightly loaded cells.

### 3.10 `engine/`: simulation loop
```
for drop in drops:                       # independent geometry; parallel across processes
    layout, UEs     <- topology
    LSPs, LOS, PL   <- propagation (spatially consistent)
    association, K-strongest sets <- link
    ray parameters  <- fast_fading (fixed per drop; H evolves with t)
    for slot in range(warmup + T):
        traffic arrivals
        per UE: H(t) for serving + K interferers
        CSI (delayed, CSI-IM interference)  -> reports
        per cell: HARQ + PF scheduling -> allocations, W, MCS
        per UE: R_I from other cells' actual allocations -> SINR -> L2S -> ACK/NACK
        OLLA / HARQ / PF-average updates; KPI accumulation (after warm-up)
```
Two passes per slot. First, every cell schedules. Second, SINRs are
evaluated. This way the interference is computed from the precoders that
are actually transmitted in the same slot.

### 3.11 `metrics/`
- **Calibration stage** (no scheduling): coupling-loss CDF, geometry
  (wideband SINR) CDF, DS / ASD / ZSD CDFs, largest-singular-value CDFs.
  These are compared against the TR 38.901 §7.8 / TR 38.802 industry
  calibration curves.
- **Performance stage**: UE throughput CDF, **cell average SE**
  (b/s/Hz/cell), **5 %-ile UE SE**, RI/MCS/BLER distributions, resource
  utilisation, user-perceived throughput (FTP). Checked against the ITU-R
  M.2412 / M.2410 targets (e.g. Dense Urban eMBB DL: 7.8 average /
  0.225 b/s/Hz 5 %-ile).

---

## 4. Complexity budget

57 cells × 10 UE × (1 + K=8) links × N_RB × n_rx × n_port per slot is the
dominant cost. The plan to keep it tractable:
- per-RB channel only, as in the LLS; optionally per-RBG for CSI;
- rays → cluster-level precompute: angles and element fields are fixed per
  drop, so only the Doppler phase changes per slot. `H(t)` is one einsum
  over clusters × rays;
- evaluate the fast fading only for UEs in the **central 19 sites' cells
  receiving KPIs**, or for all cells with wrap-around (default: all cells,
  wrap-around);
- batched numpy/BLAS; drops parallelised with `ProcessPoolExecutor`, as in
  `NRDownlinkSimulator.run(n_jobs)`.

---

## 5. Link-level ↔ system-level calibration

1. The **LLS** provides the AWGN BLER curves per MCS (the MIESM waterfall in
   `link_abstraction`; checked against the bit-true LDPC path and the 5G-IA
   / 38.104 references in `docs/calibration.md`).
2. The SLS uses exactly the same `effective_sinr_miesm` +
   `bler_from_effective_sinr`, so the SLS BLER is consistent with the LLS by
   construction.
3. Cross-check: fix one SLS UE and replace the interference with AWGN at the
   same SINR, using a CDL-like channel. The SLS SE must match the LLS
   `run_point` at that SNR (regression test).

---

## 6. Phased delivery

| Phase | Content | Exit criterion |
|---|---|---|
| **P1 – Geometry calibration** | scenario config, hex layout + wrap-around, UE drop, pathloss/LOS/O2I/SF, antenna (TXRU virtualisation), association, coupling loss & geometry SINR | coupling-loss / geometry CDFs within ~1 dB of the TR 38.901 §7.8 calibration (UMa, UMi, InH). **Status:** implemented and verified against the spec formulas; the comparison with the industry curves waits for the reference data (not reachable from this environment) |
| **P2 – Fast fading** | LSPs with spatial consistency, §7.5 cluster/ray generator (shared kernel with LLS CDL), H per RB per slot | DS/ASD/ZSD/singular-value CDFs vs §7.8 calibration |
| **P3 – Full-buffer SU-MIMO** | MMSE-IRC SINR, SVD precoding first, then Type-I and Rel-16 eType-II codebooks (with CSI payload size), CSI with delay, PF scheduler, per-UE OLLA, multi-process HARQ, L2S | cell avg / 5 %-ile SE in line with 38.802 / M.2412 industry results; LLS↔SLS regression passes |
| **P4 – Traffic & load** | FTP model 1/3, RU-dependent interference, UPT metrics | UPT vs RU curves |
| **P5 – Extensions** | MU-MIMO (eType-II is the main enabler), Type-I multi-panel, Rel-17 FeType-II port selection, TDD pattern + SRS reciprocity, FR2 (beam management, phase noise), UL | per-feature |

---

## 7. Testing
- Unit tests: pathloss formulas against spot values; LOS probabilities;
  LSP statistics (mean/std/cross-correlation) recovered from many draws;
  spatial-correlation decay; wrap-around distances; Type-I codebook
  size and unit-norm/orthogonal columns against the 38.214 tables; eType-II:
  FD basis and SD beam orthogonality, K0/bitmap limits per parameter
  combination, amplitude/phase quantisation round-trip, the reconstructed
  precoder converging to the SVD precoder as (L, p_v, β) grow, and a payload
  size matching hand-computed spec values; IRC SINR equals MMSE SINR when R_I = N₀I; PF
  fairness on a static toy case.
- Regression: the LLS↔SLS single-link equivalence (§5); determinism under a
  fixed seed; serial vs parallel drops give identical results.

---

## 8. Open decisions (defaults proposed)
1. **First scenario**: UMa 3.5 GHz, 100 MHz @ 30 kHz, 32T4R (proposed), or
   Dense-Urban M.2412 (4 GHz, 200 MHz)?
2. **CSI** (decided): both Type-I single-panel and Rel-16 eType-II are
   built in P3 (FDD-style CSI), with SVD kept as the ideal/reciprocity
   reference.
3. **Dependency on `nrdlsim`**: pinned pip/git dependency (proposed) or a
   git submodule? This includes a small upstream refactor in `nrdlsim`: the
   shared ray-summation kernel and an optional `R_I` argument in the SINR.
4. **Interference fidelity**: K = 8 explicit MIMO interferers + wideband rest
   (proposed), or all links explicit (slower, exact)?
