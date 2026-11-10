# The users' hand grip in the CW2L evaluation (FTP model 1, 20 MHz)

This study adds the users' hand grip to the FTP model 1 evaluation of [cw2lm-ftp-20mhz.md](cw2lm-ftp-20mhz.md) and reruns it. The grip is the UT self-blocking of TR 38.901 §7.6.4.1: blockage model A, without the non-self blockers.

Everything else is the warm + fast set:
- **Deployment:** Dense Urban-eMBB A, 4 GHz, 20 MHz at 30 kHz (52 PRB), 44 dBm, 32T4R.
- **Transmission:** rank ≤ 4, 0.5 Mbyte files.
- **Link adaptation and HARQ:** OLLA with warm + fast start, the HARQ fix, synchronous HARQ.
- **Drops:** 10.

The tables are in [results/cw2lm_ftp1_grip_20mhz.md](../results/cw2lm_ftp1_grip_20mhz.md).

## Summary

- **The grip takes a quarter of the serving link's power, but in this layout it barely changes performance.**
  - **Blocking:** it blocks 25 % of the serving link's clusters, which carry 26 % of its multipath power on average.
  - **Re-attachment:** 19 % of the UTs re-attach to another cell. Their strongest cell is then 1.1 dB weaker at the median and 2.4 dB on average.
  - **Interference:** it blocks interferers as well as the server, so the full-load geometry rises by 0.1–0.2 dB in mean and median. The 200 m layout is interference-limited.
- **NR:**
  - **Rates:** for the same RU the network takes 2–4 % more arrivals with the grip.
  - **Same rates:** at the no-grip rates, NR's mean UPT changes by +0.1 to +2.0 %, and its mean rank by at most 0.03.
- **The CW2L comparison does not change:**
  - **MMSE-IRC:** LTE style, twisted LTE and one codeword per layer stay within −0.7 to +1.6 % of NR in mean UPT, against −1.4 to +2.3 % without the grip.
  - **SIC:** LTE style and one codeword per layer gain +9.3 to +13.0 %, against +8.3 to +12.4 % without. All 120 single-drop gains with SIC are positive, with and without the grip.
  - **Shifts:** each mean gain moves by −0.7 to +2.1 points, and each 5th-percentile gain by −3.0 to +3.8.

## How the grip is modelled

### What TR 38.901 specifies

Blockage model A (TR 38.901 §7.6.4.1) describes blocking by two kinds of region of arrival directions at the UT:
- **Self-blocking region:** the user's own hand, head and body.
- **Non-self blockers:** K = 4 regions for other people and vehicles.

A cluster that arrives inside the self-blocking region is attenuated by 30 dB. Only the self-blocking part is modelled here.

### The grip of each UT

At the start of a drop each UT draws two things, which stay fixed for the run:
- **Mode:** landscape (two hands) with probability `self_blocking_landscape_ratio` = 0.5, otherwise portrait (one hand).
- **Orientation:** an azimuth bearing Ω_UT,α, uniform over [0°, 360°). The phone stays upright (Ω_UT,β = Ω_UT,γ = 0). Its local coordinate system (LCS) is therefore the GCS turned by α about the vertical: φ′ = φ − α, θ′ = θ.

### The blocked region (TR 38.901 Table 7.6.4.1-1)

| Mode | φ′sb, centre azimuth | x′sb, azimuth width | θ′sb, centre zenith | y′sb, zenith width | Region in the UT's LCS |
|---|---|---|---|---|---|
| Portrait | 260° | 120° | 100° | 80° | AOA′ 200°–320°, ZOA′ 60°–140° |
| Landscape | 40° | 160° | 110° | 75° | AOA′ −40°–120°, ZOA′ 72.5°–147.5° |

A GCS arrival direction (φ, θ) is in the region when

    |wrap(φ − α − φ′sb)| ≤ x′sb / 2   and   |θ − θ′sb| ≤ y′sb / 2,      wrap(·) to [−180°, 180°)

Zenith is measured from the vertical, so 90° is the horizon.
- **Portrait:** the region covers a third of the azimuths around the user, from 30° above the horizon to 50° below it.
- **Landscape:** it covers 4/9 of the azimuths, from 17.5° above the horizon to 57.5° below it.

The region turns with the phone, so each UT has its own blocked sector in the GCS.

### Which paths lose power

- **Clusters:** each cluster is tested on its centre arrival direction, that is its AOA and ZOA before the ray offsets. A cluster inside the region loses 30 dB: its power is multiplied by A = 10⁻³ on all 20 rays and all four UT ports alike.
  - **Per cluster, as in TR 38.901:** a cluster centred inside the region is attenuated even where some of its rays point outside it. A cluster centred outside is not attenuated even where some of its rays point inside.
- **LOS ray:** on LOS links the LOS ray belongs to the first cluster (eq. 7.5-30), and that cluster's centre points the same way. The ray is tested on its own direction and loses 30 dB when it arrives inside the region.
- **A loss, not a reshuffle:** the remaining clusters are not rescaled, so the link simply loses the blocked power.

With A_n = 10⁻³ for a blocked cluster and 1 otherwise, and A_LOS for the LOS ray:
- **Channel** (eq. 7.5-22 / 7.5-30): H = √(1/(K_R+1)) Σ_n √(A_n P_n / M) Σ_m (ray terms) + √(K_R/(K_R+1)) √A_LOS H_LOS.
- **Port-0 RSRP** (TR 36.873 eq. 8.1-1): RSRP ∝ 1/(K_R+1) Σ_n A_n P_n / M Σ_m g_nm + K_R/(K_R+1) A_LOS g_LOS.

Here K_R is the Ricean K-factor, P_n the cluster power and M = 20 rays.

### Where the loss acts

- **Attachment:** the RSRP of every cell toward every UT includes the loss. Each UT attaches to its strongest cell as the grip leaves it, as a real UT measuring RSRP in the hand would.
- **Interference:** each UT has its serving cell plus 8 interferers with explicit channels, and the 8 are the strongest after the grip. Their channels carry the loss, as do the power-summed interference of the other cells and the geometry.
- **Fast fading:** the per-slot channels of serving and interfering links use the attenuated clusters.
- **Delay structure:** the two strongest clusters for the sub-cluster delay split (step 11) are picked by the unblocked powers, so the delays do not change.

### The orientation turns the array

The UT array has two dual-polarised elements, 0.5 λ apart horizontally, and it turns with the phone.
- **Array response:** the elements are isotropic and the turn is about the vertical, so the polarisation basis does not change. The array response is evaluated at the LCS azimuth φ − α.
- **Doppler:** it stays a GCS quantity, since the UT's velocity does not turn with the phone.
- **Without the grip:** the array keeps the GCS orientation, as in all earlier runs.

### What stays the same

- **Random streams:** the grip comes from a child random stream of the drop. The UT positions, LOS states, pathloss, shadowing, clusters and file arrivals are those of the run without the grip, so every comparison is paired by drop.
- **Off by default:** with `ue_self_blocking=False` every result is bit-identical to before. This was checked against the previous commit.

### Simplifications

- **Blockers:** there are no non-self blockers (other people, vehicles).
- **Orientation:** the phone is upright, with no tilt (Ω_UT,β, Ω_UT,γ).
- **Static grip:** grip and orientation are fixed over a run. Attachment is fixed per drop anyway.
- **In-car UTs:** they are held like the indoor ones.
- **Uniform loss:** the 30 dB applies at every frequency and on every UT port, and blocking is decided per cluster, as in TR 38.901.

## What the grip does to the drops

10 drops, 11,400 UTs, 50 % of them in landscape mode.

| Quantity | Value |
|---|---|
| Serving-link clusters blocked | 25 % |
| Serving-link multipath power lost, mean share | 26 % |
| Loss toward the former serving cell [dB]: mean / median / p90 / max | 3.8 / 1.3 / 10.8 / 30.0 |
| UTs that change serving cell | 19 % |
| Loss of the strongest cell after re-attachment [dB]: mean / median / p90 / max | 2.4 / 1.1 / 6.5 / 30.0 |
| LOS ray blocked, on all LOS links | 35 % |
| LOS ray blocked, on the LOS links that served before the grip | 31 %, of which 79 % of the UTs re-attach |
| LOS ray blocked, on the LOS serving links after the grip | 11 % |
| Median arrival zenith of the LOS ray on LOS serving links | 77° (13° above the horizon) |
| Geometry (full-load SINR) [dB], mean / p5 / p50 / p95: no grip → grip | 3.9 / −3.5 / 2.6 / 15.9 → 4.1 / −3.5 / 2.7 / 16.1 |

The serving link after the grip, by its condition and by the grip mode:

| Serving link | Share of UTs | Clusters blocked | Multipath power lost, mean / median |
|---|---|---|---|
| Indoor (O2I) | 80 % | 27 % | 29 / 24 % |
| In car, LOS | 16 % | 17 % | 12 / 2 % |
| In car, NLOS | 4 % | 18 % | 18 / 15 % |
| Portrait grip | 50 % | — | 23 / 15 % |
| Landscape grip | 50 % | — | 28 / 21 % |

- **Indoor UTs:** their clusters arrive around the horizon, with a median zenith spread of about 10°, so most fall inside both zenith bands and the azimuth decides. The grip then covers a third of the directions in portrait and 4/9 in landscape. With azimuth spreads of about 60°, it usually takes some clusters but rarely all.
- **LOS (in-car) UTs:** the LOS ray arrives 13° above the horizon at the median, inside the zenith band of both modes.
  - **On all LOS links:** the grip blocks the LOS ray on 35 % of them, about what the region sizes predict.
  - **After re-attachment:** 79 % of the UTs whose serving LOS ray is blocked move to another cell, so only 11 % of LOS serving links have it blocked.
  - **Power lost:** most LOS UTs keep their LOS ray and lose little, 2 % at the median. A few lose most of it.
- **Interference:** the grip blocks interferers as well as the server. Each UT also re-attaches to its best unblocked cell, so the hand works a little like a crude directional antenna, and the full-load geometry rises slightly.

## Evaluation

### Set-up

- **Runs:** 360 runs, 10 drops each.
  - **MMSE-IRC:** NR, LTE style (Alt 2), twisted LTE and one codeword per layer (Alt 3).
  - **Codeword-level SIC:** LTE style and one codeword per layer.
  - **Precoders:** sub-band SVD (reciprocity) and wideband SVD.
  - **Loads:** 20 / 50 / 70 % NR resource utilisation (RU).
- **Run length:** 1000 slots at 20 and 50 % load and 2000 slots at 70 %. Files arriving in the last 300 / 1000 slots are served but not counted.
- **Rates:** recalibrated with the grip in the same way as for the no-grip set: 24 NR runs, 6 rates, 2 drops, 2300 slots with 300 slots of warm-up.
- **Controls:** 80 NR runs at the no-grip rates, at 20 and 50 % load with both precoders. One set turns the array by the grip's orientation but blocks nothing (0 dB); the other is the full grip.

### Arrival rates for the same RU

| Precoder | 20 % RU | 50 % RU | 70 % RU |
|---|---|---|---|
| Sub-band SVD [UTs/s per cell], no grip → grip | 7.27 → 7.46 (+2.7 %) | 14.20 → 14.46 (+1.8 %) | 18.42 → 18.96 (+3.0 %) |
| Wideband SVD | 7.05 → 7.22 (+2.4 %) | 13.77 → 14.02 (+1.8 %) | 17.80 → 18.59 (+4.4 %) |

With the grip, the same arrivals need slightly less RU at every calibration point, so the system serves a little more traffic per resource.

### NR

At the same arrival rates (control runs), NR's UPT changes as follows. Each cell gives mean / p5 / p95 in %.

| Precoder | Load | Orientation vs no grip | Blocking (grip vs orientation) | Grip vs no grip |
|---|---|---|---|---|
| Sub-band SVD | 20 % | +1.5 / +0.7 / −0.2 | −0.8 / −0.6 / +0.1 | +0.7 / +0.1 / −0.1 |
| Sub-band SVD | 50 % | −0.4 / −1.6 / −1.2 | +2.1 / −0.1 / +3.7 | +1.6 / −1.7 / +2.5 |
| Wideband SVD | 20 % | −0.5 / −4.5 / −2.0 | +0.6 / +7.7 / −0.4 | +0.1 / +2.9 / −2.4 |
| Wideband SVD | 50 % | −0.4 / −1.0 / −0.8 | +2.4 / +4.7 / +2.5 | +2.0 / +3.6 / +1.7 |

- **The turned array does not hide a blocking loss.** The orientation alone moves NR's mean UPT by −0.5 to +1.5 %. The blocking moves it by −0.8 to +2.4 %, and the gain grows with load, where interference matters more.
- **Rank:** NR's mean rank changes by at most 0.03.
- **RU-matched sets:** between the evaluation sets, at their own RU-matched rates, NR's mean UPT moves by −5.4 to +4.7 % and its 5th percentile by −9.1 to +2.3 %. These differences carry the rate change and a different traffic realisation, and the same-rate controls show they are mostly noise.

### Gains against NR

Mean UPT gain over NR [%], no grip → grip, at 20 / 50 / 70 % load:

| Scheme | Sub-band SVD | Wideband SVD |
|---|---|---|
| LTE style, MMSE-IRC | +2.3 / +0.7 / +0.4 → +1.6 / +1.3 / +0.9 | −0.1 / +0.3 / −0.3 → +0.5 / +0.2 / +0.3 |
| Twisted LTE, MMSE-IRC | +2.1 / +0.7 / −0.2 → +1.3 / +1.2 / +1.0 | −0.6 / +0.2 / +0.1 → +0.5 / +0.4 / +0.9 |
| One codeword per layer, MMSE-IRC | +1.5 / +0.0 / −1.4 → +1.3 / +0.9 / −0.1 | −1.0 / −0.0 / −1.1 → +0.6 / −0.7 / −0.2 |
| LTE style, SIC | +10.3 / +9.6 / +10.0 → +9.9 / +9.8 / +10.2 | +8.3 / +9.3 / +8.3 → +9.7 / +9.3 / +10.4 |
| One codeword per layer, SIC | +12.4 / +11.3 / +12.1 → +12.9 / +12.5 / +12.3 | +11.8 / +11.0 / +10.2 → +13.0 / +10.8 / +11.7 |

- **5th percentile:** with MMSE-IRC the multi-codeword gains are −2.9 to +3.6 % with the grip (−5.5 to +2.4 % without). With SIC they are +5.4 to +12.2 % (+4.2 to +11.7 % without).
- **Single drops:**
  - **SIC:** all 120 single-drop mean gains are positive in both sets: +4.5 to +18.9 % with the grip, +3.2 to +15.7 % without.
  - **MMSE-IRC:** 123 of 180 are positive with the grip and 99 of 180 without. They range from −3.4 to +4.2 % with the grip and −4.5 to +4.5 % without.
- **First-transmission BLER:**
  - **NR, LTE style, twisted LTE and both SIC schemes:** 10–12 % per codeword with the grip.
  - **One codeword per layer with MMSE-IRC:** up to 14 % on its third and fourth codewords.
  - Both are as without the grip.

### Why the grip changes so little here

- **Interference-limited layout:** at 200 m ISD and 44 dBm the grip removes interference about as much as signal, and re-attachment picks the best remaining cell. The power loss would only matter where noise does, at the cell edge at low load, and there the 5th percentile moves by a few points either way.
- **Wide angular spreads:** indoor arrivals spread over about 60° in azimuth, so blocking a third of the directions leaves enough clusters for the same rank.
- **The gains are relative:** every scheme sees the same blocked channels, and the grip does not touch what separates them. With MMSE-IRC that is the CQI error on the weaker codewords; with SIC it is the receiver gain.

### Limits

- **95th percentile at 20 % RU:** it sits at the peak rate (about 250 Mbit/s) and swings with the share of files that reach it, so its gains there are not meaningful.
- **No warm-up:** as in all FTP model 1 runs, files arriving while the system fills up are counted.
  - **Absolute UPTs:** at 70 % load they are about 5 % optimistic.
  - **Gains:** dropping the first 100 ms of arrivals moves a mean gain by at most 1.2 points with the grip, and 0.9 without.
- **Other deployments:** the result is for an interference-limited deployment. A noise-limited one, with larger distances, lower power or a higher carrier, would feel the grip's power loss.
- **Template:** the 20 MHz template copy still holds the no-grip set.

## Code and reproduction

- **Model:** `nrsls/propagation/blockage.py` holds the regions, the grip draw and the per-cluster loss. `nrsls/config/scenario.py` adds `ue_self_blocking`, `self_blocking_landscape_ratio` and `self_blocking_db`.
  - **Drop:** `nrsls/engine/drop.py` draws the grip from a child stream and applies it before the RSRP.
  - **RSRP:** `nrsls/link/rsrp.py` applies the loss.
  - **Channel:** `nrsls/propagation/fast_fading.py` applies the loss in `channel_batch` and `link_channel`, and turns the UT array.
- **Tests:** `tests/test_self_blocking.py` covers the regions, the grip draw, the cluster loss, the channel and RSRP scaling, the turned array, and an unchanged drop with the same files.
- **Set-ups:** `examples/cw2lm_ftp_eval.py`:
  - `20mhz-ftp1-grip` is the evaluation.
  - `20mhz-ftp1-orient` (orientation only, 0 dB) and `20mhz-ftp1-grip-norecal` (grip at the no-grip rates) are the controls.
- **Logs and summaries:**
  - **Grip set:** logs in `results/ftp1_grip_cal/` and `results/ftp1_grip/`; rates in `results/cw2lm_ftp1_grip_rates_20mhz.json`; summary in `results/cw2lm_ftp1_grip_20mhz.json`.
  - **Controls:** log in `results/ftp1_grip_ctrl/`; summaries in `results/cw2lm_ftp1_orient_20mhz.json` and `results/cw2lm_ftp1_grip_norecal_20mhz.json`.
  - **Drop statistics:** `results/cw2lm_ftp1_grip_drops.json`.

```bash
python examples/cw2lm_ftp_eval.py --setup 20mhz-ftp1-grip --calibrate --cases svd_sb_20ms,svd_20ms --cal-drops 2 --cal-slots 2300 --warmup 300 --jobs 4 --log results/ftp1_grip_cal/cal.jsonl
```

```bash
python examples/cw2lm_ftp_eval.py --setup 20mhz-ftp1-grip --cases svd_sb_20ms --loads 20,50 --variants irc-fix-warmfast --schemes nr,lte,per_layer,lte_twisted --drops 10 --slots 1000 --warmup 0 --drain 0 --jobs 4 --log results/ftp1_grip/svd_sb-2050.jsonl
```

The other shares differ in `--cases`, `--loads`, `--variants` (`sic-fix-warmfast` with `--schemes lte,per_layer`), `--first-drop` / `--drops` and `--slots 2000` at 70 %; the worker logs in `results/ftp1_grip/` are named after them.

```bash
python examples/cw2lm_ftp_eval.py --setup 20mhz-ftp1-grip --summary-only --log "$(ls results/ftp1_grip/*.jsonl | paste -sd,)" --summary-drain 1000:300,2000:1000
```

```bash
python examples/cw2lm_ftp1_grip_compare.py
```
