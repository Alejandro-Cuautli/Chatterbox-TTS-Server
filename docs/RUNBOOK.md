# Operación y validación

Usar Python3.10 y las dependencias fijadas en requirements.txt para la lane CPU,
como exige README. CI crea el venv con uv sin actualizar Python del host:

```sh
uv venv --python 3.10 --seed .venv-ci
. .venv-ci/bin/activate
python -m pip install -r requirements.txt
python -m pip install ruff pytest
ruff check .
pytest -q
bash .hermes/contract-check.sh
```

El stack gestionado usa la release, overrides y digests del inventario de
migración; no arrancar el Compose NVIDIA por defecto en un host sin GPU.
Para desarrollo CPU, consultar docker-compose-cpu.yml y Dockerfile.cpu.
Los perfiles GPU existentes se conservan y no se declaran validados por CI CPU.
HF_TOKEN se materializa mediante OpenBao; nunca se imprime ni se incorpora
al repo o a las imágenes. Conservar voces, referencias, salidas y modelos.

Rollback: volver al digest/release previo validado conservando los volúmenes;
no ejecutar down -v ni reiniciar otros servicios. Durante la migración,
cualquier activación de consumidores sigue el corte coordinado.
