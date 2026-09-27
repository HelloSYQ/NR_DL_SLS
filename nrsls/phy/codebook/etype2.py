"""TS 38.214 clause 5.2.2.2.5: Rel-16 enhanced Type-II codebook (ranks 1-4).

Per layer l the precoder of PMI sub-band t is

    w_l(t) ~ [ sum_i v_{m(i)} sum_f x_{0,i,f} e^{j 2 pi t n3(f) / N3} ;
               sum_i v_{m(i)} sum_f x_{1,i,f} e^{j 2 pi t n3(f) / N3} ]

(W = W1 W~2 W_f^H), normalised to unit norm per sub-band; the rank-v
precoder is [w_1 ... w_v] / sqrt(v).

  * W1: L orthogonal 2-D DFT beams v_{O1 n1 + q1, O2 n2 + q2} of one
    rotation (q1, q2), common to both polarisations and all layers;
  * W_f: M_v = ceil(p_v N3 / R) DFT basis vectors out of N3 (free choice for
    N3 <= 19; a cyclic shift of the indices is only a per-sub-band phase);
  * W~2: 2L x M_v coefficients, at most K0 = ceil(beta 2L M1) non-zero per
    layer and 2 K0 in total, quantised relative to the strongest one (SCI):
    4-bit reference amplitude of the weaker polarisation (2^(-k/4), k =
    0..14), 3-bit differential amplitudes (2^(-k/2), k = 0..7), 16-PSK.

Parameter combinations (Table 5.2.2.2.5-1): (L, p_v for v = 1-2, p_v for
v = 3-4, beta); combinations 7-8 support ranks 1-2 only.

The UT side (``derive``) is the usual eigenvector-based derivation: the
dominant eigenvectors of the whitened channel per PMI sub-band, phase-aligned
on the strongest beam, projected on the best L beams and on the M_v
strongest delay-domain DFT vectors, pruned to K0 coefficients and quantised.
"""

from __future__ import annotations

from dataclasses import dataclass
from math import ceil, comb, log2

import numpy as np

PARAM_COMBOS = {
    1: (2, 1 / 4, 1 / 8, 1 / 4), 2: (2, 1 / 4, 1 / 8, 1 / 2),
    3: (4, 1 / 4, 1 / 8, 1 / 4), 4: (4, 1 / 4, 1 / 8, 1 / 2),
    5: (4, 1 / 4, 1 / 4, 3 / 4), 6: (4, 1 / 2, 1 / 4, 1 / 2),
    7: (6, 1 / 4, None, 1 / 2), 8: (6, 1 / 4, None, 3 / 4),
}
REF_AMP = 2.0 ** (-np.arange(15) / 4)          # 4-bit reference amplitude
DIFF_AMP = 2.0 ** (-np.arange(8) / 2)          # 3-bit differential amplitude


def _nearest_log(x, levels):
    """Nearest quantisation level in the log domain (x > 0)."""
    lx = np.log(np.maximum(x, 1e-12))[..., None]
    return levels[np.argmin(np.abs(lx - np.log(levels)), axis=-1)]


def _bits(n):
    return ceil(log2(n)) if n > 1 else 0


@dataclass
class ETypeIICodebook:
    n1: int = 8
    n2: int = 2
    o1: int = 4
    o2: int = 4
    combo: int = 6
    n3: int = 18                 # PMI sub-bands (R = 1)
    r: int = 1

    def __post_init__(self):
        # TS 38.214 5.2.2.2.5: P_CSI-RS in {4, 8, 12, 16, 24, 32};
        # combinations 3-8 not with 4 ports, 7-8 only with 32 ports
        p = self.n_ports
        if p < 4:
            raise ValueError(f"eType-II needs >= 4 CSI-RS ports, got {p}")
        if (p == 4 and self.combo >= 3) or (p < 32 and self.combo >= 7):
            raise ValueError(f"parameter combination {self.combo} not supported "
                             f"with {p} ports")

    @property
    def n_ports(self):
        return 2 * self.n1 * self.n2

    def params(self, rank):
        l, pv12, pv34, beta = PARAM_COMBOS[self.combo]
        pv = pv12 if rank <= 2 else pv34
        if pv is None:
            raise ValueError(f"parameter combination {self.combo} supports rank <= 2")
        m_v = ceil(pv * self.n3 / self.r)
        m1 = ceil(pv12 * self.n3 / self.r)
        k0 = ceil(beta * 2 * l * m1)
        return l, m_v, k0

    def supports(self, rank):
        return rank <= 4 and not (PARAM_COMBOS[self.combo][2] is None and rank > 2)

    def _beam_matrix(self, q1, q2):
        """(N1 N2, N1 N2) orthonormal DFT beams of rotation (q1, q2)."""
        n1, n2, o1, o2 = self.n1, self.n2, self.o1, self.o2
        k1 = np.arange(n1)
        k2 = np.arange(n2)
        cols = []
        for a in range(n1):
            for b in range(n2):
                h = np.exp(2j * np.pi * (o1 * a + q1) * k1 / (o1 * n1))
                v = np.exp(2j * np.pi * (o2 * b + q2) * k2 / (o2 * n2))
                cols.append(np.kron(h, v))
        return np.array(cols).T / np.sqrt(n1 * n2)

    def _all_beams(self):
        """(N1 N2, O1 O2, N1 N2): the orthogonal beam set of every rotation."""
        if getattr(self, "_beams_cache", None) is None:
            self._beams_cache = np.stack(
                [self._beam_matrix(q1, q2) for q1 in range(self.o1)
                 for q2 in range(self.o2)], axis=1)
        return self._beams_cache

    def payload_bits(self, rank, k_nz):
        l, m_v, k0 = self.params(rank)
        part1 = _bits(2 * k0)                       # number of non-zero coeffs
        sd = _bits(self.o1 * self.o2) + _bits(comb(self.n1 * self.n2, l))
        fd = rank * _bits(comb(self.n3 - 1, m_v - 1)) if self.n3 <= 19 else 0
        per_layer = rank * (_bits(2 * l) + 2 * l * m_v + 4)   # SCI, bitmap, ref amp
        coeff = 7 * max(k_nz - rank, 0)                        # 3 + 4 bits each
        return part1 + sd + fd + per_layer + coeff

    def derive(self, hw, subband_of_f, rank):
        """Quantised eType-II precoders (N3, S, rank) from whitened channels
        hw (F, U, S); returns (W, number of non-zero coefficients)."""
        n12 = self.n1 * self.n2
        l, m_v, k0 = self.params(rank)
        # 1. dominant eigenvectors per PMI sub-band (batched)
        cov_f = np.einsum("fus,fut->fst", np.conj(hw), hw)            # (F, S, S)
        onehot = (subband_of_f[None, :] == np.arange(self.n3)[:, None]).astype(float)
        cov = np.tensordot(onehot, cov_f, axes=(1, 0))               # (N3, S, S)
        empty = onehot.sum(axis=1) == 0
        if empty.any():
            cov[empty] = cov_f.sum(axis=0)
        _, vec = np.linalg.eigh(cov)
        e = vec[..., ::-1][..., :rank]                               # (N3, S, rank)
        ep = e.reshape(self.n3, 2, n12, rank)       # (t, pol, port, layer)
        # 2. SD basis: rotation and L strongest orthogonal beams, all
        #    O1 O2 rotations at once
        b_all = self._all_beams()                                    # (n12, R, n12)
        proj = np.einsum("sqk,tpsl->qktpl", np.conj(b_all), ep)
        pw = np.sum(np.abs(proj) ** 2, axis=(2, 3, 4))               # (R, n12)
        top = np.sort(pw, axis=1)[:, ::-1][:, :l].sum(axis=1)
        q = int(np.argmax(top))
        sel = np.argsort(pw[q])[::-1][:l]
        beams = b_all[:, q, sel]                                      # (n12, L)
        c = np.einsum("sk,tpsl->tlpk", np.conj(beams), ep)     # (t, layer, pol, L)
        c = c.reshape(self.n3, rank, 2 * l)                    # (t, layer, 2L)
        # 3. phase alignment on the strongest (pol, beam) of each layer
        strong = np.argmax(np.sum(np.abs(c) ** 2, axis=0), axis=-1)   # (layer,)
        ref = c[:, np.arange(rank), strong]                           # (t, layer)
        c = c * np.exp(-1j * np.angle(ref))[..., None]
        # 4. delay-domain DFT: x[f] = 1/N3 sum_t c[t] e^{-j 2 pi t f / N3}
        t = np.arange(self.n3)
        dft = np.exp(-2j * np.pi * np.outer(t, t) / self.n3) / self.n3
        x = np.einsum("tf,tlc->lcf", dft, c)                          # (layer, 2L, N3)
        fsel = np.argsort(np.sum(np.abs(x) ** 2, axis=1), axis=-1)[:, ::-1][:, :m_v]
        xs = np.take_along_axis(x, fsel[:, None, :], axis=2)          # (layer, 2L, Mv)
        # 5. keep the K0 strongest per layer and 2 K0 in total
        mag = np.abs(xs)
        keep = np.zeros(mag.shape, bool)
        for ly in range(rank):
            order = np.argsort(mag[ly].ravel())[::-1][:k0]
            keep[ly].flat[order] = True
        if keep.sum() > 2 * k0:
            thr = np.sort(mag[keep])[::-1][2 * k0 - 1]
            keep &= mag >= thr
        xs = np.where(keep, xs, 0)
        # 6. quantisation relative to the strongest coefficient (SCI)
        xq = np.zeros_like(xs)
        for ly in range(rank):
            a = xs[ly]
            s = np.unravel_index(np.argmax(np.abs(a)), a.shape)
            a = a / a[s]
            half = np.abs(a).reshape(2, l, m_v)
            pref = half.max(axis=(1, 2))
            p_strong = s[0] // l
            refq = np.ones(2)
            refq[1 - p_strong] = _nearest_log(pref[1 - p_strong] / max(pref[p_strong], 1e-12),
                                              REF_AMP)
            amp = np.abs(a).reshape(2, l, m_v) / refq[:, None, None]
            diff = np.where(amp > 0, _nearest_log(np.minimum(amp, 1.0), DIFF_AMP), 0.0)
            ph = np.round(np.angle(a).reshape(2, l, m_v) / (2 * np.pi / 16)) * (2 * np.pi / 16)
            q = refq[:, None, None] * diff * np.exp(1j * ph)
            q = np.where(np.abs(a).reshape(2, l, m_v) > 0, q, 0).reshape(2 * l, m_v)
            q[s] = 1.0
            xq[ly] = q
        # 7. reconstruct per sub-band and normalise
        yt = np.exp(2j * np.pi * np.einsum("t,lm->ltm", t, fsel) / self.n3)  # (layer, t, Mv)
        ct = np.einsum("ltm,lcm->tlc", yt, xq).reshape(self.n3, rank, 2, l)
        w = np.einsum("sk,tlpk->tpsl", beams, ct).reshape(self.n3, self.n_ports, rank)
        w = w / np.linalg.norm(w, axis=1, keepdims=True) / np.sqrt(rank)
        return w, int(keep.sum())
