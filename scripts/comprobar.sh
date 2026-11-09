#!/bin/bash
# Comprobación completa del plugin: la misma en local y en CI.
# uso: scripts/comprobar.sh   (desde cualquier carpeta)
set -euo pipefail
cd "$(dirname "$0")/.."
fallos=0
paso() { printf '\n== %s\n' "$1"; }
falla() { echo "FALLA: $1" >&2; fallos=$((fallos + 1)); }

paso "JSON del plugin, marketplace y hooks"
for f in .claude-plugin/plugin.json .claude-plugin/marketplace.json hooks/hooks.json; do
  python3 -m json.tool "$f" >/dev/null || falla "$f no es JSON válido"
done

paso "Frontmatter de las skills (name y description)"
for s in skills/*/SKILL.md; do
  head -1 "$s" | grep -qx -- '---' || { falla "$s sin frontmatter"; continue; }
  n=$(awk '/^---$/{c++; next} c==1 && /^name:/{print $2}' "$s")
  [[ $n == "$(basename "$(dirname "$s")")" ]] || falla "$s: name '$n' no coincide con su carpeta"
  awk '/^---$/{c++; next} c==1' "$s" | grep -q '^description: .\{20,\}' || falla "$s sin description"
done

paso "Sin rutas personales en lo publicado (el repo es público)"
# Solo lo que git versionaría (tracked + nuevos no ignorados); sin binarios ni cachés.
if git ls-files -z -co --exclude-standard | grep -zv '^scripts/comprobar.sh$' \
   | xargs -0 grep -nIE '/home/[a-z]+/|~/(Work|Streaming)\b' | grep -v '/home/dev/'; then
  falla "rutas personales: usa nombres de repo o rutas genéricas"
fi

paso "reglas.py y ajustes.py en un HOME temporal"
H=$(mktemp -d); trap 'rm -rf "$H"' EXIT
python3 -I scripts/reglas.py >/dev/null || falla "reglas.py"
for a in "" "" "--si-hace-falta"; do
  HOME="$H" python3 -I scripts/ajustes.py $a >/dev/null || falla "ajustes.py $a"
done

paso "Tests"
for t in tests/test_*.py; do
  if python3 -I "$t" >/dev/null 2>&1; then echo "ok $t"; else falla "$t"; python3 -I "$t" 2>&1 | tail -15; fi
done

paso "claude plugin validate"
if command -v claude >/dev/null; then
  claude plugin validate . || falla "claude plugin validate"
else
  echo "claude no está instalado: se omite (en CI sí se instala)"
fi

echo
if ((fallos)); then echo "$fallos fallo(s)"; exit 1; fi
echo "Todo OK"
