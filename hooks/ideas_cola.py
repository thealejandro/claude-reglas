"""Cola local de ideas (formato v1, JSONL). Solo stdlib.

Fichero: ~/.local/state/cabo/ideas/cola.jsonl (carpeta 700, fichero 600). Solo se añaden líneas;
nunca se reescribe una existente. Una línea = un registro JSON con `v` (versión) y `tipo`:

  idea      {"v":1,"tipo":"idea","fecha":ISO8601 UTC,"sesion":str,"cwd":str,"remoto":str,
             "categoria":"idea"|"bug"|"pendiente","extracto":str<=500 ya redactado,"hash":16 hex,
             "repo_cabo":"owner/repo" (opcional, del .cabo.toml)}
  resuelta  {"v":1,"tipo":"resuelta","fecha":...,"hash":...,"estado":"creada"|"comentada"|"duplicada"|"descartada",
             "issue":"owner/repo#N" (opcional)}
  aplazada  {"v":1,"tipo":"aplazada","fecha":...,"hash":...,"motivo":str}  (sigue pendiente)
  aviso     {"v":1,"tipo":"aviso","fecha":...,"sesion":str}  (el Stop ya bloqueó una vez en esa sesión)

Pendiente = `idea` sin ningún `resuelta` con el mismo `hash`. Los lectores ignoran líneas rotas y
registros con `v` desconocido o `tipo` desconocido. Documentación completa: README, «Cola de ideas».
"""
import contextlib
import datetime
import json
import os
import re

VERSION = 1
MAX_EXTRACTO = 500
ESTADOS_RESUELTA = ("creada", "comentada", "duplicada", "descartada")


def ruta_cola():
    return os.path.join(os.path.expanduser("~"), ".local", "state", "cabo", "ideas", "cola.jsonl")


def ahora():
    return datetime.datetime.now(datetime.timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


@contextlib.contextmanager
def bloqueo():
    """Exclusión mutua entre hooks y `compactar` (flock sobre cola.lock; sin él, se sigue sin bloquear)."""
    carpeta = os.path.dirname(ruta_cola())
    os.makedirs(carpeta, mode=0o700, exist_ok=True)
    fd = os.open(os.path.join(carpeta, "cola.lock"), os.O_WRONLY | os.O_CREAT, 0o600)
    try:
        try:
            import fcntl
            fcntl.flock(fd, fcntl.LOCK_EX)
        except (ImportError, OSError):
            pass
        yield
    finally:
        os.close(fd)


def añadir(registro):
    registro = dict(registro, v=VERSION, fecha=registro.get("fecha") or ahora())
    ruta = ruta_cola()
    carpeta = os.path.dirname(ruta)
    os.makedirs(carpeta, mode=0o700, exist_ok=True)
    with bloqueo():
        fd = os.open(ruta, os.O_WRONLY | os.O_APPEND | os.O_CREAT, 0o600)
        try:
            os.fchmod(fd, 0o600)
            os.write(fd, (json.dumps(registro, ensure_ascii=False, separators=(",", ":")) + "\n").encode("utf-8"))
        finally:
            os.close(fd)


def leer():
    try:
        with open(ruta_cola(), encoding="utf-8", errors="replace") as origen:
            lineas = origen.read().splitlines()
    except OSError:
        return []
    registros = []
    for linea in lineas:
        try:
            r = json.loads(linea)
        except ValueError:
            continue
        if isinstance(r, dict) and r.get("v") == VERSION and isinstance(r.get("tipo"), str):
            registros.append(r)
    return registros


def pendientes(registros, sesion=None):
    resueltos = {r.get("hash") for r in registros if r["tipo"] == "resuelta"}
    return [r for r in registros
            if r["tipo"] == "idea" and r.get("hash") not in resueltos
            and (sesion is None or r.get("sesion") == sesion)]


def repo_cabo(cwd):
    """`repo = "owner/repo"` del .cabo.toml más cercano, sin salir del repositorio git ni del home.

    Un .cabo.toml de otro usuario (carpetas compartidas) se ignora.
    """
    try:
        carpeta = os.path.abspath(cwd)
        casa = os.path.expanduser("~")
        for _ in range(40):
            try:
                with open(os.path.join(carpeta, ".cabo.toml"), encoding="utf-8", errors="replace") as f:
                    ajeno = hasattr(os, "getuid") and os.fstat(f.fileno()).st_uid != os.getuid()
                    texto = None if ajeno else f.read(65536)
            except OSError:
                texto = None
            if texto is not None:  # solo claves de la raíz: antes de la primera [tabla]
                raiz = re.split(r"(?m)^[ \t]*\[", texto)[0]
                m = re.search(r"""(?m)^[ \t]*repo[ \t]*=[ \t]*(["'])([A-Za-z0-9][\w.-]*/[\w.-]+)\1""", raiz)
                return m.group(2) if m else ""
            padre = os.path.dirname(carpeta)
            if padre == carpeta or carpeta == casa or os.path.exists(os.path.join(carpeta, ".git")):
                break
            carpeta = padre
        return ""
    except Exception:
        return ""


def remoto_de(cwd):
    """owner/repo (o la URL sin credenciales) del remoto origin, leyendo .git/config sin lanzar git."""
    try:
        carpeta = os.path.abspath(cwd)
        for _ in range(40):
            git = os.path.join(carpeta, ".git")
            if os.path.exists(git):
                break
            padre = os.path.dirname(carpeta)
            if padre == carpeta:
                return ""
            carpeta = padre
        else:
            return ""
        if os.path.isfile(git):  # worktree: .git es un fichero «gitdir: …»
            with open(git, encoding="utf-8") as f:
                destino = f.read().strip().removeprefix("gitdir:").strip()
            destino = os.path.join(carpeta, destino)
            try:
                with open(os.path.join(destino, "commondir"), encoding="utf-8") as f:
                    destino = os.path.normpath(os.path.join(destino, f.read().strip()))
            except OSError:
                pass
            config = os.path.join(destino, "config")
        else:
            config = os.path.join(git, "config")
        with open(config, encoding="utf-8", errors="replace") as f:
            texto = f.read()
        m = re.search(r'\[remote "origin"\][^\[]*?\burl\s*=\s*(\S+)', texto)
        if not m:
            return ""
        url = m.group(1)
        g = re.search(r"github\.com[:/]+([\w.-]+/[\w.-]+?)(?:\.git)?/?$", url)
        if g:
            return g.group(1)
        return re.sub(r"//[^/@]*@", "//", url)[:200]
    except Exception:
        return ""
