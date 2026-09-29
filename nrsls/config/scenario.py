"""Scenario configuration for the NR downlink system-level simulator.

The deployment scenarios follow TR 38.901 clause 7.2:

  * UMa and UMi-Street Canyon (Table 7.2-1): 19 hexagonal sites with 3
    sectors each, ISD 500 m / 200 m, BS height 25 m / 10 m, 80 % indoor UTs
    on floors n_fl ~ U{1..N_fl}, N_fl ~ U{4..8}, h_UT = 3(n_fl - 1) + 1.5 m.
  * RMa (Table 7.2-3): ISD 1732 m, BS height 35 m, 50 % indoor and 50 %
    in-car UTs at 1.5 m.
  * InH-Office (Table 7.2-2): 120 m x 50 m hall, 12 ceiling TRPs 20 m apart
    at 3 m, UTs at 1 m.

Antenna panels follow TR 38.901 clause 7.3; the TXRU (antenna port)
virtualisation follows TR 36.897 clause 5.2.2.  The carrier is the
``nrdlsim`` :class:`~nrdlsim.config.CarrierConfig`, so the system-level and
link-level simulators share one numerology definition.
"""

from __future__ import annotations

from dataclasses import dataclass, field, replace
from typing import Optional

from nrdlsim.config import CarrierConfig

# TR 38.901 Table 7.4.1-1 note 1: c = 3.0e8 m/s in the breakpoint distances
SPEED_OF_LIGHT = 3.0e8

SCENARIOS = ("UMa", "UMi", "RMa", "InH-open", "InH-mixed")


@dataclass
class BSAntennaConfig:
    """gNB antenna panel (TR 38.901 clause 7.3) and TXRU virtualisation.

    The panel has M x N element positions with P polarisations (only a
    single panel, Mg = Ng = 1, for now).  Each TXRU (antenna port) drives a
    vertical sub-array of K = M / Mp co-polarised elements with the
    TR 36.897 clause 5.2.2 weights

        w_k = exp(-j 2 pi (k - 1) dV cos(theta_etilt)) / sqrt(K),

    which steer the sub-array beam to the zenith angle ``electrical_tilt_deg``
    (90 = horizon, 102 = 12 degrees below it).  There are Mp * Np * P ports.
    """

    M: int = 10                       # element rows
    N: int = 1                        # element columns
    P: int = 1                        # polarisations (1 or 2)
    Mp: int = 1                       # TXRU rows (M must be a multiple)
    Np: int = 1                       # TXRU columns (N must be a multiple)
    dV: float = 0.8                   # vertical element spacing (wavelengths)
    dH: float = 0.5                   # horizontal element spacing (wavelengths)
    pattern: str = "38.901"           # '38.901' (Table 7.3-1) or 'omni'
    max_gain_dbi: float = 8.0         # G_E,max
    hpbw_deg: float = 65.0            # theta_3dB = phi_3dB
    front_back_db: float = 30.0       # SLA_V = A_max
    electrical_tilt_deg: float = 102.0  # theta_etilt, zenith angle in the LCS
    mechanical_downtilt_deg: float = 0.0  # positive = below the horizon

    def __post_init__(self):
        if self.M % self.Mp or self.N % self.Np:
            raise ValueError("M and N must be multiples of Mp and Np")
        if self.P not in (1, 2):
            raise ValueError("P must be 1 or 2")
        if self.pattern not in ("38.901", "omni"):
            raise ValueError(f"unknown element pattern {self.pattern!r}")

    @property
    def n_ports(self) -> int:
        return self.Mp * self.Np * self.P

    @property
    def elements_per_txru(self) -> int:
        return self.M // self.Mp


@dataclass
class UEAntenna:
    """UT antenna: (M, N, P) isotropic elements (TR 38.901 Table 7.8-1)."""

    M: int = 1
    N: int = 1
    P: int = 1
    dV: float = 0.5
    dH: float = 0.5
    gain_dbi: float = 0.0

    @property
    def n_ports(self) -> int:
        return self.M * self.N * self.P


@dataclass
class ScenarioConfig:
    """One system-level deployment: layout, carrier, users, propagation."""

    name: str = "UMa"
    scenario: str = "UMa"             # propagation family, one of SCENARIOS

    # --- layout (hexagonal grid; the InH hall is fixed by TR 38.901) ---
    isd_m: float = 500.0              # inter-site distance
    n_rings: int = 2                  # 2 rings -> 19 sites
    sector_bearings_deg: tuple = (30.0, 150.0, 270.0)
    h_bs_m: float = 25.0
    wrap_around: bool = True
    min_d2d_m: float = 35.0           # minimum BS-UT 2-D distance
    inh_hall_m: tuple = (120.0, 50.0)  # InH: hall length x width
    inh_trp_grid: tuple = (6, 2)      # InH: TRPs along the length x width

    # --- carrier ---
    carrier_freq_hz: float = 3.5e9
    carrier: CarrierConfig = field(
        default_factory=lambda: CarrierConfig(mu=1, n_size_grid=273))
    noise_bandwidth_hz: Optional[float] = None  # None: occupied bandwidth
    # channel bandwidth that spectral efficiencies are normalised by (ITU-R
    # M.2410: throughput / channel bandwidth); None: the occupied bandwidth
    channel_bandwidth_hz: Optional[float] = None
    bs_tx_power_dbm: float = 53.0     # total over the carrier
    ue_noise_figure_db: float = 9.0

    # --- users ---
    ue_per_cell: int = 10
    indoor_ratio: float = 0.8         # O2I UTs (outdoor-BS scenarios)
    n_floors: tuple = (4, 8)          # building floors N_fl ~ U{4..8}
    h_ut_outdoor_m: float = 1.5
    in_car_ratio: float = 0.0         # fraction of outdoor UTs inside cars
    car_loss_db: tuple = (9.0, 5.0)   # TR 38.901 7.4.3.2: N(mu, sigma)
    ue_speed_kmh: float = 3.0
    in_car_speed_kmh: Optional[float] = None   # in-car UTs; None: ue_speed_kmh

    # --- O2I building penetration (TR 38.901 7.4.3.1) ---
    # 'low' | 'high' | 'mixed' (high-loss share = o2i_high_loss_ratio) |
    # 'legacy' (Table 7.4.3-3: 20 dB wall, UMa/UMi below 6 GHz)
    o2i_model: str = "mixed"
    o2i_high_loss_ratio: float = 0.2
    d2d_in_max_m: float = 25.0        # indoor distance: min of two U(0, max)

    # --- RMa environment (Table 7.4.1-1) ---
    building_height_m: float = 5.0
    street_width_m: float = 20.0
    # ITU-R M.2412 LMLC: RMa NLOS pathloss reduced by 12 dB (bounded by LOS)
    rma_nlos_offset_db: float = 0.0
    # ITU-R M.2412 channel model A where it departs from TR 38.901 (InH at
    # 0.5-6 GHz: pathloss, SF, LSP means and Laplacian azimuths)
    itu_model_a: bool = False

    # --- large-scale parameters / coupling ---
    shadow_fading: bool = True
    sf_spatial_correlation: bool = True        # spatially correlated LSPs
    # 'multipath': port-0 RSRP summed over the TR 38.901 rays (TR 36.873
    # eq. 8.1-1, as in the RP-180524 calibration); 'los': BS gain toward the
    # LOS direction only (phase-1 model)
    coupling_model: str = "multipath"

    # --- antennas ---
    bs_antenna: BSAntennaConfig = field(default_factory=BSAntennaConfig)
    ue_antenna: UEAntenna = field(default_factory=UEAntenna)

    def __post_init__(self):
        if self.scenario not in SCENARIOS:
            raise ValueError(f"unknown scenario {self.scenario!r}; "
                             f"expected one of {SCENARIOS}")
        if self.o2i_model not in ("low", "high", "mixed", "legacy"):
            raise ValueError(f"unknown O2I model {self.o2i_model!r}")
        if self.coupling_model not in ("multipath", "los"):
            raise ValueError(f"unknown coupling model {self.coupling_model!r}")
        if self.o2i_model == "legacy" and self.family not in ("uma", "umi"):
            raise ValueError("the legacy O2I model covers UMa and UMi only")

    @property
    def family(self) -> str:
        """'uma' | 'umi' | 'rma' | 'inh'."""
        return self.scenario.split("-")[0].lower()

    @property
    def propagation_family(self) -> str:
        """Key of the pathloss / LSP tables (``inh_a`` = M.2412 InH_A)."""
        if (self.itu_model_a and self.family == "inh"
                and self.carrier_freq_hz <= 6e9):
            return "inh_a"
        return self.family

    @property
    def is_indoor_scenario(self) -> bool:
        return self.family == "inh"

    @property
    def carrier_freq_ghz(self) -> float:
        return self.carrier_freq_hz / 1e9

    @property
    def bandwidth_hz(self) -> float:
        """Noise bandwidth: the occupied bandwidth unless overridden."""
        if self.noise_bandwidth_hz is not None:
            return self.noise_bandwidth_hz
        return self.carrier.occupied_bandwidth_hz


# ----------------------------------------------------------------------------
# Presets
# ----------------------------------------------------------------------------

def uma(**overrides) -> ScenarioConfig:
    """UMa, TR 38.901 Table 7.2-1: ISD 500 m, h_BS 25 m, 80 % indoor."""
    return replace(ScenarioConfig(name="UMa", scenario="UMa"), **overrides)


def umi(**overrides) -> ScenarioConfig:
    """UMi-Street Canyon, TR 38.901 Table 7.2-1: ISD 200 m, h_BS 10 m."""
    base = ScenarioConfig(name="UMi", scenario="UMi", isd_m=200.0,
                          h_bs_m=10.0, min_d2d_m=10.0)
    return replace(base, **overrides)


def rma(**overrides) -> ScenarioConfig:
    """RMa, TR 38.901 Table 7.2-3: ISD 1732 m, h_BS 35 m, 50 % indoor,
    50 % in car, UTs at 1.5 m, low-loss buildings (d2D-in up to 10 m)."""
    base = ScenarioConfig(
        name="RMa", scenario="RMa", isd_m=1732.0, h_bs_m=35.0,
        min_d2d_m=35.0, indoor_ratio=0.5, n_floors=(1, 1), in_car_ratio=1.0,
        o2i_model="low", d2d_in_max_m=10.0, carrier_freq_hz=0.7e9,
        carrier=CarrierConfig(mu=0, n_size_grid=52),
        bs_tx_power_dbm=46.0)
    return replace(base, **overrides)


def inh(variant: str = "open", **overrides) -> ScenarioConfig:
    """InH-Office (open or mixed), TR 38.901 Table 7.2-2: 12 TRPs at 3 m in
    a 120 m x 50 m hall, UTs at 1 m, no minimum distance."""
    base = ScenarioConfig(
        name=f"InH-{variant}", scenario=f"InH-{variant}", isd_m=20.0,
        h_bs_m=3.0, wrap_around=False, min_d2d_m=0.0,
        sector_bearings_deg=(0.0,), indoor_ratio=0.0, n_floors=(1, 1),
        h_ut_outdoor_m=1.0, bs_tx_power_dbm=24.0, o2i_model="low")
    return replace(base, **overrides)


def calibration_38901(scenario: str = "UMa", fc_ghz: float = 6.0,
                      **overrides) -> ScenarioConfig:
    """Large-scale calibration set-up in the style of TR 38.901 Table 7.8-1.

    Values recalled from the specification (verify against the spec text
    before quoting a calibration against it):

      * one TXRU of M = 10 vertical elements, dV = 0.8 lambda, element pattern
        of Table 7.3-1, electrical downtilt 102 deg (UMa, UMi) / 110 deg (InH);
      * 20 MHz at 6 GHz (100 MHz above 6 GHz), UT noise figure 9 dB;
      * BS power 44 dBm (UMa, UMi) at 6 GHz, 35 dBm above 6 GHz, 24 dBm (InH);
      * isotropic UT antenna, attachment on the strongest port-0 RSRP
        (0 dB handover margin), no fast fading;
      * O2I: equal mix of low- and high-loss buildings (assumption).
    """
    above6 = fc_ghz > 6.0
    carrier = (CarrierConfig(mu=3, n_size_grid=66) if above6
               else CarrierConfig(mu=0, n_size_grid=106))
    bw = 100e6 if above6 else 20e6
    tilt = 110.0 if scenario.startswith("InH") else 102.0
    ant = BSAntennaConfig(M=10, N=1, P=1, Mp=1, Np=1, dV=0.8,
                          electrical_tilt_deg=tilt)
    common = dict(carrier_freq_hz=fc_ghz * 1e9, carrier=carrier,
                  noise_bandwidth_hz=bw, bs_antenna=ant,
                  o2i_model="mixed", o2i_high_loss_ratio=0.5)
    if scenario == "UMa":
        cfg = uma(bs_tx_power_dbm=35.0 if above6 else 44.0, **common)
    elif scenario == "UMi":
        cfg = umi(bs_tx_power_dbm=35.0 if above6 else 44.0, **common)
    elif scenario.startswith("InH"):
        common["o2i_model"] = "low"
        cfg = inh(scenario.split("-")[1], bs_tx_power_dbm=24.0, **common)
    else:
        raise ValueError("Table 7.8-1 covers UMa, UMi and InH only")
    return replace(cfg, name=f"{cfg.name} calib {fc_ghz:g} GHz", **overrides)


def system_default(**overrides) -> ScenarioConfig:
    """Default system: UMa, 3.5 GHz, 100 MHz at 30 kHz (273 PRB), 32T4R.

    gNB: (M, N, P) = (8, 8, 2) elements at 0.5 lambda, TXRUs (Mp, Np) = (2, 8)
    -> 32 ports, each a 4-element vertical sub-array tilted to 102 deg.
    Power 53 dBm (46 dBm per 20 MHz). UT: (1, 2, 2) = 4 isotropic ports.
    O2I: 80 % low-loss / 20 % high-loss buildings.
    """
    ant = BSAntennaConfig(M=8, N=8, P=2, Mp=2, Np=8, dV=0.5, dH=0.5,
                          electrical_tilt_deg=102.0)
    base = uma(name="UMa 3.5 GHz 32T4R", bs_antenna=ant,
               ue_antenna=UEAntenna(M=1, N=2, P=2),
               o2i_model="mixed", o2i_high_loss_ratio=0.2)
    return replace(base, **overrides)


PRESETS = {
    "system": system_default,
    "uma": uma,
    "umi": umi,
    "rma": rma,
    "inh-open": lambda **kw: inh("open", **kw),
    "inh-mixed": lambda **kw: inh("mixed", **kw),
    "calib-uma": lambda **kw: calibration_38901("UMa", **kw),
    "calib-umi": lambda **kw: calibration_38901("UMi", **kw),
    "calib-inh": lambda **kw: calibration_38901("InH-open", **kw),
}


def get_preset(name: str, **overrides) -> ScenarioConfig:
    try:
        return PRESETS[name.lower()](**overrides)
    except KeyError:
        raise ValueError(f"unknown preset {name!r}; "
                         f"choose from {sorted(PRESETS)}") from None


# ----------------------------------------------------------------------------
# RP-180524: 3GPP calibration for the IMT-2020 self-evaluation (ITU-R M.2412
# test environments; results in TR 37.910 Annex A)
# ----------------------------------------------------------------------------

def rp180524(env: str, channel_model_a_o2i: str = "legacy",
             **overrides) -> ScenarioConfig:
    """Baseline calibration parameters of RP-180524 Tables 3-5.

    ``env``: 'rural-700m', 'rural-4g', 'rural-lmlc', 'mmtc-500m',
    'mmtc-1732m', 'urllc-4g', 'urllc-700m'.  Common to all: 10 MHz simulation
    bandwidth, 46 dBm per TRxP, UE NF 7 dB, isotropic 0 dBi UE at 1.5 m,
    3 sectors (30/150/270 deg), d2D_min = 10 m, wrap-around, attachment on
    port-0 RSRP with 0 dB handover margin.  Each port is a vertical sub-array
    of 8 elements at 0.8 lambda (element pattern of M.2412 Table 8-6,
    8 dBi), mechanically horizontal with the tabulated electrical tilt.

    The high/low-loss building mix in RP-180524 "applies to channel model B";
    ``channel_model_a_o2i`` selects the O2I model used here for channel
    model A (default: the TR 38.901 Table 7.4.3-3 legacy model for UMa,
    low-loss for RMa, which has no legacy variant in nrsls).

    Dense Urban config A and Indoor Hotspot need the analog-beam attachment
    and are not covered yet.
    """
    env = env.lower()
    tilt = {"rural-700m": 100.0, "rural-4g": 100.0, "rural-lmlc": 96.0,
            "mmtc-500m": 99.0, "mmtc-1732m": 93.0, "urllc-4g": 99.0,
            "urllc-700m": 99.0}[env]
    ant = BSAntennaConfig(M=8, N=1, P=2, Mp=1, Np=1, dV=0.8,
                          electrical_tilt_deg=tilt)
    common = dict(carrier=CarrierConfig(mu=0, n_size_grid=52),
                  noise_bandwidth_hz=10e6, bs_tx_power_dbm=46.0,
                  ue_noise_figure_db=7.0, min_d2d_m=10.0, n_floors=(1, 1),
                  bs_antenna=ant, ue_antenna=UEAntenna(M=1, N=1, P=2))
    if env.startswith("rural"):
        fc = 4e9 if env == "rural-4g" else 0.7e9
        isd = 6000.0 if env == "rural-lmlc" else 1732.0
        # A/B: 50 % indoor, 50 % in car; LMLC: 40 % indoor, 40 % pedestrian,
        # 20 % in car
        indoor, car = (0.4, 1 / 3) if env == "rural-lmlc" else (0.5, 1.0)
        # LMLC uses the M.2412 LMLC NLOS pathloss: max(PL_LOS, PL'_NLOS - 12)
        cfg = rma(carrier_freq_hz=fc, isd_m=isd, indoor_ratio=indoor,
                  in_car_ratio=car, o2i_model="low",
                  rma_nlos_offset_db=12.0 if env == "rural-lmlc" else 0.0,
                  **common)
    else:
        fc = 4e9 if env == "urllc-4g" else 0.7e9
        isd = 1732.0 if env == "mmtc-1732m" else 500.0
        indoor = 0.2 if env.startswith("urllc") else 0.8
        car = 0.0                       # outdoor UMa UEs: no car loss
        cfg = uma(carrier_freq_hz=fc, isd_m=isd, indoor_ratio=indoor,
                  in_car_ratio=car, o2i_model=channel_model_a_o2i,
                  o2i_high_loss_ratio=0.2, **common)
    return replace(cfg, name=f"RP-180524 {env}", **overrides)


def rp180524_inh(trxp_per_site: int = 1, **overrides) -> ScenarioConfig:
    """RP-180524 Table 1, Indoor Hotspot config A (4 GHz), 12 or 36 TRxP.

    12 TRxP: one TRxP per site pointing at the floor (mechanical tilt 180 deg
    in GCS, electrical tilt 90 deg in LCS).  36 TRxP: three TRxPs per site at
    30 / 150 / 270 deg, mechanically tilted to 110 deg (20 deg down).
    32 elements (4, 4, 2) mapped 1-to-1 to TXRUs, so port 0 is one element
    of the ceiling-mount pattern (M.2412 Table 10: 90 deg beamwidth, 25 dB
    limits, 5 dBi).  21 dBm in 10 MHz, UE NF 7 dB, UEs (1, 2, 2) at 1.5 m,
    no wrap-around, d2D_min = 0.  Channel model A = M.2412 InH_A.
    """
    tilt = 90.0 if trxp_per_site == 1 else 20.0
    bearings = (0.0,) if trxp_per_site == 1 else (30.0, 150.0, 270.0)
    ant = BSAntennaConfig(M=4, N=4, P=2, Mp=4, Np=4, dV=0.5, dH=0.5,
                          max_gain_dbi=5.0, hpbw_deg=90.0, front_back_db=25.0,
                          electrical_tilt_deg=90.0, mechanical_downtilt_deg=tilt)
    cfg = inh("open", carrier_freq_hz=4e9,
              carrier=CarrierConfig(mu=0, n_size_grid=52), noise_bandwidth_hz=10e6,
              bs_tx_power_dbm=21.0, ue_noise_figure_db=7.0, h_ut_outdoor_m=1.5,
              sector_bearings_deg=bearings, bs_antenna=ant,
              ue_antenna=UEAntenna(M=1, N=2, P=2), itu_model_a=True,
              name=f"RP-180524 InH {12 * trxp_per_site} TRxP")
    return replace(cfg, **overrides)


def dense_urban_a(**overrides) -> ScenarioConfig:
    """ITU-R M.2412 Table 5b, Dense Urban-eMBB configuration A (macro layer),
    FDD 10 MHz (the TR 37.910 Table 5.4.1.2.1-1(a) set-up).

    19 sites x 3 TRxPs, ISD 200 m, BS at 25 m, 4 GHz, 41 dBm per 10 MHz,
    15 kHz SCS (52 PRB), BS element 8 dBi, UE NF 7 dB, 10 UTs per TRxP:
    80 % indoor (20 % high-loss / 80 % low-loss buildings, 3 km/h), 20 %
    outdoor in cars (30 km/h).  gNB 32T: (M, N, P, Mg, Ng; Mp, Np) =
    (8, 8, 2, 1, 1; 2, 8); UT 4 ports (1, 2, 2).  Channel model A: the
    TR 38.901 UMa model (matches the RP-180524 UMa calibration).
    Spectral efficiency is normalised by the 10 MHz channel bandwidth.
    """
    ant = BSAntennaConfig(M=8, N=8, P=2, Mp=2, Np=8, dV=0.5, dH=0.5,
                          electrical_tilt_deg=102.0)
    cfg = uma(name="Dense Urban-eMBB A (FDD 10 MHz)", isd_m=200.0,
              carrier_freq_hz=4e9, carrier=CarrierConfig(mu=0, n_size_grid=52),
              noise_bandwidth_hz=None, channel_bandwidth_hz=10e6,
              bs_tx_power_dbm=41.0, ue_noise_figure_db=7.0, min_d2d_m=10.0,
              indoor_ratio=0.8, in_car_ratio=1.0, ue_speed_kmh=3.0,
              in_car_speed_kmh=30.0, o2i_model="mixed", o2i_high_loss_ratio=0.2,
              bs_antenna=ant, ue_antenna=UEAntenna(M=1, N=2, P=2))
    return replace(cfg, **overrides)


PRESETS["du-a"] = dense_urban_a
PRESETS["rp-inh-12trxp"] = lambda **kw: rp180524_inh(1, **kw)
PRESETS["rp-inh-36trxp"] = lambda **kw: rp180524_inh(3, **kw)


for _env in ("rural-700m", "rural-4g", "rural-lmlc", "mmtc-500m",
             "mmtc-1732m", "urllc-4g", "urllc-700m"):
    PRESETS[f"rp-{_env}"] = (lambda e: (lambda **kw: rp180524(e, **kw)))(_env)
