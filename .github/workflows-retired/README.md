# Workflows retirados (migración vps_04 → vps_06, Bloque 8)

GitHub no ejecuta nada fuera de `.github/workflows/`. Estos workflows solo podían correr en runners
hospedados por GitHub (Windows, macOS o imágenes GPU), prohibidos por la regla de CI de la fábrica:
todo CI corre en runners self-hosted efímeros X64 de vps_05, sin fallback hospedado. Para reactivarlos
hace falta un runner self-hosted de esa plataforma; entonces se devuelven a `.github/workflows/`.

- `docker-build.yml`
