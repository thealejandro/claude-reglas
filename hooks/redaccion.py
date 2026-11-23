"""Reglas de detección compartidas por anti-filtraciones.py e ideas-captura.py (solo stdlib).

SECRETOS: credenciales y datos reales; se bloquean siempre.
PRIVADOS: hosts, IPs, usuarios y rutas de servidores; se bloquean hacia repos públicos.
"""
import os
import re

CONTENT_RULES = (
    ("clave privada", re.compile(r"\bBEGIN [A-Z0-9 ]*PRIVATE KEY\b"), 0),
    ("token de GitHub", re.compile(r"(?<![A-Za-z0-9_])(?:ghp_|gho_)[A-Za-z0-9]{8,}(?![A-Za-z0-9])"), 0),
    ("token de GitHub", re.compile(r"(?<![A-Za-z0-9_])github_pat_[A-Za-z0-9_]{8,}(?![A-Za-z0-9_])"), 0),
    ("clave de AWS", re.compile(r"(?<![A-Z0-9])AKIA[A-Z0-9]{16}(?![A-Z0-9])"), 0),
    ("token de Slack", re.compile(r"(?<![A-Za-z0-9])xox[a-z]-[A-Za-z0-9-]{8,}(?![A-Za-z0-9-])"), 0),
    ("clave de Stripe", re.compile(r"(?<![A-Za-z0-9_])sk_live_[A-Za-z0-9]{8,}(?![A-Za-z0-9])"), 0),
    ("clave de Anthropic", re.compile(r"(?<![A-Za-z0-9_-])sk-ant-[A-Za-z0-9_-]{8,}(?![A-Za-z0-9_-])"), 0),
    ("clave de OpenAI", re.compile(r"(?<![A-Za-z0-9_-])sk-proj-[A-Za-z0-9_-]{8,}(?![A-Za-z0-9_-])"), 0),
    ("JWT", re.compile(r"(?<![A-Za-z0-9_-])eyJ[A-Za-z0-9_-]{5,}\.[A-Za-z0-9_-]{8,}\.[A-Za-z0-9_-]{16,}(?![A-Za-z0-9_-])"), 0),
    ("asignación de secreto", re.compile(r"(?i)\b(?:password|secret|api_key|token)\b\s*=\s*([\"'])(?P<value>[^\"'\r\n]{12,})\1"), "value"),
    ("XML de factura FEL", re.compile(r"<dte:GTDocumento\b"), 0),  # reglas:permitir
    ("DPI de Guatemala", re.compile(r"(?<!\d)\d{4}[ -]\d{5}[ -]\d{4}(?!\d)"), 0),
)

_OCTET = r"(?:25[0-5]|2[0-4]\d|1\d\d|[1-9]?\d)"
IPV4 = re.compile(r"(?<![\d.])" + _OCTET + r"(?:\." + _OCTET + r"){3}(?![\d]|\.\d)")
IPV6 = re.compile(
    r"(?<![0-9A-Fa-f:])(?:(?:[0-9A-Fa-f]{1,4}:){7}[0-9A-Fa-f]{1,4}"
    r"|(?:[0-9A-Fa-f]{1,4}:){1,6}(?::[0-9A-Fa-f]{1,4}){1,6}"
    r"|(?:[0-9A-Fa-f]{1,4}:){1,7}:)(?![0-9A-Fa-f:])"
)
# Sufijos de redes internas y de malla privada.
HOST_INTERNO = re.compile(
    r"(?<![\w.-])[A-Za-z0-9](?:[A-Za-z0-9-]*[A-Za-z0-9])?(?:\.[A-Za-z0-9-]+)*"
    r"\.(?:ts\.net|local|lan|internal|intranet|corp|home\.arpa|localdomain)(?![\w-])",
    re.IGNORECASE,
)
USUARIO_HOST = re.compile(r"(?<![\w.@-])(?!git@)[a-z_][a-z0-9_-]{0,31}@[A-Za-z0-9][A-Za-z0-9.-]*\.[A-Za-z]{2,}\b|(?<![\w.@-])(?!git@)[a-z_][a-z0-9_-]{0,31}@(?:\d{1,3}\.){3}\d{1,3}\b")
RUTA_PRIVADA = re.compile(
    r"(?<![\w.-])(?:/home/[^/\s\"'`]+|/Users/[^/\s\"'`]+|/root|/srv|/mnt|/media|/var/(?:lib|www|log|backups)"
    r"|[A-Za-z]:\\Users\\[^\\\s\"'`]+)(?=[/\\\s\"'`,.;:)]|$)"
)

PRIVADOS = (
    ("dirección IP", IPV4),
    ("dirección IPv6", IPV6),
    ("host interno", HOST_INTERNO),
    ("usuario@host", USUARIO_HOST),
    ("ruta de servidor o de usuario", RUTA_PRIVADA),
)

_LOOPBACK = ("127.", "0.0.0.0", "255.255.255.")


def _ip_publica_o_ignorable(valor):
    return valor.startswith(_LOOPBACK)


def hosts_extra():
    """Patrones propios del usuario (un host o subcadena por línea) en ~/.config/reglas/hosts-privados."""
    ruta = os.path.join(os.path.expanduser("~"), ".config", "reglas", "hosts-privados")
    try:
        with open(ruta, encoding="utf-8") as origen:
            lineas = [x.strip() for x in origen.read().splitlines()]
    except OSError:
        return ()
    return tuple(re.compile(re.escape(x), re.IGNORECASE) for x in lineas if x and not x.startswith("#"))


def buscar_secretos(texto):
    """Devuelve [(etiqueta, valor)] con los secretos de CONTENT_RULES hallados en el texto."""
    hallazgos = []
    for etiqueta, patron, grupo in CONTENT_RULES:
        for m in patron.finditer(texto):
            hallazgos.append((etiqueta, m.group(grupo)))
    return hallazgos


def buscar_privados(texto):
    """Devuelve [(etiqueta, valor)] con hosts, IPs, usuarios y rutas privadas del texto."""
    hallazgos = []
    for etiqueta, patron in PRIVADOS:
        for m in patron.finditer(texto):
            valor = m.group(0)
            if etiqueta == "dirección IP" and _ip_publica_o_ignorable(valor):
                continue
            hallazgos.append((etiqueta, valor))
    for patron in hosts_extra():
        for m in patron.finditer(texto):
            hallazgos.append(("host privado", m.group(0)))
    return hallazgos


def redactar(texto):
    """Sustituye secretos, hosts, IPs, usuarios y rutas por marcadores. Se usa en la cola local de ideas."""
    for etiqueta, patron, grupo in CONTENT_RULES:
        texto = patron.sub(lambda m, g=grupo: m.group(0).replace(m.group(g), "[secreto]") if g else "[secreto]", texto)
    texto = RUTA_PRIVADA.sub("[ruta]", texto)
    texto = USUARIO_HOST.sub("[usuario@host]", texto)
    texto = HOST_INTERNO.sub("[host]", texto)
    texto = IPV6.sub("[ip]", texto)
    texto = IPV4.sub(lambda m: m.group(0) if _ip_publica_o_ignorable(m.group(0)) else "[ip]", texto)
    for patron in hosts_extra():
        texto = patron.sub("[host]", texto)
    return texto
