# Chatterbox TTS Server

FastAPI expone la API de síntesis y la interfaz web del servidor. La aplicación
configura sus motores Chatterbox y carga voces, referencias y modelos desde
los directorios persistentes declarados en Compose. config.yaml selecciona
dispositivo y configuración; los perfiles CPU, CUDA y otros runtimes del repo
se conservan. CI usa CPU y Python3.10, versión requerida por README y por las
ruedas fijadas de Torch/torchvision/torchaudio.

Los secretos de descarga proceden de OpenBao; .env.example solo documenta
los nombres. CI no requiere credenciales reales ni proveedores externos.
Voces, reference_audio, outputs y hf_cache se conservan al actualizar.
