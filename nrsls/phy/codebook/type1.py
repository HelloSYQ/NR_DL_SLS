"""TS 38.214 clause 5.2.2.2.1: Type-I single-panel codebook, ranks 1-4.

Port layout (N1, N2) with oversampling (O1, O2) and two polarisations,
P = 2 N1 N2 CSI-RS ports.  Inside one polarisation the port index is
n1 * N2 + n2 (N2 fastest), the order of v_{l,m} = u_m (x) [1, e^{j2pi l/O1N1},
...]^T; the second polarisation follows.  This matches
:func:`nrsls.propagation.fast_fading.bs_port_layout` with N1 = Np
(horizontal TXRUs) and N2 = Mp (vertical TXRUs).

codebookMode = 1:
  * rank 1:  W = [v_lm ; phi_n v_lm] / sqrt(P),          n = i2 in 0..3
  * rank 2:  W = [[v_lm, v_l'm'], [phi_n v_lm, -phi_n v_l'm']] / sqrt(2P),
             (l', m') = (l + k1, m + k2) from i1,3 (Table 5.2.2.2.1-3),
             n = i2 in 0..1
  * ranks 3-4 for P >= 16 (Table 5.2.2.2.1-5/6): beams v~_lm over half of
    the N1 dimension, co-phasing theta_p = e^{j pi p / 4} between the two
    halves (p = i1,3 in 0..3) and phi_n (n = i2 in 0..1) between the
    polarisations; P < 16 uses the two-beam form of ranks 3-4 with the
    rank-2 (k1, k2) offsets.

phi_n = e^{j pi n / 2}.  Every precoder has unit Frobenius norm.
"""

from __future__ import annotations

from dataclasses import dataclass
from itertools import product

import numpy as np


def _u(m, n2, o2):
    return np.exp(2j * np.pi * m * np.arange(n2) / (o2 * n2))


def _v(l, m, n1, n2, o1, o2, half=False):
    """v_{l,m} (length N1 N2) or, with ``half``, v~_{l,m} (length N1 N2 / 2)."""
    k = n1 // 2 if half else n1
    step = 4 * np.pi if half else 2 * np.pi
    return np.kron(np.exp(1j * step * l * np.arange(k) / (o1 * n1)), _u(m, n2, o2))


def rank2_offsets(n1, n2, o1, o2):
    """(k1, k2) for i1,3 = 0..3 (Table 5.2.2.2.1-3)."""
    if n1 > n2 > 1:
        return [(0, 0), (o1, 0), (0, o2), (2 * o1, 0)]
    if n1 == n2:
        return [(0, 0), (o1, 0), (0, o2), (o1, o2)]
    if n2 == 1 and n1 > 2:
        return [(0, 0), (o1, 0), (2 * o1, 0), (3 * o1, 0)]
    return [(0, 0), (o1, 0)]                  # N1 = 2, N2 = 1


@dataclass
class TypeICodebook:
    n1: int = 8
    n2: int = 2
    o1: int = 4
    o2: int = 4

    @property
    def n_ports(self) -> int:
        return 2 * self.n1 * self.n2

    def _phi(self, n):
        return np.exp(1j * np.pi * n / 2)

    def precoders(self, rank: int):
        """(indices, W) with W of shape (n_codewords, P, rank)."""
        n1, n2, o1, o2 = self.n1, self.n2, self.o1, self.o2
        p = self.n_ports
        ws, idx = [], []
        if rank == 1:
            for l, m, n in product(range(n1 * o1), range(n2 * o2), range(4)):
                v = _v(l, m, n1, n2, o1, o2)
                ws.append(np.concatenate([v, self._phi(n) * v])[:, None] / np.sqrt(p))
                idx.append((l, m, 0, n))
        elif rank == 2:
            for (l, m), k3, n in product(product(range(n1 * o1), range(n2 * o2)),
                                         range(len(rank2_offsets(n1, n2, o1, o2))),
                                         range(2)):
                k1, k2 = rank2_offsets(n1, n2, o1, o2)[k3]
                a = _v(l, m, n1, n2, o1, o2)
                b = _v(l + k1, m + k2, n1, n2, o1, o2)
                ph = self._phi(n)
                w = np.stack([np.concatenate([a, ph * a]),
                              np.concatenate([b, -ph * b])], axis=1)
                ws.append(w / np.sqrt(2 * p))
                idx.append((l, m, k3, n))
        elif rank in (3, 4) and p >= 16:
            for l, m, pp, n in product(range(n1 * o1 // 2), range(n2 * o2),
                                       range(4), range(2)):
                vt = _v(l, m, n1, n2, o1, o2, half=True)
                th = np.exp(1j * np.pi * pp / 4)
                ph = self._phi(n)
                if rank == 3:
                    signs = [(1, 1, 1), (1, -1, 1), (1, 1, -1), (1, -1, -1)]
                else:
                    signs = [(1, 1, 1, 1), (1, -1, 1, -1), (1, 1, -1, -1),
                             (1, -1, -1, 1)]
                blocks = [1, th, ph, ph * th]
                cols = [np.concatenate([blocks[r] * signs[r][c] * vt
                                        for r in range(4)])
                        for c in range(rank)]
                ws.append(np.stack(cols, axis=1) / np.sqrt(rank * p))
                idx.append((l, m, pp, n))
        elif rank in (3, 4):
            offs = rank2_offsets(n1, n2, o1, o2)
            for (l, m), k3, n in product(product(range(n1 * o1), range(n2 * o2)),
                                         range(len(offs)), range(2)):
                k1, k2 = offs[k3]
                a = _v(l, m, n1, n2, o1, o2)
                b = _v(l + k1, m + k2, n1, n2, o1, o2)
                ph = self._phi(n)
                cols = [np.concatenate([a, ph * a]), np.concatenate([b, ph * b]),
                        np.concatenate([a, -ph * a])]
                if rank == 4:
                    cols.append(np.concatenate([b, -ph * b]))
                ws.append(np.stack(cols, axis=1) / np.sqrt(rank * p))
                idx.append((l, m, k3, n))
        else:
            raise ValueError("ranks 1-4 only")
        return np.array(idx), np.array(ws)
