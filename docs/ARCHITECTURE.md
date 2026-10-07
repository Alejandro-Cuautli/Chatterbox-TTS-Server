# Arquitectura de voice-studio

`server.py` expone FastAPI, la UI raíz, `/api/model-info`, `/v1/audio/voices`
y `/v1/audio/speech`. La síntesis usa los módulos del motor Chatterbox y audio.
Compose monta configuración, voces, referencias, salidas y un cache de modelos.
Las imágenes Nvidia, CUDA 12.8, CUDA 13 ARM64, ROCm, Strix Halo y CPU conservan
sus dependencias específicas; no se sustituye una variante por otra para verde.
El Docker image workflow serializa la matriz (`max-parallel: 1`) y usa runners
nativos ARM64 o amd64 rootless según la imagen.
