"""Dynamic time warping between two recitations of the same text.

Steps (1,1), (1,2), (2,1), (1,3), (3,1): one recitation may be locally up to 3× faster than the
other, and each row only depends on earlier rows, so a row is computed with numpy in one go.
Two passes: a coarse one over everything at 1 frame/s, then a fine one at the full frame rate
in a band around the coarse path. An 80-minute surah takes a few seconds.
"""
import numpy as np

INF = np.float32(1e30)
# (di, dj, extra cells on the step whose cost is added: list of (di, dj) back from the target)
_STEPS = ((1, 1, ()), (1, 2, ((0, 1),)), (2, 1, ((1, 0),)), (1, 3, ((0, 1), (0, 2))), (3, 1, ((1, 0), (2, 0))))


def _dist(a: np.ndarray, b: np.ndarray) -> np.ndarray:
    return np.sqrt(np.maximum(((a[:, None, :] - b[None, :, :]) ** 2).sum(-1), 0)).astype(np.float32)


def skip_cost(A: np.ndarray, B: np.ndarray, q: float = 30, seed: int = 0) -> float:
    """Cost of leaving one frame of A unmatched: a low percentile of random A-B distances, so
    unrelated audio (talk, silence, music) is cheaper to skip than to match, and recitation is not."""
    r = np.random.default_rng(seed)
    a = A[r.integers(0, len(A), min(len(A), 400))]; b = B[r.integers(0, len(B), min(len(B), 400))]
    return float(np.percentile(_dist(a, b), q))


def banded(A: np.ndarray, B: np.ndarray, center: np.ndarray, R: int, open_a: bool = False, tau: float = 0.0) -> np.ndarray:
    """Path [(i, j)] through all of B; row i only considers |j - center[i]| <= R.
    open_a=False: from (0,0) to (len(A)-1, len(B)-1). open_a=True: B may start and end anywhere in A
    (talk before / after the recitation in A); every skipped frame of A costs `tau`."""
    n, m = len(A), len(B)
    W = 2 * R + 1
    lo = np.clip(np.round(center).astype(int) - R, 0, max(0, m - W))
    D = np.full((n, W), INF, np.float32)
    C = np.full((n, W), INF, np.float32)
    back = np.zeros((n, W), np.int8)
    cols = lo[:, None] + np.arange(W)[None, :]
    for i in range(n):
        jj = cols[i]; ok = jj < m
        c = np.full(W, INF, np.float32)
        c[ok] = _dist(A[i:i + 1], B[jj[ok]])[0]
        C[i] = c
        if i == 0:
            if lo[0] == 0: D[0, 0] = c[0]; back[0, 0] = -1
            continue
        best = np.full(W, INF, np.float32); arg = np.zeros(W, np.int8)
        for s, (di, dj, extra) in enumerate(_STEPS):
            pi = i - di
            if pi < 0: continue
            pb = jj - dj - lo[pi]
            valid = ok & (pb >= 0) & (pb < W)
            if not valid.any(): continue
            v = np.full(W, INF, np.float32)
            v[valid] = D[pi, pb[valid]]
            for ei, ej in extra:
                ri = i - ei
                eb = jj - ej - lo[ri]
                ev = valid & (eb >= 0) & (eb < W)
                add = np.full(W, INF, np.float32); add[ev] = C[ri, eb[ev]]
                v = v + add
            better = v < best
            best[better] = v[better]; arg[better] = s
        D[i] = np.minimum(best + c, INF)
        back[i] = arg
        if open_a and lo[i] == 0 and c[0] + tau * i < D[i, 0]:   # B starts here, after skipping i frames
            D[i, 0] = c[0] + tau * i; back[i, 0] = -1
    # end: last cell of B
    if open_a:
        rows = np.flatnonzero((lo <= m - 1) & (m - 1 < lo + W))
        score = D[rows, m - 1 - lo[rows]] + tau * (n - 1 - rows)
        i, j = int(rows[np.argmin(score)]), m - 1
    else:
        i, j = n - 1, m - 1
        if D[i, j - lo[i]] >= INF: j = int(lo[i] + np.argmin(D[i]))   # end not reachable: best in last row
    path = [(i, j)]
    while i > 0:
        b = j - lo[i]
        if back[i, b] < 0: break                       # open start
        di, dj, _ = _STEPS[int(back[i, b])]
        i, j = i - di, j - dj
        if j < 0: break
        path.append((i, j))
    return np.array(path[::-1])


def align(A: np.ndarray, B: np.ndarray, coarse: int = 10, fine_band_s: int = 20, fps: int = 10,
          open_a: bool = False) -> np.ndarray:
    """Path between feature sequences A and B (frames at `fps`). open_a: B is somewhere inside A."""
    n, m = len(A), len(B)
    if n == 0 or m == 0: return np.zeros((0, 2), int)
    k = coarse
    a = A[:n // k * k].reshape(-1, k, A.shape[1]).mean(1) if n >= 2 * k else A
    b = B[:m // k * k].reshape(-1, k, B.shape[1]).mean(1) if m >= 2 * k else B
    kk_a, kk_b = n / len(a), m / len(b)
    # coarse: full width
    p = banded(a, b, np.full(len(a), (len(b) - 1) / 2), (len(b) + 1) // 2, open_a, skip_cost(a, b) if open_a else 0.0)
    # fine: band around the coarse path (only the part of A the coarse path covers, plus a margin)
    i0, i1 = 0, n
    if open_a:
        i0 = max(0, int(p[0, 0] * kk_a) - fine_band_s * fps)
        i1 = min(n, int((p[-1, 0] + 1) * kk_a) + fine_band_s * fps)
    ci = np.interp(np.arange(i0, i1), p[:, 0] * kk_a + kk_a / 2, p[:, 1] * kk_b + kk_b / 2)
    fine = banded(A[i0:i1], B, ci, fine_band_s * fps, open_a, skip_cost(A, B) if open_a else 0.0)
    fine[:, 0] += i0
    return fine


def map_times(path: np.ndarray, times_b: list[float], fps: int = 10) -> list[float]:
    """Times in B (s) -> matching times in A (s), following the path."""
    if len(path) == 0: return list(times_b)
    j, i = path[:, 1].astype(float), path[:, 0].astype(float)
    order = np.argsort(j, kind="stable")
    return list(np.interp(np.asarray(times_b) * fps, j[order], i[order]) / fps)
