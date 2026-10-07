# Operación de voice-studio

Ver instalación y configuración del motor en [README](../README.md). La UI
está en `/` y `/api/model-info` informa estado del modelo; no llamar health a
un endpoint inexistente. La síntesis `/v1/audio/speech` exige un modelo cargado.

CI usa Python 3.12 compatible con los pins PyTorch 2.5.1. El contrato verifica
Compose/documentación; no acredita GPU, credenciales, descarga de modelos ni
síntesis real. Verificar cada imagen nativa antes de merge. `rocm-ml-libraries`
no estaba disponible en la base Strix Halo del run 37632781895; ARM64 no fue
adquirido en cinco intentos. Son bloqueos independientes, no un CI completo verde.

Rollback de estas correcciones: revertir commit por PR. No levantar ni reiniciar
servicios, borrar cache o volúmenes, modificar OpenBao ni cambiar baselines.
