# Synaptic Voice Studio (fork de Chatterbox-TTS-Server)

Fork propio de [devnen/Chatterbox-TTS-Server](https://github.com/devnen/Chatterbox-TTS-Server): servidor TTS con clonación de voz zero-shot (Chatterbox, Resemble AI, MIT), Web UI y API compatible con OpenAI (`/v1/audio/speech`). Es el motor de Synaptic Voice Studio.

## Dónde corre
- **No corre en vps_04.** Se ejecuta en el Mac mini M4, acelerado por MPS, con un venv de Python 3.10 (3.11+ no tiene wheels para torch/ONNX).
- `synaptic-model-manager` lo expone en `voice-studio.synaptic-ai.dev` (túnel `voice-tunnel` + `voice-ui-proxy`) y a Hermes por MCP (`mcp-voice`).
- Instalación, pins tolerados (`protobuf==3.20.3`, `omegaconf==2.3.0`, `setuptools<81`) y operación: `docs/OPERATIONS.md` §11 del repo `synaptic-model-manager`. Ese es el runbook canónico.

## Comandos
```bash
python start.py      # lanzador del upstream: prepara el entorno y arranca (ver README)
python server.py     # servidor directo (lee config.yaml)
```
Los `Dockerfile*` y `docker-compose-*.yml` son variantes GPU del upstream (CUDA, ROCm, RDNA4…) y no se usan en Synaptic. El CI (`docker-build.yml`) las construye en cada PR y solo las publica en GHCR con el push a `main` o un tag. No hay tests.

## Reglas
- Mantén el diff con el upstream pequeño y localizado (UI y presets). Para traer cambios: `git fetch upstream` y merge. No reestructures el proyecto.
- El repo en GitHub es **público** (el resto de Synaptic es privado): nunca commitees voces de referencia privadas, `.env`, credenciales, IPs ni configuración del Mac mini.
- Despliegue: actualizar el checkout del Mac mini según el runbook de model-manager. No hay carril automático.

## Synaptic
- Slug `synaptic-voice-studio` · estado: experimental · port_block 19.
- Contexto: infra → MCP `graphify`; código → `codegraph` (`projectPath=/data/codegraph-worktrees/synaptic-voice-studio`); guía → `/home/alex/projects/_catalog/AGENT-GUIDE.md`.
