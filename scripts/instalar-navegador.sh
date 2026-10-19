#!/bin/bash
# Uso (como root, una vez por servidor Ubuntu 24.04): instalar-navegador.sh [usuario]
# Deja un navegador compartido para QA de todos los agentes del usuario (dev por defecto):
# librerías de Chromium, pantalla virtual xvfb, fuentes, Chromium de Playwright y chrome-devtools-mcp.
set -eu
U="${1:-dev}"
[[ $(id -u) -eq 0 ]] || { echo "Ejecútalo como root" >&2; exit 1; }
apt-get update
apt-get install -y libatk1.0-0t64 libatk-bridge2.0-0t64 libcups2t64 libasound2t64 libgbm1 libcairo2 \
  libpango-1.0-0 libxcomposite1 libxdamage1 libxfixes3 libxrandr2 libatspi2.0-0t64 \
  xvfb fonts-liberation fonts-noto-color-emoji
# Como el usuario, con un script por stdin: con sudo -i las variables de un comando en línea pueden expandirse mal.
sudo -u "$U" -i bash <<'COMO_USUARIO'
set -eu
ls -d ~/.cache/ms-playwright/chromium-*/ >/dev/null 2>&1 || npx -y playwright install chromium
command -v chrome-devtools-mcp >/dev/null || npm i -g --prefix ~/.local chrome-devtools-mcp
rm -f ~/.claude/.reglas-ajustes   # para que el plugin registre el navegador en la próxima sesión
echo "Navegador listo para $(id -un)"
COMO_USUARIO
