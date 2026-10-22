#!/bin/bash
# Uso como root: instalar-servidor.sh [--simular] <usuario> <nombre-equipo>
set -euo pipefail
SIMULAR=0
if [[ ${1:-} == --simular ]]; then SIMULAR=1; shift; fi
[[ $# == 2 ]] || { echo "Uso: instalar-servidor.sh [--simular] <usuario> <nombre-equipo>" >&2; exit 2; }
U=$1; EQUIPO=$2
[[ $U =~ ^[a-z_][a-z0-9_-]*\$?$ && $EQUIPO =~ ^[A-Za-z0-9][A-Za-z0-9_.-]*$ ]] || { echo 'Usuario o nombre de equipo inválido' >&2; exit 2; }
REGISTRO=$(getent passwd "$U") || { echo "No existe el usuario $U" >&2; exit 2; }
IFS=: read -r _ _ UID_USUARIO GID_USUARIO _ CASA _ <<< "$REGISTRO"
[[ $CASA == /* && $UID_USUARIO != 0 ]] || { echo 'Se requiere un usuario no root con HOME absoluto' >&2; exit 2; }
RAIZ=$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)
# PATH común en instalaciones del CLI; conserva también el PATH de login del usuario.
RUTA="$CASA/.local/bin:$CASA/.npm-global/bin:/usr/local/bin:/usr/bin:/bin"
if (( ! SIMULAR )); then
  [[ $(id -u) == 0 ]] || { echo 'Ejecútalo como root' >&2; exit 1; }
  RUTA_LOGIN=$(sudo -u "$U" -i bash <<'COMO_USUARIO'
set -eu
command -v claude >/dev/null
for herramienta in tmux python3 curl flock; do command -v "$herramienta" >/dev/null; done
printf '%s' "$PATH"
COMO_USUARIO
)
  RUTA="$RUTA:$RUTA_LOGIN"
fi
TEMPORAL=$(mktemp -d)
trap 'rm -rf -- "$TEMPORAL"' EXIT
python3 - "$RAIZ/servidor" "$TEMPORAL" "$EQUIPO" "$RUTA" <<'PY'
import pathlib, sys
origen, destino, equipo, ruta = sys.argv[1:]
# Escape de Environment= y de especificadores systemd (también en PATH).
ruta = ruta.replace('\\', '\\\\').replace('"', '\\"').replace('%', '%%')
if '\n' in ruta or '\r' in ruta:
    raise SystemExit('PATH inválido')
for plantilla in pathlib.Path(origen).glob('*.service'):
    (pathlib.Path(destino) / plantilla.name).write_text(plantilla.read_text().replace('@EQUIPO@', equipo).replace('@PATH@', ruta))
for plantilla in pathlib.Path(origen).glob('*.timer'):
    (pathlib.Path(destino) / plantilla.name).write_text(plantilla.read_text())
PY
if (( SIMULAR )); then
  echo "SIMULACIÓN: instalar scripts root:root 755 en /usr/local/bin"
  echo "loginctl enable-linger $U"
  echo "Instalar unidades en $CASA/.config/systemd/user/; respaldar cambios en .bak únicos"
  echo "Crear $CASA/.config/claude-arranque/sesiones.conf vacío solo si no existe"
  echo "sudo -u $U -i bash < script (por stdin)"
  echo 'systemctl --user daemon-reload'
  echo 'systemctl --user enable --now claude-rc.service claude-sesiones.service claude-guardar.service claude-guardar-periodico.timer'
  cat "$TEMPORAL"/*
  exit 0
fi
for SCRIPT in claude-arranque claude-guardar-abiertas claude-nueva-sesion; do
  install -o root -g root -m 755 "$RAIZ/servidor/$SCRIPT" "/usr/local/bin/$SCRIPT"
done
for CARPETA in "$CASA/work" "$CASA/.config" "$CASA/.config/systemd" "$CASA/.config/systemd/user" "$CASA/.config/claude-arranque"; do
  if [[ ! -d $CARPETA ]]; then install -d -o "$UID_USUARIO" -g "$GID_USUARIO" -m 755 "$CARPETA"; fi
done
for UNIDAD in "$TEMPORAL"/*; do
  DESTINO="$CASA/.config/systemd/user/${UNIDAD##*/}"
  if [[ -e $DESTINO ]] && ! cmp -s "$UNIDAD" "$DESTINO"; then
    COPIA=$(mktemp "$DESTINO.bak.XXXXXX")
    cp -p -- "$DESTINO" "$COPIA"
    echo "Aviso: unidad diferente; copia conservada en $COPIA" >&2
  fi
  if [[ ! -e $DESTINO ]] || ! cmp -s "$UNIDAD" "$DESTINO"; then
    install -o "$UID_USUARIO" -g "$GID_USUARIO" -m 644 "$UNIDAD" "$DESTINO"
  fi
done
# Docker sin root: las sesiones necesitan su socket (drop-in aparte, no se pisa al reinstalar).
if [[ -e "$CASA/.config/systemd/user/docker.service" ]]; then
  for UNIDAD in claude-rc claude-sesiones claude-guardar-periodico; do
    install -d -o "$UID_USUARIO" -g "$GID_USUARIO" -m 755 "$CASA/.config/systemd/user/$UNIDAD.service.d"
    printf '[Service]\nEnvironment=DOCKER_HOST=unix:///run/user/%s/docker.sock\n' "$UID_USUARIO" > "$CASA/.config/systemd/user/$UNIDAD.service.d/docker.conf"
    chown "$UID_USUARIO:$GID_USUARIO" "$CASA/.config/systemd/user/$UNIDAD.service.d/docker.conf"
  done
fi
CONF="$CASA/.config/claude-arranque/sesiones.conf"
if [[ ! -e $CONF ]]; then install -o "$UID_USUARIO" -g "$GID_USUARIO" -m 600 /dev/null "$CONF"; fi
loginctl enable-linger "$U"
sudo -u "$U" -i bash <<'COMO_USUARIO'
set -eu
export XDG_RUNTIME_DIR="/run/user/$(id -u)"
export DBUS_SESSION_BUS_ADDRESS="unix:path=$XDG_RUNTIME_DIR/bus"
systemctl --user daemon-reload
systemctl --user enable --now claude-rc.service claude-sesiones.service claude-guardar.service claude-guardar-periodico.timer
COMO_USUARIO
echo "Módulo de servidor instalado para $U ($EQUIPO)"
# La confianza de una carpeta cubre sus subcarpetas; la del home nunca se guarda.
echo "Último paso, una sola vez como $U: cd ~/work && claude, acepta la carpeta y sal con /exit."
echo "Así las sesiones dentro de ~/work arrancan solas tras un reinicio sin pedir confianza."
