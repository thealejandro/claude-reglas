#!/bin/bash
# Uso como root: instalar-chrome.sh [usuario-de-prueba]
# Google Chrome del sistema para PDF y QA, con la confianza en Google acotada:
# clave solo para su repo, solo el paquete de Chrome, sin SUID (sandbox por user namespaces
# con el perfil AppArmor de Ubuntu, válido porque la ruta solo la escribe root), parches
# automáticos y políticas sin Gemini, modelo de IA local ni telemetría. Idempotente.
set -euo pipefail
[[ $EUID -eq 0 ]] || { echo "Ejecutar como root" >&2; exit 1; }
PRUEBA=${1:-}
[[ -z $PRUEBA ]] || getent passwd "$PRUEBA" >/dev/null || { echo "No existe el usuario $PRUEBA" >&2; exit 2; }

# Que el cron de Google no reescriba la configuración de apt.
printf 'repo_add_once="false"\nrepo_reenable_on_distupgrade="false"\n' > /etc/default/google-chrome
curl -fsSL https://dl.google.com/linux/linux_signing_key.pub | gpg --dearmor --yes -o /usr/share/keyrings/google-chrome.gpg
rm -f /etc/apt/sources.list.d/google-chrome.list
# Mismo formato que escribe el paquete, para que no lo sustituya.
cat > /etc/apt/sources.list.d/google-chrome.sources <<'SRC'
Types: deb
URIs: https://dl.google.com/linux/chrome-stable/deb/
Suites: stable
Components: main
Architectures: amd64
Signed-By: /usr/share/keyrings/google-chrome.gpg
SRC
# De ese origen solo puede venir google-chrome-stable.
cat > /etc/apt/preferences.d/google-chrome <<'PIN'
Package: *
Pin: origin dl.google.com
Pin-Priority: -1

Package: google-chrome-stable
Pin: origin dl.google.com
Pin-Priority: 500
PIN
# Sin binario SUID; statoverride lo mantiene en cada actualización.
dpkg-statoverride --list /opt/google/chrome/chrome-sandbox >/dev/null 2>&1 \
  || dpkg-statoverride --add root root 0755 /opt/google/chrome/chrome-sandbox
apt-get update -o Dir::Etc::sourcelist=/dev/null -o Dir::Etc::sourceparts=/etc/apt/sources.list.d -o APT::Get::List-Cleanup=0 >/dev/null
apt-get install -y google-chrome-stable
echo 'Unattended-Upgrade::Origins-Pattern { "origin=Google LLC,suite=stable"; };' > /etc/apt/apt.conf.d/52unattended-google-chrome
install -d -m 755 /etc/opt/chrome/policies/managed
cat > /etc/opt/chrome/policies/managed/reglas.json <<'POL'
{
  "GeminiSettings": 1,
  "GenAILocalFoundationalModelSettings": 1,
  "MetricsReportingEnabled": false,
  "BackgroundModeEnabled": false
}
POL
chmod 644 /etc/opt/chrome/policies/managed/reglas.json

echo "== Verificación"
ls -l /opt/google/chrome/chrome-sandbox
apt-cache policy google-chrome-stable | sed -n 1,3p
if aa-status 2>/dev/null | grep -Eq '^[[:space:]]+chrome$'; then echo "Perfil AppArmor chrome cargado"
else echo "AVISO: perfil AppArmor chrome no cargado; sin él Chrome no tiene sandbox"; fi
if [[ -n $PRUEBA ]]; then
  (cd /tmp && sudo -u "$PRUEBA" /usr/bin/google-chrome --headless --dump-dom about:blank 2>/dev/null)
fi
