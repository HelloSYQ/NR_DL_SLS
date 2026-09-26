"""Multi-drop driver.

Drop ``i`` of a run with seed ``s`` uses the random stream
``np.random.default_rng([s, i])``, so results do not depend on how drops are
spread over worker processes.  Workers are spawned with single-threaded BLAS:
one drop is small, and letting every worker start its own BLAS thread pool
oversubscribes the cores (a 20x slowdown).
"""

from __future__ import annotations

import multiprocessing
import os
from concurrent.futures import ProcessPoolExecutor
from contextlib import contextmanager
from dataclasses import dataclass, fields

import numpy as np

from ..config.scenario import ScenarioConfig
from .drop import generate_drop


@dataclass
class LargeScaleStats:
    """Per-UT large-scale results, concatenated over drops."""

    coupling_gain_db: np.ndarray   # serving cell
    geometry_db: np.ndarray
    los: np.ndarray                # LOS state of the serving link
    o2i: np.ndarray
    d2d_m: np.ndarray              # to the serving site
    h_ut_m: np.ndarray
    ue_per_cell: np.ndarray        # served UTs per cell (one entry per cell)
    drop_ring: np.ndarray          # hex ring of the site the UT was dropped in
    drop: np.ndarray               # drop index

    @classmethod
    def concat(cls, parts):
        return cls(**{f.name: np.concatenate([getattr(p, f.name) for p in parts])
                      for f in fields(cls)})


def _site_ring(site_xy: np.ndarray, isd: float) -> np.ndarray:
    """Hex ring index of each site (0 = centre)."""
    q = (site_xy[:, 0] - site_xy[:, 1] / np.sqrt(3.0)) / isd
    r = site_xy[:, 1] * 2.0 / np.sqrt(3.0) / isd
    return np.rint(np.max(np.abs([q, r, q + r]), axis=0)).astype(int)


def drop_stats(cfg: ScenarioConfig, seed: int, index: int) -> LargeScaleStats:
    d = generate_drop(cfg, np.random.default_rng([seed, index]))
    n = d.ues.n
    ring = (_site_ring(d.layout.site_xy, d.layout.isd_m)
            if d.layout.kind == "hex" else np.zeros(d.layout.n_sites, int))
    return LargeScaleStats(
        coupling_gain_db=d.serving_coupling_gain_db,
        geometry_db=d.geometry_db,
        los=d.per_ut(d.los),
        o2i=d.ues.o2i,
        d2d_m=d.per_ut(d.d2d_m),
        h_ut_m=d.ues.h_m,
        ue_per_cell=np.bincount(d.serving_cell, minlength=d.layout.n_cells),
        drop_ring=ring[d.layout.cell_site[d.ues.drop_cell]],
        drop=np.full(n, index),
    )


def _worker(args):
    return drop_stats(*args)


_BLAS_THREAD_VARS = ("OMP_NUM_THREADS", "OPENBLAS_NUM_THREADS",
                     "MKL_NUM_THREADS")


@contextmanager
def _single_threaded_blas_env():
    """Set the BLAS thread variables inherited by spawned workers."""
    saved = {k: os.environ.get(k) for k in _BLAS_THREAD_VARS}
    os.environ.update({k: "1" for k in _BLAS_THREAD_VARS})
    try:
        yield
    finally:
        for k, v in saved.items():
            if v is None:
                os.environ.pop(k, None)
            else:
                os.environ[k] = v


def parallel_map(fn, jobs, n_jobs: int):
    """``map(fn, jobs)`` over ``n_jobs`` spawned single-BLAS-thread workers."""
    if n_jobs <= 1:
        return [fn(j) for j in jobs]
    with _single_threaded_blas_env():
        ctx = multiprocessing.get_context("spawn")
        with ProcessPoolExecutor(max_workers=n_jobs, mp_context=ctx) as ex:
            return list(ex.map(fn, jobs))


def run_large_scale(cfg: ScenarioConfig, n_drops: int, seed: int = 1,
                    n_jobs: int = 1) -> LargeScaleStats:
    jobs = [(cfg, seed, i) for i in range(n_drops)]
    return LargeScaleStats.concat(parallel_map(_worker, jobs, n_jobs))
