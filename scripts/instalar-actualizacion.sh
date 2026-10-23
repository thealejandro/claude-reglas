#!/bin/bash
# Uso como root: instalar-actualizacion.sh [--simular] <usuario> [<usuario>...]
# Instala la actualización diaria del plugin reglas para cada usuario (también root).
set -euo pipefail
SIMULAR=0
if [[ ${1:-} == --simular ]]; then SIMULAR=1; shift; fi
[[ $# -ge 1 ]] || { echo "Uso: instalar-actualizacion.sh [--simular] <usuario>..." >&2; exit 2; }
for U in "$@"; do
  [[ $U =~ ^[a-z_][a-z0-9_-]*\$?$ ]] || { echo "Usuario inválido: $U" >&2; exit 2; }
  getent passwd "$U" >/dev/null || { echo "No existe el usuario $U" >&2; exit 2; }
done
ORIGEN="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)/actualizar"
if (( SIMULAR )); then
  echo "SIMULACIÓN: instalar claude-actualizar-reglas root:root 755 en /usr/local/bin"
  echo "Instalar en /etc/systemd/system: claude-actualizar-reglas@.service y .timer"
  for U in "$@"; do echo "systemctl enable --now claude-actualizar-reglas@$U.timer"; done
  cat "$ORIGEN"/claude-actualizar-reglas@.*
  exit 0
fi
[[ $(id -u) == 0 ]] || { echo 'Ejecútalo como root' >&2; exit 1; }
install -o root -g root -m 755 "$ORIGEN/claude-actualizar-reglas" /usr/local/bin/claude-actualizar-reglas
install -o root -g root -m 644 "$ORIGEN/claude-actualizar-reglas@.service" "$ORIGEN/claude-actualizar-reglas@.timer" /etc/systemd/system/
systemctl daemon-reload
for U in "$@"; do
  systemctl enable --now "claude-actualizar-reglas@$U.timer"
  echo "Actualización diaria activada para $U (04:00 hora del servidor; registro en ~$U/.local/state/claude-actualizar-reglas.log)"
done
echo "Para actualizar ya: systemctl start claude-actualizar-reglas@<usuario>.service"
