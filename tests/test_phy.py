"""Phase 3 PHY: Type-I codebook, IRC SINR, CSI selection."""

import numpy as np
import pytest

from nrsls.phy.codebook.type1 import TypeICodebook
from nrsls.phy.csi import CSIProcessor
from nrsls.phy.sinr import capacity, mmse_sinr, whitening


@pytest.mark.parametrize("rank,size", [(1, 32 * 8 * 4), (2, 32 * 8 * 4 * 2),
                                       (3, 16 * 8 * 4 * 2), (4, 16 * 8 * 4 * 2)])
def test_type1_sizes_norms_and_orthogonal_layers(rank, size):
    cb = TypeICodebook(8, 2, 4, 4)
    idx, w = cb.precoders(rank)
    assert w.shape == (size, 32, rank) and len(idx) == size
    assert np.allclose(np.linalg.norm(w, axis=(1, 2)), 1.0)
    # layers are orthogonal with equal power
    g = np.conj(np.swapaxes(w, 1, 2)) @ w
    assert np.allclose(g, np.eye(rank)[None] / rank, atol=1e-12)


def test_type1_small_port_counts():
    for n1, n2 in [(2, 1), (2, 2), (4, 1)]:
        cb = TypeICodebook(n1, n2, 4, 4 if n2 > 1 else 1)
        for rank in (1, 2, 3, 4):
            if rank > cb.n_ports:
                continue
            _, w = cb.precoders(rank)
            assert np.allclose(np.linalg.norm(w, axis=(1, 2)), 1.0)


def test_irc_reduces_to_mmse_and_capacity_consistency():
    rng = np.random.default_rng(0)
    h = (rng.normal(size=(50, 4, 3)) + 1j * rng.normal(size=(50, 4, 3))) / np.sqrt(2)
    n0 = 0.3
    lw = whitening(np.broadcast_to(n0 * np.eye(4), (50, 4, 4)).astype(complex))
    g = lw @ h
    from nrdlsim.receiver import batch_mmse_sinr
    assert np.allclose(mmse_sinr(g), batch_mmse_sinr(h, n0), rtol=1e-6)
    # rate of the MMSE-SIC decomposition equals the log det
    assert np.all(capacity(g) >= np.sum(np.log2(1 + mmse_sinr(g)), axis=-1) - 1e-9)


def test_csi_picks_the_matching_codeword():
    """A channel that is exactly a rank-1 Type-I beam is reported as that
    beam at rank 1 with a high CQI."""
    cb = TypeICodebook(8, 2, 4, 4)
    idx, w = cb.precoders(1)
    target = 137
    v = w[target, :, 0]
    f = 16
    hw = np.tile((30 * np.conj(v))[None, None, :], (f, 1, 1))     # U = 1
    hw = np.concatenate([hw, 1e-3 * hw], axis=1)                  # U = 2
    proc = CSIProcessor(8, 2, max_rank=2, n_beams=4)
    rep = proc.select(hw, np.repeat(np.arange(2), 8), 2, slot=0)
    assert rep.rank == 1
    # wideband i1 and the same co-phasing i2 in both sub-bands
    i = [int(x) for x in idx[target]]
    assert rep.pmi == (i[0], i[1], i[2], (i[3], i[3]))
    wb = CSIProcessor(8, 2, max_rank=2, n_beams=4, pmi_subband=False)
    assert wb.select(hw, np.repeat(np.arange(2), 8), 2, slot=0).pmi == tuple(i)
    assert rep.cqi_wb >= 13 and len(rep.cqi_sb) == 2


def test_type1_subband_i2_follows_the_co_phasing():
    """Each sub-band has its own polarisation co-phasing: sub-band i2 finds
    it, a wideband i2 cannot."""
    cb = TypeICodebook(8, 2, 4, 4)
    idx, w = cb.precoders(1)
    base = 4 * (8 * 5 + 3)                     # beam (l, m) = (5, 3), i2 = 0
    f, n_sb = 32, 4
    sb = np.repeat(np.arange(n_sb), f // n_sb)
    hw = np.stack([30 * np.conj(w[base + b % 4, :, 0])[None, :] for b in sb])
    hw = np.concatenate([hw, 1e-3 * hw], axis=1)             # (F, 2, 32)
    rep = CSIProcessor(8, 2, max_rank=1).select(hw, sb, 1, slot=0)
    assert rep.pmi[:3] == (5, 3, 0) and rep.pmi[3] == (0, 1, 2, 3)
    assert rep.w.shape == (n_sb, 32, 1) and rep.pmi_bits == 8 + n_sb * 2         # i1: 5 + 3 bits
    wb = CSIProcessor(8, 2, max_rank=1, pmi_subband=False).select(hw, sb, 1, 0)
    assert wb.cqi_wb < rep.cqi_wb


def test_csi_svd_rank_follows_channel_rank():
    rng = np.random.default_rng(1)
    f, u, s = 8, 4, 32
    a = rng.normal(size=(u, 2)) + 1j * rng.normal(size=(u, 2))
    b = rng.normal(size=(2, s)) + 1j * rng.normal(size=(2, s))
    hw = np.tile((20 * a @ b)[None], (f, 1, 1))                   # rank 2, high SNR
    rep = CSIProcessor(8, 2, codebook="svd").select(hw, np.zeros(f, int), 2, 0)
    assert rep.rank == 2


def _multipath_channel(rng, f=36, u=4, s=32, n_paths=6, n1=8, n2=2):
    """Frequency-selective channel from a few DFT-like paths (whitened)."""
    tau = rng.uniform(0, 1.0, n_paths)
    h = np.zeros((f, u, s), complex)
    for p in range(n_paths):
        th1, th2 = rng.uniform(-1, 1, 2)
        a = np.kron(np.exp(1j * np.pi * th1 * np.arange(n1)),
                    np.exp(1j * np.pi * th2 * np.arange(n2)))
        a = np.concatenate([a, np.exp(1j * rng.uniform(0, 2 * np.pi)) * a])
        b = rng.normal(size=u) + 1j * rng.normal(size=u)
        g = (rng.normal() + 1j * rng.normal()) * 10
        h += g * np.exp(-2j * np.pi * np.arange(f)[:, None, None] * tau[p] / 6) \
            * b[None, :, None] * a[None, None, :]
    return h


def _eig_gain(hw, w, sb):
    """Mean fraction of the dominant eigen-direction energy captured."""
    out = []
    for fi in range(hw.shape[0]):
        cov = hw[fi].conj().T @ hw[fi]
        lam = np.linalg.eigvalsh(cov)[-1]
        v = w[sb[fi], :, 0]
        v = v / np.linalg.norm(v)
        out.append(np.real(v.conj() @ cov @ v) / lam)
    return np.mean(out)


def test_etype2_shapes_norms_and_payload():
    from nrsls.phy.codebook.etype2 import ETypeIICodebook
    rng = np.random.default_rng(3)
    hw = _multipath_channel(rng)
    sb = np.repeat(np.arange(18), 2)
    for combo in (1, 4, 6, 8):
        cb = ETypeIICodebook(8, 2, 4, 4, combo, 18)
        for rank in (1, 2, 3, 4):
            if not cb.supports(rank):
                continue
            w, knz = cb.derive(hw, sb, rank)
            assert w.shape == (18, 32, rank)
            assert np.allclose(np.linalg.norm(w, axis=(1, 2)), 1.0)
            l, m_v, k0 = cb.params(rank)
            assert 1 <= knz <= 2 * k0
    with pytest.raises(ValueError):
        ETypeIICodebook(1, 1, 4, 1, combo=1)             # 2 ports
    with pytest.raises(ValueError):
        ETypeIICodebook(2, 1, 4, 1, combo=4)             # 4 ports, L = 4
    assert (ETypeIICodebook(combo=6).payload_bits(2, 40)
            > ETypeIICodebook(combo=1).payload_bits(2, 10))


def test_etype2_beats_type1_and_improves_with_resolution():
    from nrsls.phy.codebook.etype2 import ETypeIICodebook
    rng = np.random.default_rng(4)
    g_small, g_big, g_t1 = [], [], []
    sb = np.repeat(np.arange(18), 2)
    for _ in range(6):
        hw = _multipath_channel(rng)
        g_small.append(_eig_gain(hw, ETypeIICodebook(combo=1).derive(hw, sb, 1)[0], sb))
        g_big.append(_eig_gain(hw, ETypeIICodebook(combo=6).derive(hw, sb, 1)[0], sb))
        rep = CSIProcessor(8, 2, max_rank=1).select(hw, sb, 2, 0)
        g_t1.append(_eig_gain(hw, np.broadcast_to(rep.w, (18, 32, 1)), sb))
    assert np.mean(g_big) > np.mean(g_small) > np.mean(g_t1)
    assert np.mean(g_big) > 0.85
