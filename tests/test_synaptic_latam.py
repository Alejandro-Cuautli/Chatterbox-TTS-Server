"""Selector del finetune es-MX sin cargar pesos (CPU, CI)."""

import pytest

import synaptic_latam


def test_selector_resolves_to_multilingual():
    engine = pytest.importorskip("engine")
    assert engine.MODEL_SELECTOR_MAP[synaptic_latam.SELECTOR] == "multilingual"


def test_missing_checkpoint_fails_with_the_files_it_needs(tmp_path):
    (tmp_path / "ve.pt").write_bytes(b"")
    with pytest.raises(FileNotFoundError) as err:
        synaptic_latam.load(tmp_path, "cpu")
    msg = str(err.value)
    assert "t3_es_mx_latam.safetensors" in msg and "s3gen_v3.pt" in msg and "ve.pt" not in msg


def test_unconfigured_directory_is_explicit():
    with pytest.raises(FileNotFoundError, match="local_ckpt_dir"):
        synaptic_latam.load("", "cpu")
