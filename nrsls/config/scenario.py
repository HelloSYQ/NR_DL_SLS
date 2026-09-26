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

    # --- O2I building penetration (TR 38.901 7.4.3.1) ---
    # 'low' | 'high' | 'mixed' (high-loss share = o2i_high_loss_ratio) |
    # 'legacy' (Table 7.4.3-3: 20 dB wall, UMa/UMi below 6 GHz)
    o2i_model: str = "mixed"
    o2i_high_loss_ratio: float = 0.2
    d2d_in_max_m: float = 25.0        # indoor distance: min of two U(0, max)

    # --- RMa environment (Table 7.4.1-1) ---
    building_height_m: float = 5.0
    street_width_m: float = 20.0

    # --- shadow fading ---
    shadow_fading: bool = True
    sf_spatial_correlation: bool = True

    # --- antennas ---
    bs_antenna: BSAntennaConfig = field(default_factory=BSAntennaConfig)
    ue_antenna: UEAntenna = field(default_factory=UEAntenna)

    def __post_init__(self):
        if self.scenario not in SCENARIOS:
            raise ValueError(f"unknown scenario {self.scenario!r}; "
                             f"expected one of {SCENARIOS}")
        if self.o2i_model not in ("low", "high", "mixed", "legacy"):
            raise ValueError(f"unknown O2I model {self.o2i_model!r}")
        if self.o2i_model == "legacy" and self.family not in ("uma", "umi"):
            raise ValueError("the legacy O2I model covers UMa and UMi only")

    @property
    def family(self) -> str:
        """'uma' | 'umi' | 'rma' | 'inh'."""
        return self.scenario.split("-")[0].lower()

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
