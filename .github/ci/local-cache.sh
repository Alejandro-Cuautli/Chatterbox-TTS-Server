#!/usr/bin/env bash
# Caché en el disco del runner (estándar «CI de la fábrica», synaptic-catalog
# ci/ESTANDAR-CI-FABRICA.md §Caché). Patrón del piloto: incu-bot ops/ci/local-cache.sh.
#
# Por qué no actions/cache: sube a GitHub (10 GB por repo, ida y vuelta por red) y el
# runner self-hosted ya tiene un disco que sobrevive entre jobs.
#
# Dónde: $HERMES_CI_CACHE_ROOT si el runner lo define (las plazas de un host comparten
# /var/cache/hermes-ci desde su .env, así que un job arranca caliente caiga donde caiga);
# si no, el $RUNNER_TOOL_CACHE de la instancia. En un runner efímero (JIT) sin
# HERMES_CI_CACHE_ROOT no hay caché que valga: cada job arranca en frío y no pasa nada.
#
# Es un acelerador, nunca una fuente de verdad: un fallo, una entrada corrupta o un disco
# borrado solo hacen el job más lento. Ningún subcomando falla el job por la caché.
#
#   local-cache.sh key <toolchain> <files...>   -> clave (toolchain + uname -m + ficheros)
#   local-cache.sh restore-modules <dir> <key>  -> <dir>/node_modules por hardlink; exit 1 si no hay
#   local-cache.sh save-modules <dir> <key>     -> guarda <dir>/node_modules bajo <key>
#   local-cache.sh dir <name>                   -> imprime (y crea) un directorio persistente
#                                                  (p. ej. PIP_CACHE_DIR, UV_CACHE_DIR, npm cache)
set -euo pipefail

base="${HERMES_CI_CACHE_ROOT:-}"
if [ -z "$base" ] || ! { mkdir -p "$base" 2>/dev/null && [ -w "$base" ]; }; then
  base="${RUNNER_TOOL_CACHE:?RUNNER_TOOL_CACHE sin definir: no es un runner de Actions}"
fi
# Un directorio por repo: dos repos con el mismo lockfile no comparten node_modules
# por accidente, y borrar la caché de un repo no toca la de otro.
root="$base/hermes-ci/${GITHUB_REPOSITORY:-local}"
mkdir -p "$root"
lock() { exec 9>"$root/.lock"; flock "$@" 9; }
# "." daría una entrada oculta (".-<key>"), invisible para los globs.
slug() { if [ "$1" = . ]; then echo root; else echo "$1" | tr '/' '_'; fi; }

cmd=${1:?uso: local-cache.sh <key|restore-modules|save-modules|dir> ...}
shift

case "$cmd" in
  key)
    toolchain=$1; shift
    { echo "$toolchain"; uname -m; sha256sum "$@" 2>/dev/null || true; } | sha256sum | cut -c1-16
    ;;

  restore-modules)
    dir=$1 key=$2
    entry="$root/modules/$(slug "$dir")-$key"
    lock -s
    [ -f "$entry/.complete" ] || { echo "caché de node_modules vacía para $dir ($key)"; exit 1; }
    rm -rf "$dir/node_modules"
    # Hardlinks: instantáneo y seguro porque npm sustituye ficheros en vez de editarlos,
    # y un lockfile nuevo es una clave nueva. node_modules/.cache nunca se guarda.
    cp -al "$entry/node_modules" "$dir/node_modules"
    echo "node_modules de $dir restaurado desde la caché del runner ($key)"
    ;;

  save-modules)
    dir=$1 key=$2
    [ -d "$dir/node_modules" ] || exit 0
    prefix="$root/modules/$(slug "$dir")-"
    entry="$prefix$key"
    [ -f "$entry/.complete" ] && exit 0
    mkdir -p "$root/modules"
    tmp=$(mktemp -d "$root/modules/.tmp.XXXXXX")
    cp -al "$dir/node_modules" "$tmp/node_modules"
    rm -rf "$tmp/node_modules/.cache"
    touch "$tmp/.complete"
    lock -x
    if [ -f "$entry/.complete" ]; then rm -rf "$tmp"; exit 0; fi
    rm -rf "$entry"
    mv "$tmp" "$entry"
    # Dos lockfiles por árbol como mucho: el de main y el de la PR que lo cambia.
    ls -1dt "$prefix"* 2>/dev/null | tail -n +3 | xargs -r rm -rf
    echo "node_modules de $dir guardado en la caché del runner ($key)"
    ;;

  dir)
    mkdir -p "$root/dirs/$1"
    echo "$root/dirs/$1"
    ;;

  *)
    echo "subcomando desconocido: $cmd" >&2
    exit 2
    ;;
esac
