"""Contrato de audio por segmento (segment_finish.py) con señales sintéticas."""

import numpy as np
import pytest

import segment_finish as sf

SPEC = sf.FinishSpec()


def _voice(sr, seconds, amp, freq=220.0, lead=0.02, trail=0.0):
    """Tono con armónicos que empieza y acaba en seco (como un bloque cortado del motor)."""
    t = np.arange(int(seconds * sr)) / sr
    tone = amp * (np.sin(2 * np.pi * freq * t) + 0.5 * np.sin(2 * np.pi * 3 * freq * t))
    return np.concatenate([np.zeros(int(lead * sr)), tone, np.zeros(int(trail * sr))]).astype(np.float32)


def test_lufs_matches_bs1770_reference_sine():
    sr = 48000
    t = np.arange(sr * 3) / sr
    # BS.1770: un seno de 997 Hz a fondo de escala en un canal mide -3,01 LUFS.
    assert sf.integrated_lufs(np.sin(2 * np.pi * 997 * t), sr) == pytest.approx(-3.01, abs=0.05)


def test_segment_contract_from_24k_engine_output():
    out, sr = sf.finish(_voice(24000, 2.0, 0.9, lead=0.02), 24000)
    assert sr == 48000
    zeros_head = round((SPEC.head_s - SPEC.pre_roll_s) * sr)
    zeros_tail = round((SPEC.tail_s - SPEC.post_roll_s) * sr)
    assert not out[:zeros_head].any() and not out[-zeros_tail:].any()
    voice = out[zeros_head:-zeros_tail]
    assert voice[0] == 0.0 and voice[-1] == 0.0
    nz = np.flatnonzero(np.abs(out) > 1e-3)
    assert nz[0] / sr == pytest.approx(SPEC.head_s, abs=0.012)
    assert (len(out) - nz[-1]) / sr == pytest.approx(SPEC.tail_s, abs=0.012)
    # La rampa evita el salto de amplitud del corte en seco.
    assert np.abs(np.diff(voice[: int(SPEC.fade_s * sr)])).max() < 0.05
    assert sf.integrated_lufs(voice, sr) == pytest.approx(SPEC.target_lufs, abs=0.5)
    assert sf.true_peak_db(out) <= SPEC.true_peak_db + 0.05
    assert abs(float(out.mean())) < 1e-3


def test_levels_are_homogeneous_across_segments():
    loud, _ = sf.finish(_voice(24000, 1.5, 0.95, lead=0.1), 24000)
    quiet, _ = sf.finish(_voice(24000, 1.5, 0.08, freq=180.0, lead=0.1), 24000)
    assert sf.integrated_lufs(loud, 48000) == pytest.approx(sf.integrated_lufs(quiet, 48000), abs=0.5)


def test_margins_are_fixed_regardless_of_engine_padding():
    a, sr = sf.finish(_voice(44100, 1.0, 0.5, lead=0.6, trail=0.9), 44100)
    b, _ = sf.finish(_voice(44100, 1.0, 0.5, lead=0.0, trail=0.0), 44100)
    first = lambda x: int(np.flatnonzero(np.abs(x) > 1e-3)[0])
    assert abs(first(a) - first(b)) <= int(0.002 * sr)
    assert first(b) / sr == pytest.approx(SPEC.head_s, abs=0.012)
    # Granularidad de la puerta: tramos de 10 ms (y la cola del paso alto tras un corte en seco).
    assert abs(len(a) - len(b)) <= int(0.025 * sr)


def test_quiet_onset_before_vowel_is_kept():
    sr = 24000
    rng = np.random.default_rng(0)
    consonant = (0.01 * rng.standard_normal(int(0.03 * sr))).astype(np.float32)  # «s» suave, -40 dB
    seg = np.concatenate([np.zeros(int(0.2 * sr), np.float32), consonant, _voice(sr, 1.0, 0.8, lead=0.0)])
    out, osr = sf.finish(seg, sr)
    onset = np.flatnonzero(np.abs(out) > 1e-4)[0] / osr
    # La consonante (30 ms antes de la vocal, bajo la puerta) cae en el pre-roll: no se recorta.
    assert SPEC.head_s - SPEC.pre_roll_s <= onset <= SPEC.head_s - 0.02
    vowel = np.flatnonzero(np.abs(out) > 0.1)[0] / osr
    assert vowel == pytest.approx(SPEC.head_s, abs=0.012)


def test_silence_returns_only_margins():
    out, sr = sf.finish(np.zeros(24000, np.float32), 24000)
    assert sr == 48000 and not out.any()
    assert len(out) == int(SPEC.head_s * sr) + int(SPEC.tail_s * sr)
