"""Speech features (MFCC) in plain numpy, for matching two recitations of the same text."""
import subprocess

import numpy as np

RATE = 8000
FPS = 10                       # feature frames per second used for matching
_WIN = 256                     # 32 ms window at 8 kHz
_HOP = RATE // 100             # 10 ms analysis hop, averaged down to FPS
N_MELS, N_MFCC = 26, 13


def decode(src: str, ffmpeg: str = "ffmpeg", cancel=lambda: False) -> np.ndarray:
    """Mono 8 kHz int16 samples of a file or URL."""
    p = subprocess.Popen([ffmpeg, "-v", "error", "-nostdin", "-i", src, "-vn", "-ac", "1", "-ar", str(RATE), "-f", "s16le", "-"],
                         stdout=subprocess.PIPE, stderr=subprocess.PIPE)
    assert p.stdout is not None
    chunks = []
    while True:
        b = p.stdout.read(1 << 20)
        if not b: break
        chunks.append(b)
        if cancel():
            p.kill(); p.wait(); raise InterruptedError("cancelled")
    err = p.stderr.read().decode(errors="ignore") if p.stderr else ""
    if p.wait() != 0 and not chunks:
        raise RuntimeError(err.strip().splitlines()[-1] if err.strip() else "could not read the audio")
    return np.frombuffer(b"".join(chunks), np.int16)


def _mel_bank() -> np.ndarray:
    def mel(f): return 2595 * np.log10(1 + f / 700)
    def hz(m): return 700 * (10 ** (m / 2595) - 1)
    pts = hz(np.linspace(mel(60), mel(RATE / 2 - 200), N_MELS + 2))
    bins = np.floor((_WIN + 1) * pts / RATE).astype(int)
    fb = np.zeros((N_MELS, _WIN // 2 + 1))
    for i in range(N_MELS):
        a, b, c = bins[i], bins[i + 1], bins[i + 2]
        if b > a: fb[i, a:b] = (np.arange(a, b) - a) / (b - a)
        if c > b: fb[i, b:c] = (c - np.arange(b, c)) / (c - b)
    return fb


_FB = _mel_bank()
_DCT = np.cos(np.pi / N_MELS * (np.arange(N_MELS)[None, :] + 0.5) * np.arange(N_MFCC)[:, None])
_WINDOW = np.hamming(_WIN).astype(np.float32)


def mfcc(x: np.ndarray) -> np.ndarray:
    """[frames, N_MFCC-1] at FPS frames/s, mean/variance normalised (speaker differences shrink)."""
    x = x.astype(np.float32) / 32768
    n = (len(x) - _WIN) // _HOP + 1
    if n <= 0: return np.zeros((0, N_MFCC - 1), np.float32)
    out = []
    step = 20000                                      # frames per block, keeps memory flat
    for s in range(0, n, step):
        idx = np.arange(s, min(n, s + step))[:, None] * _HOP + np.arange(_WIN)[None, :]
        spec = np.abs(np.fft.rfft(x[idx] * _WINDOW, axis=1)) ** 2
        logmel = np.log(spec @ _FB.T + 1e-8)
        out.append(logmel @ _DCT.T)
    c = np.concatenate(out)[:, 1:]                    # drop c0 (loudness)
    k = 100 // FPS
    m = len(c) // k
    c = c[:m * k].reshape(m, k, -1).mean(1)
    c = (c - c.mean(0)) / (c.std(0) + 1e-6)
    return c.astype(np.float32)
