#!/usr/bin/env bash
# Sincroniza las skills canonicas (skills/<nombre>/SKILL.md) hacia las rutas que los distintos
# agentes descubren. Mantiene las copias identicas a la fuente.
#
# Rutas destino:
#   - DeepSeek Harness (proyecto, versionable): .dsh/skills, .agents/skills
#   - DeepSeek Harness (usuario, global):       ~/.dsh/skills, ~/.agents/skills
#   - Claude Code (proyecto, versionable):      .claude/skills
#   - Claude Code (usuario, global):            ~/.claude/skills
#
# Uso:  bash scripts/copiar_skills.sh
set -euo pipefail

RAIZ="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
FUENTE="$RAIZ/skills"
NOMBRES=(ideacion-video generacion-video)

DESTINOS=(
  "$RAIZ/.dsh/skills"
  "$RAIZ/.agents/skills"
  "$HOME/.dsh/skills"
  "$HOME/.agents/skills"
  "$RAIZ/.claude/skills"
  "$HOME/.claude/skills"
)

for n in "${NOMBRES[@]}"; do
  src="$FUENTE/$n/SKILL.md"
  if [[ ! -f "$src" ]]; then
    echo "[copiar_skills] Falta la fuente: $src" >&2
    exit 1
  fi
  for d in "${DESTINOS[@]}"; do
    mkdir -p "$d/$n"
    cp "$src" "$d/$n/SKILL.md"
    echo "[copiar_skills] -> $d/$n/SKILL.md"
  done
done

echo "[copiar_skills] OK."
