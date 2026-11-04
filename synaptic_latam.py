"""Finetune es-MX/es-419 de Chatterbox Multilingual (Synaptic).

`ResembleAI/Chatterbox-Multilingual-es-mx-latam` (MIT, V3 Single Language Pack) trae
su propio T3 (`t3_es_mx_latam.safetensors`) y el vocoder `s3gen_v3.pt`; el codificador
de voz (`ve.pt`) y el tokenizador son los del repo base. `from_pretrained` del paquete
solo descarga `ResembleAI/chatterbox`, así que se carga desde un directorio local que
instala y aprueba el Model Manager (nada de descargas desde aquí).

Se elige con `model.repo_id: chatterbox-multilingual-latam` y
`model.local_ckpt_dir: <directorio>` en config.yaml.
"""

from __future__ import annotations

from pathlib import Path

SELECTOR = "chatterbox-multilingual-latam"
REQUIRED_FILES = (
    "t3_es_mx_latam.safetensors",
    "s3gen_v3.pt",
    "ve.pt",
    "grapheme_mtl_merged_expanded_v1.json",
)
EXPECTED_MISSING_S3GEN = {"tokenizer._mel_filters", "tokenizer.window"}


def missing_files(ckpt_dir: str | Path) -> list[str]:
    root = Path(ckpt_dir)
    return [name for name in REQUIRED_FILES if not (root / name).is_file()]


def load(ckpt_dir: str | Path, device: str):
    """Devuelve un ChatterboxMultilingualTTS con el T3 y el vocoder es-MX."""
    if not ckpt_dir:
        raise FileNotFoundError(f"{SELECTOR} requiere model.local_ckpt_dir en config.yaml.")
    missing = missing_files(ckpt_dir)
    if missing:
        raise FileNotFoundError(f"{SELECTOR}: faltan {', '.join(missing)} en {ckpt_dir}.")

    import torch
    from chatterbox.models.s3gen import S3Gen
    from chatterbox.models.t3 import T3
    from chatterbox.models.t3.modules.t3_config import T3Config
    from chatterbox.models.tokenizers import MTLTokenizer
    from chatterbox.models.voice_encoder import VoiceEncoder
    from chatterbox.mtl_tts import ChatterboxMultilingualTTS
    from safetensors.torch import load_file

    root = Path(ckpt_dir)
    ve = VoiceEncoder()
    ve.load_state_dict(torch.load(root / "ve.pt", map_location=device, weights_only=True))
    t3 = T3(T3Config.multilingual())
    t3.load_state_dict(load_file(root / "t3_es_mx_latam.safetensors"))
    s3gen = S3Gen()
    result = s3gen.load_state_dict(
        torch.load(root / "s3gen_v3.pt", map_location=device, weights_only=True), strict=False
    )
    # s3gen_v3 no trae dos buffers deterministas que S3Gen calcula al construirse
    # (comprobado en el nodo el 2026-11-04). Cualquier otra diferencia es un fichero
    # equivocado: mejor no arrancar que sintetizar con pesos aleatorios.
    missing = set(result.missing_keys) - EXPECTED_MISSING_S3GEN
    if missing or result.unexpected_keys:
        raise RuntimeError(
            f"s3gen_v3 no encaja con S3Gen: ausentes {sorted(missing)[:5]}, "
            f"inesperadas {result.unexpected_keys[:5]}"
        )
    tokenizer = MTLTokenizer(str(root / "grapheme_mtl_merged_expanded_v1.json"))
    return ChatterboxMultilingualTTS(
        t3.to(device).eval(), s3gen.to(device).eval(), ve.to(device).eval(), tokenizer, device, conds=None
    )
