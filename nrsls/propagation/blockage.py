"""UT self-blocking (the user's hand and body), TR 38.901 clause 7.6.4.1.

Blockage model A, self-blocking part only (no non-self blockers).  Every UT
is held in portrait mode (one hand) or landscape mode (two hands).  The UT
has a random azimuth orientation Omega_UT,alpha ~ U[0, 360) with
Omega_UT,beta = Omega_UT,gamma = 0, so its local coordinate system (LCS) is
the GCS turned by alpha about z: phi' = phi - alpha, theta' = theta.  The
self-blocking region of the mode (Table 7.6.4.1-1) is

    phi'_sb - x'_sb / 2 <= AOA' <= phi'_sb + x'_sb / 2
    theta'_sb - y'_sb / 2 <= ZOA' <= theta'_sb + y'_sb / 2

and a cluster whose centre arrival direction falls in it loses 30 dB
(step c); every ray of the cluster and every UT port are attenuated alike.
On LOS links the LOS ray is a ray of the first cluster (eq. 7.5-30) and
points the same way as its centre, so it is tested on its own direction.

The loss scales the cluster's contribution to the channel and to the port-0
RSRP (so it also acts on the serving-cell choice); the cluster powers that
pick the two strongest clusters for the sub-cluster delay split (step 11)
stay unblocked.  The orientation also turns the UT array.  Its elements are
isotropic and the rotation is about z, so the polarisation basis does not
change: the array is evaluated at the LCS arrival angles.

Per-antenna hand loss (``hand_loss_db`` > 0), not part of TR 38.901.  The
self-blocking above attenuates a cluster on every UT port alike, so it
cannot make one antenna weaker than another.  A hand on a handset also
covers some of its antennas, which then receive less from every direction.
Here every UT port is one antenna of the handset; the hand covers
``covered[0]`` of them in portrait mode (one hand) and ``covered[1]`` in
landscape mode (two hands), picked at random per UT, and a covered antenna
loses ``hand_loss_db`` in power: its row of every channel matrix, serving
and interfering, is scaled, and so is the interference of the cells that
are modelled as white noise, while the receiver's thermal noise is not
(``port_gain``).  Cell selection and the coupling gain are those of an
uncovered antenna.  The loss is a number to choose, not a measured one.
"""

from __future__ import annotations

from dataclasses import dataclass, replace

import numpy as np

from .clusters import Clusters

PORTRAIT, LANDSCAPE = 0, 1
# Table 7.6.4.1-1: (phi'_sb, x'_sb, theta'_sb, y'_sb) [deg], UT LCS
REGIONS = np.array([[260.0, 120.0, 100.0, 80.0],          # portrait
                    [40.0, 160.0, 110.0, 75.0]])          # landscape


@dataclass
class SelfBlocking:
    """Grip of every UT of a drop."""

    mode: np.ndarray            # (U,) PORTRAIT / LANDSCAPE
    bearing_deg: np.ndarray     # (U,) UT orientation Omega_UT,alpha [deg]
    loss_db: float = 30.0
    # per-antenna hand loss: (U, ports) power gain of every UT port, 1 or
    # 10^(-hand_loss_db / 10); None: no hand loss
    port_gain: np.ndarray | None = None


def draw_self_blocking(n_ue: int, landscape_ratio: float, loss_db: float,
                       rng, n_ports: int = 0, hand_loss_db: float = 0.0,
                       covered=(1, 2)) -> SelfBlocking:
    """Grip mode and orientation of every UT and, with ``hand_loss_db`` > 0,
    the antennas its hand covers: ``covered[mode]`` of the ``n_ports`` UT
    ports (at most all), every subset equally likely.  The antennas are
    drawn last, so mode and orientation are the same with and without them."""
    mode = np.where(rng.random(n_ue) < landscape_ratio, LANDSCAPE, PORTRAIT)
    bearing = rng.uniform(0.0, 360.0, n_ue)
    port_gain = None
    if hand_loss_db > 0:
        if n_ports < 1:
            raise ValueError("the hand loss needs the number of UT ports")
        rank = np.argsort(np.argsort(rng.random((n_ue, n_ports)), axis=1), axis=1)
        k = np.minimum(np.asarray(covered)[mode], n_ports)            # (U,)
        port_gain = np.where(rank < k[:, None], 10 ** (-hand_loss_db / 10), 1.0)
    return SelfBlocking(mode=mode, bearing_deg=bearing, loss_db=float(loss_db),
                        port_gain=port_gain)


def in_region(mode, bearing_deg, aoa_deg, zoa_deg) -> np.ndarray:
    """True where the GCS arrival direction (aoa, zoa) lies in the UT's
    self-blocking region.  ``mode`` / ``bearing_deg`` broadcast against the
    angles from the left (per link, angles (L, ...))."""
    mode = np.asarray(mode)
    aoa, zoa = np.asarray(aoa_deg, float), np.asarray(zoa_deg, float)
    extra = (1,) * (aoa.ndim - mode.ndim)
    phi, x, th, y = (REGIONS[mode, i].reshape(mode.shape + extra) for i in range(4))
    rot = np.asarray(bearing_deg, float).reshape(mode.shape + extra)
    d_az = np.mod(aoa - rot - phi + 180.0, 360.0) - 180.0
    return (np.abs(d_az) <= x / 2) & (np.abs(zoa - th) <= y / 2)


def apply_self_blocking(cl: Clusters, sb: SelfBlocking, ues=None) -> Clusters:
    """``cl`` with the self-blocking loss of the links' UTs (``ues`` (L,),
    default link l = UT l) and their orientation."""
    ues = np.arange(cl.valid.shape[0]) if ues is None else np.asarray(ues)
    mode, rot = sb.mode[ues], sb.bearing_deg[ues]
    att = 10 ** (-sb.loss_db / 10)
    hit = in_region(mode, rot, cl.aoa_c, cl.zoa_c)
    hit_los = in_region(mode, rot, cl.los_aoa, cl.los_zoa)
    return replace(cl, gain=np.where(hit, att, 1.0),
                   los_gain=np.where(hit_los, att, 1.0), ue_bearing_deg=rot.astype(float),
                   port_gain=None if sb.port_gain is None else sb.port_gain[ues])


def blocked_power_fraction(cl: Clusters) -> np.ndarray:
    """(L,) share of each link's multipath power (NLOS + LOS, K-weighted)
    lost to self-blocking; 0 without it."""
    k = cl.k_r
    p = np.where(cl.valid, cl.power, 0.0)
    g = np.ones(p.shape) if cl.gain is None else cl.gain
    gl = np.ones(k.shape) if cl.los_gain is None else cl.los_gain
    kept = (np.sum(p * g, axis=1) + k * gl) / (np.sum(p, axis=1) + k)
    return 1.0 - kept
