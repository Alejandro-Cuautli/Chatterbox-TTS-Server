"""Acabado por segmento de Synaptic: el contrato de audio que la cola de voz entrega al render.

Cada respuesta de /tts es un segmento (una escena) que el montaje une con otros.
Para que esas uniones no tengan clics, cortes ni saltos de nivel, el segmento sale:

- mono, PCM, `target_sr` Hz (48 kHz por defecto, la frecuencia del máster AAC);
- con la primera energía de voz a `head_s` del inicio y la última a `tail_s` del
  final (los `pre_roll_s`/`post_roll_s` contiguos a la voz son el fondo original del
  motor, casi silencio; el resto del margen es silencio digital exacto; las pausas
  internas se conservan);
- con rampas de `fade_s` en los bordes de la voz: primera y última muestra = 0;
- sin DC y con paso alto a `highpass_hz`;
- a `target_lufs` integrados (ITU-R BS.1770-4, puerta absoluta y relativa) con el
  pico verdadero (sobremuestreo ×4) limitado a `true_peak_db` por ganancia, sin
  compresión.

Desactivado por defecto (`audio_processing.synaptic_segment_finish`), así el
comportamiento del upstream no cambia salvo en el nodo de Synaptic.
"""

from __future__ import annotations

from dataclasses import dataclass
from math import gcd

import numpy as np
from scipy.signal import butter, lfilter, resample_poly, sosfilt


@dataclass(frozen=True)
class FinishSpec:
    target_sr: int = 48000
    head_s: float = 0.150
    tail_s: float = 0.250
    fade_s: float = 0.008
    highpass_hz: float = 70.0
    target_lufs: float = -18.0
    true_peak_db: float = -1.5
    # Detección de voz por islas (regla acordada con montaje, F4, el 2026-11-04): tramos de
    # 10 ms por encima de max(p95 - 30 dB, suelo + 10 dB, -62 dBFS), unidos si el hueco es
    # < 300 ms; una isla es voz solo si su pico llega a p95 - 18 dB. Un umbral fijo dejaba
    # pasar el ruido que Chatterbox genera tras la última palabra (hasta -39 dBFS durante
    # 1,3 s en job_054575ba S02, -55 dB ~0,7 s en otros): parte del ruido en las uniones.
    # Margen extra alrededor de la voz para no comerse consonantes de baja energía (la «t»
    # o la «s» iniciales) ni la caída natural de la última sílaba.
    gate_below_p95_db: float = 30.0
    gate_above_floor_db: float = 10.0
    gate_abs_db: float = -62.0
    island_join_s: float = 0.300
    island_peak_below_p95_db: float = 18.0
    pre_roll_s: float = 0.040
    post_roll_s: float = 0.080


def resample(audio: np.ndarray, sr: int, target_sr: int) -> np.ndarray:
    if sr == target_sr:
        return audio.astype(np.float32, copy=False)
    g = gcd(int(sr), int(target_sr))
    return resample_poly(audio.astype(np.float64), target_sr // g, sr // g).astype(np.float32)


def _k_weighting_48k(x: np.ndarray) -> np.ndarray:
    """Filtro K de BS.1770-4 (coeficientes publicados para 48 kHz)."""
    b1 = [1.53512485958697, -2.69169618940638, 1.19839281085285]
    a1 = [1.0, -1.69065929318241, 0.73248077421585]
    b2 = [1.0, -2.0, 1.0]
    a2 = [1.0, -1.99004745483398, 0.99007225036621]
    return lfilter(b2, a2, lfilter(b1, a1, x))


def integrated_lufs(audio: np.ndarray, sr: int) -> float:
    """Sonoridad integrada (mono) según BS.1770-4. -inf si no hay nada por encima de la puerta."""
    x = resample(audio, sr, 48000).astype(np.float64)
    y = _k_weighting_48k(x)
    block, hop = 19200, 4800  # 400 ms con 75 % de solape a 48 kHz
    if len(y) < block:
        y = np.pad(y, (0, block - len(y)))
    starts = range(0, len(y) - block + 1, hop)
    z = np.array([np.mean(y[s:s + block] ** 2) for s in starts])
    loud = -0.691 + 10 * np.log10(np.maximum(z, 1e-12))
    z = z[loud > -70.0]
    if not len(z):
        return float("-inf")
    rel = -0.691 + 10 * np.log10(np.mean(z)) - 10.0
    z = z[(-0.691 + 10 * np.log10(np.maximum(z, 1e-12))) > rel]
    return float(-0.691 + 10 * np.log10(np.mean(z)))


def true_peak_db(audio: np.ndarray) -> float:
    up = resample_poly(audio.astype(np.float64), 4, 1)
    return float(20 * np.log10(max(np.abs(up).max(initial=0.0), 1e-9)))


def speech_bounds(audio: np.ndarray, sr: int, spec: FinishSpec) -> tuple[int, int] | None:
    """[inicio, fin) en muestras de las islas de voz (ver FinishSpec). None si es silencio."""
    hop = max(1, int(0.010 * sr))
    n = len(audio) // hop
    if n == 0:
        return None
    frames = audio[: n * hop].reshape(n, hop).astype(np.float64)
    rms_db = 10 * np.log10(np.maximum(np.mean(frames ** 2, axis=1), 1e-12))
    p95 = float(np.percentile(rms_db, 95))
    floor = float(np.percentile(rms_db, 10))
    # Sin silencio en el segmento el p10 es la propia voz: el término del suelo no puede
    # pasar de p95 - 20 dB o la puerta lo cerraría entero.
    floor_term = min(floor + spec.gate_above_floor_db, p95 - 20.0)
    thr = max(p95 - spec.gate_below_p95_db, floor_term, spec.gate_abs_db)
    active = np.flatnonzero(rms_db > thr)
    if not len(active):
        return None
    join = max(1, round(spec.island_join_s / 0.010))
    cuts = np.flatnonzero(np.diff(active) > join)
    islands = np.split(active, cuts + 1)
    voiced = [isl for isl in islands if rms_db[isl].max() >= p95 - spec.island_peak_below_p95_db]
    if not voiced:
        return None
    return int(voiced[0][0] * hop), int((voiced[-1][-1] + 1) * hop)


def finish(audio: np.ndarray, sr: int, spec: FinishSpec | None = None) -> tuple[np.ndarray, int]:
    """Aplica el contrato a un segmento mono float y devuelve (audio float32, target_sr)."""
    spec = spec or FinishSpec()
    x = np.asarray(audio, dtype=np.float32).reshape(-1)
    x = resample(x, sr, spec.target_sr)
    sr = spec.target_sr
    if spec.highpass_hz:
        # Segundo orden: quita DC y retumbos sin tocar la fundamental de la voz.
        x = sosfilt(butter(2, spec.highpass_hz, btype="highpass", fs=sr, output="sos"), x).astype(np.float32)
    bounds = speech_bounds(x, sr, spec)
    if bounds is None:
        return np.zeros(round(spec.head_s * sr) + round(spec.tail_s * sr), dtype=np.float32), sr
    # El pre/post-roll forma parte del margen: la primera energía de voz cae en head_s
    # y la última a tail_s del final, con independencia del relleno que traiga el motor.
    onset, offset = bounds
    head_n, tail_n = round(spec.head_s * sr), round(spec.tail_s * sr)
    start = max(0, onset - min(round(spec.pre_roll_s * sr), head_n))
    end = min(len(x), offset + min(round(spec.post_roll_s * sr), tail_n))
    head = np.zeros(head_n - (onset - start), dtype=np.float32)
    tail = np.zeros(tail_n - (end - offset), dtype=np.float32)
    voice = x[start:end].copy()
    nf = min(int(spec.fade_s * sr), len(voice) // 2)
    if nf > 0:
        ramp = np.sin(np.linspace(0.0, np.pi / 2, nf, dtype=np.float32)) ** 2
        voice[:nf] *= ramp
        voice[-nf:] *= ramp[::-1]
    loud = integrated_lufs(voice, sr)
    if np.isfinite(loud):
        voice *= np.float32(10 ** ((spec.target_lufs - loud) / 20))
    peak = true_peak_db(voice)
    if peak > spec.true_peak_db:
        voice *= np.float32(10 ** ((spec.true_peak_db - peak) / 20))
    # Rampas al cero exacto: en PCM 16 bit la primera y la última muestra de voz ya valen 0.
    voice[0] = 0.0
    voice[-1] = 0.0
    return np.concatenate([head, voice, tail]).astype(np.float32), sr
