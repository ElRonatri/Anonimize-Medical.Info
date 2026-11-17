#!/usr/bin/env bash
# Publica el release vVERSION con los ZIP y SHA256SUMS.txt de la carpeta release/.
# Lo usa .github/workflows/release.yml (job "publish"); necesita gh autenticado (GH_TOKEN).
#
#   VERSION=1.1.0 GITHUB_SHA=<commit> GITHUB_REF=<ref> GITHUB_REPOSITORY=<dueño/repo> \
#     scripts/publish_release.sh release notes.md
#
# Casos:
#   * El release ya está publicado            -> error (no se sobrescribe).
#   * Hay un BORRADOR vVERSION (p. ej. creado
#     en la web)                              -> sube los archivos y lo publica.
#   * El tag existe                           -> debe apuntar a GITHUB_SHA; crea el release.
#   * El tag no existe (ejecución manual)     -> sólo desde main: GitHub crea el tag en GITHUB_SHA.
set -euo pipefail

DIR="${1:?carpeta con los ZIP y SHA256SUMS.txt}"
NOTES="${2:?archivo de notas}"
TAG="v${VERSION:?}"
TITLE="Anonimize Medical ${VERSION}"
FILES=("$DIR"/*.zip "$DIR/SHA256SUMS.txt")

tag_commit() {  # commit al que apunta el tag, o vacío si no existe
  # Si el tag no existe, gh imprime el JSON del error en stdout y termina con error: sólo se
  # acepta la salida de una llamada exitosa que sea un SHA completo.
  local out
  if out="$(gh api "repos/${GITHUB_REPOSITORY:?}/commits/${TAG}" --jq .sha 2>/dev/null)" \
      && [[ "$out" =~ ^[0-9a-f]{40}$ ]]; then
    echo "$out"
  fi
}

check_tag_target() {
  local commit
  commit="$(tag_commit)"
  if [ -n "$commit" ] && [ "$commit" != "${GITHUB_SHA:?}" ]; then
    echo "El tag ${TAG} apunta a ${commit}, no al commit compilado ${GITHUB_SHA}." >&2
    exit 1
  fi
  if [ -z "$commit" ] && [ "${GITHUB_REF:?}" != "refs/heads/main" ]; then
    echo "El tag ${TAG} no existe: sólo se crea al publicar desde main (ref actual: ${GITHUB_REF})." >&2
    exit 1
  fi
}

if draft="$(gh release view "$TAG" --json isDraft --jq .isDraft 2>/dev/null)"; then
  if [ "$draft" != "true" ]; then
    echo "El release ${TAG} ya está publicado; no se modifica." >&2
    exit 1
  fi
  check_tag_target
  echo "Completando el borrador ${TAG}"
  gh release upload "$TAG" "${FILES[@]}" --clobber
  gh release edit "$TAG" --title "$TITLE" --notes-file "$NOTES" --target "$GITHUB_SHA" --draft=false
  exit 0
fi

check_tag_target
if [ -n "$(tag_commit)" ]; then
  echo "Publicando ${TAG} (tag existente)"
  gh release create "$TAG" "${FILES[@]}" --verify-tag --title "$TITLE" --notes-file "$NOTES"
else
  echo "Publicando ${TAG} (se crea el tag en ${GITHUB_SHA})"
  gh release create "$TAG" "${FILES[@]}" --target "$GITHUB_SHA" --title "$TITLE" --notes-file "$NOTES"
fi
