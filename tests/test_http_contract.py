"""CPU HTTP validation without starting the model-loading lifespan."""

import pytest
from fastapi.testclient import TestClient

from models import CustomTTSRequest
from server import app


@pytest.fixture
def client():
    # Context-manager entry would start model downloads; these tests cover HTTP
    # validation and the published upload schema, before inference is invoked.
    return TestClient(app)


@pytest.mark.parametrize("payload", [
    {"text": ""},
    {"text": "Hola", "voice_mode": "unsupported"},
    {"text": "Hola", "output_format": "flac"},
    {"text": "Hola", "chunk_size": 20},
])
def test_invalid_synthesis_is_rejected_before_inference(client, payload):
    response = client.post("/tts", json=payload)
    assert response.status_code == 422
    assert response.json()["detail"]


def test_clone_streaming_payload_preserves_multilingual_input():
    request = CustomTTSRequest.model_validate_json(
        '{"text":"Hola, voz: español y 日本語", "voice_mode":"clone", '
        '"reference_audio_filename":"reference.wav", "stream":true}'
    )
    restored = CustomTTSRequest.model_validate_json(request.model_dump_json())
    assert restored.text == "Hola, voz: español y 日本語"
    assert restored.reference_audio_filename == "reference.wav"
    assert restored.voice_mode == "clone"
    assert restored.stream is True


@pytest.mark.parametrize("route", ["/upload_reference", "/upload_predefined_voice"])
def test_upload_contract_requires_binary_file_array(client, route):
    response = client.get("/openapi.json")
    assert response.status_code == 200
    spec = response.json()
    body = spec["paths"][route]["post"]["requestBody"]
    assert body["required"] is True
    ref = body["content"]["multipart/form-data"]["schema"]["$ref"].split("/")[-1]
    schema = spec["components"]["schemas"][ref]
    assert "files" in schema["required"]
    assert schema["properties"]["files"]["type"] == "array"
    assert schema["properties"]["files"]["items"]["format"] == "binary"
