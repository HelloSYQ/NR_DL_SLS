"""Interference-aware (MMSE-IRC) post-equaliser SINR.

With the interference-plus-noise covariance R = sum_k H_k W_k W_k^H H_k^H
+ sigma^2 I at the UT, whitening H~ = L^-1 H (R = L L^H) turns the problem
into white noise of unit power.  For the effective whitened channel
G = H~ W of r layers the MMSE-IRC SINR of layer l is

    SINR_l = 1 / [(I + G^H G)^-1]_{ll} - 1,

and the Shannon rate of the precoder is log2 det(I + G^H G).  With R =
sigma^2 I this is the MMSE receiver of ``nrdlsim.receiver.batch_mmse_sinr``.
"""

from __future__ import annotations

import numpy as np


def whitening(r_cov: np.ndarray) -> np.ndarray:
    """L^-1 for R = L L^H, batched over leading axes."""
    l = np.linalg.cholesky(r_cov)
    eye = np.broadcast_to(np.eye(r_cov.shape[-1], dtype=r_cov.dtype), r_cov.shape)
    return np.linalg.solve(l, eye)


def mmse_sinr(g: np.ndarray) -> np.ndarray:
    """Per-layer SINR (linear) of whitened effective channels G (..., U, r)."""
    r = g.shape[-1]
    a = np.conj(np.swapaxes(g, -1, -2)) @ g + np.eye(r)
    inv = np.linalg.inv(a)
    d = np.real(np.diagonal(inv, axis1=-2, axis2=-1))
    return np.maximum(1.0 / np.maximum(d, 1e-12) - 1.0, 1e-9)


def evm_limited(sinr: np.ndarray, evm_percent: float) -> np.ndarray:
    """Post-equaliser SINR (linear) with an error-vector magnitude of
    ``evm_percent``: the EVM adds distortion of EVM^2 times the signal power
    on every layer, SINR' = 1 / (1 / SINR + EVM^2), a ceiling of 1 / EVM^2
    (32 dB at 2.5 %, 29.1 dB at 3.5 %).  0 leaves the SINR as it is."""
    if evm_percent <= 0:
        return sinr
    return 1.0 / (1.0 / sinr + (evm_percent / 100.0) ** 2)


def capacity(g: np.ndarray) -> np.ndarray:
    """log2 det(I + G^H G) of whitened effective channels G (..., U, r)."""
    r = g.shape[-1]
    a = np.conj(np.swapaxes(g, -1, -2)) @ g + np.eye(r)
    sign, logdet = np.linalg.slogdet(a)
    return logdet / np.log(2)
