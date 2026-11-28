"""Repo destino de una idea, repos permitidos, motivos de confirmación y duplicados (solo stdlib y `gh`).

Configuración opcional, fuera de cualquier repo: ~/.config/reglas/ideas.json
  {"repos": ["mi-usuario/*", "mi-org/web"], "runbooks": "mi-usuario/runbooks", "alias": {"la web": "mi-org/web"}}
"""
import datetime
import difflib
import fnmatch
import json
import os
import re
import subprocess
import time
import unicodedata

REPO = re.compile(r"^[A-Za-z0-9][\w.-]*/[\w.-]+$")
URL_GITHUB = re.compile(r"(?:(?<![\w.-])|(?<=www\.))github\.com[:/]([A-Za-z0-9][\w-]*/[\w.-]+)", re.IGNORECASE)  # gist. no
REF_ISSUE = re.compile(r"(?<![\w./-])([A-Za-z0-9][\w-]*/[\w.-]+)#\d+")
TOKEN_REPO = re.compile(r"(?<![\w./-])([A-Za-z0-9][\w-]*/[\w.-]+)(?![\w/])")
DATOS_SERVIDOR = ("[ip]", "[host]", "[usuario@host]", "[ruta]")
MARCADORES = DATOS_SERVIDOR + ("[secreto]",)
PRODUCCION = re.compile(r"\b(?:producci[oó]n|prod\b|despl(?:ie|e)g|deploy|release)", re.IGNORECASE)

TTL_CACHE = 600
DIAS_CERRADOS = 30
DUPLICADA = 0.92
PARECIDA = 0.45
ESCRITURA = ("ADMIN", "MAINTAIN", "WRITE")


class ErrorGh(Exception):
    pass


def gh_json(*args):
    try:
        r = subprocess.run(["gh", *args], stdin=subprocess.DEVNULL, capture_output=True, text=True,
                           timeout=30, check=False)
        if r.returncode != 0:
            raise ErrorGh((r.stderr.strip() or "gh falló")[:300])
        return json.loads(r.stdout)
    except (OSError, subprocess.TimeoutExpired, ValueError) as error:
        raise ErrorGh(type(error).__name__) from error


def _leer_json(ruta):
    with open(ruta, encoding="utf-8") as f:
        return json.load(f)


def runbooks_del_plugin():
    """Opción `repo_runbooks` del plugin: del entorno o de ~/.claude/settings.json."""
    valor = os.environ.get("CLAUDE_PLUGIN_OPTION_REPO_RUNBOOKS", "").strip()
    if valor:
        return valor
    try:
        datos = _leer_json(os.path.join(os.path.expanduser("~"), ".claude", "settings.json"))
        return str(datos["pluginConfigs"]["reglas@thealejandro"]["options"]["repo_runbooks"]).strip()
    except (OSError, ValueError, KeyError, TypeError):
        return ""


def configuracion():
    """Lanza ValueError si el fichero existe y está mal: una lista de permitidos rota no se ignora."""
    ruta = os.path.join(os.path.expanduser("~"), ".config", "reglas", "ideas.json")
    try:
        datos = _leer_json(ruta)
    except FileNotFoundError:
        datos = {}
    except (OSError, ValueError) as error:
        raise ValueError("no se pudo leer ideas.json: " + str(error)) from error
    if not isinstance(datos, dict):
        raise ValueError("ideas.json debe ser un objeto")
    repos = datos.get("repos")
    if repos is not None and not (isinstance(repos, list) and all(isinstance(x, str) for x in repos)):
        raise ValueError("ideas.json: «repos» debe ser una lista de textos")
    alias = datos.get("alias") or {}
    if not (isinstance(alias, dict) and all(isinstance(x, str) and REPO.match(x) for x in alias.values())):
        raise ValueError("ideas.json: «alias» debe ser un objeto {nombre: \"owner/repo\"}")
    runbooks = str(datos.get("runbooks") or "").strip() or runbooks_del_plugin()
    if not re.match(r"^(?:[A-Za-z0-9][\w.-]*/)?[A-Za-z0-9_][\w.-]*$", runbooks):
        runbooks = ""
    return {"repos": repos, "alias": alias, "runbooks": runbooks}


def en_lista(repo, patrones):
    return any(fnmatch.fnmatchcase(repo.lower(), p.strip().lower()) for p in patrones)


def _plano(texto):
    sin = unicodedata.normalize("NFKD", texto.lower())
    return "".join(c for c in sin if not unicodedata.combining(c))


def menciones(texto, config):
    """[(repo, "alias"|"mencion")] citados en el texto, sin repetir."""
    hallados = []
    plano = _plano(texto)
    for nombre, repo in config["alias"].items():
        if nombre.strip() and re.search(r"(?<![\w-])" + re.escape(_plano(nombre.strip())) + r"(?![\w-])", plano):
            hallados.append((repo, "alias"))
    explicitos = URL_GITHUB.findall(texto) + REF_ISSUE.findall(texto)
    if config["repos"]:  # un «a/b» suelto puede ser una ruta: solo cuenta si está permitido
        explicitos += [t for t in TOKEN_REPO.findall(texto) if en_lista(t.rstrip("."), config["repos"])]
    for repo in explicitos:
        repo = repo.rstrip(".").removesuffix(".git")
        if REPO.match(repo):
            hallados.append((repo, "mencion"))
    vistos = {}
    for repo, motivo in hallados:
        vistos.setdefault(repo.lower(), (repo, motivo))
    return list(vistos.values())


def examinar(repo, config, es_runbooks=False):
    """Visibilidad y permiso de un repo; si `gh` falla no se permite (`error`).

    Sin lista de permitidos, solo valen los repos que administras. El de runbooks vale además si puedes escribir en él.
    """
    try:
        datos = gh_json("repo", "view", repo, "--json", "nameWithOwner,visibility,viewerPermission,isArchived")
        nombre = datos.get("nameWithOwner") or repo
        visibilidad = str(datos.get("visibility") or "").upper() or None
    except (ErrorGh, AttributeError):
        datos, nombre, visibilidad = {}, repo, None
    archivado = bool(datos.get("isArchived"))
    permiso = datos.get("viewerPermission")
    if config["repos"] is not None:
        permitido = en_lista(nombre, config["repos"])
    else:
        permitido = permiso == "ADMIN"
    if es_runbooks:
        permitido = permitido or permiso in ESCRITURA
    info = {"repo": nombre, "visibilidad": visibilidad, "archivado": archivado,
            "permitido": bool(datos) and permitido and not archivado}
    if not datos:
        info["error"] = "gh"
    return info


def destino(idea, config):
    """Orden: mención o alias → remoto git del cwd → .cabo.toml → runbooks (datos de servidor) → borrador."""
    extracto = str(idea.get("extracto", ""))
    citados = menciones(extracto, config)
    candidatos = list(citados)
    for campo, motivo in (("remoto", "remoto"), ("repo_cabo", "cabo.toml")):
        valor = str(idea.get(campo) or "")
        if REPO.match(valor):
            candidatos.append((valor, motivo))
    de_servidor = any(m in extracto for m in DATOS_SERVIDOR)
    runbooks = config["runbooks"]
    if de_servidor and runbooks:
        candidatos.append((runbooks, "runbooks"))

    elegido, motivo, descartado = None, "borrador", None
    vistos = set()
    for repo, causa in candidatos:
        if repo.lower() in vistos:
            continue
        vistos.add(repo.lower())
        es_runbooks = repo.lower() == runbooks.lower()
        info = examinar(repo, config, es_runbooks)
        de_confianza = config["repos"] is None or es_runbooks or en_lista(repo, config["repos"])
        if info["permitido"] or "error" in info and de_confianza:  # un fallo de gh no desvía a otro repo
            elegido, motivo = info, causa
            break
        if descartado is None:
            descartado = (info, causa)
    if elegido is None and descartado:
        elegido, motivo = descartado

    resultado = {"hash": idea.get("hash"), "repo": None, "motivo": motivo, "visibilidad": None,
                 "permitido": False, "archivado": False, "confirmar": []}
    if elegido:
        resultado.update(elegido)
    confirmar = resultado["confirmar"]
    if elegido:
        if resultado["visibilidad"] == "PUBLIC":
            confirmar.append("repo público")
            if de_servidor:
                confirmar.append("habla de datos de servidores y el repo es público")
                if runbooks and motivo != "runbooks" and runbooks.lower() != resultado["repo"].lower():
                    resultado["alternativa"] = runbooks
        elif resultado["visibilidad"] is None:
            confirmar.append("visibilidad desconocida")
    otros = [repo for repo, _ in citados if not elegido or repo.lower() != resultado["repo"].lower()]
    remoto = str(idea.get("remoto") or "")
    if motivo == "alias" and REPO.match(remoto) and remoto.lower() != resultado["repo"].lower() \
            and remoto not in otros:  # un alias es texto corriente: si desplaza al remoto, se pregunta
        otros.append(remoto)
    if otros:
        confirmar.append("destino dudoso")
        resultado["otros"] = otros
    if any(m in extracto for m in MARCADORES):
        confirmar.append("el filtro redactó algo")
    if PRODUCCION.search(extracto):
        confirmar.append("afecta a producción")
    return resultado


def normalizar(titulo):
    return " ".join(sorted(re.findall(r"[a-z0-9]+", _plano(titulo))))


def parecido(a, b):
    return difflib.SequenceMatcher(None, normalizar(a), normalizar(b), autojunk=False).ratio()


def _desde():
    return (datetime.datetime.now(datetime.timezone.utc) - datetime.timedelta(days=DIAS_CERRADOS)).strftime("%Y-%m-%d")


def _vigente(issue):
    """Abierto, o cerrado hace 30 días o menos."""
    return str(issue.get("state", "")).upper() == "OPEN" or str(issue.get("closedAt") or "")[:10] >= _desde()


def ruta_cache(repo):
    return os.path.join(os.path.expanduser("~"), ".local", "state", "cabo", "ideas", "cache",
                        repo.lower().replace("/", "__") + ".json")


def olvidar_cache(repo):
    try:
        os.remove(ruta_cache(repo))
    except OSError:
        pass


def issues_recientes(repo):
    """Issues abiertos y cerrados en 30 días, con caché local de unos minutos."""
    ruta = ruta_cache(repo)
    try:
        guardado = _leer_json(ruta)
        if 0 <= time.time() - guardado["leido"] < TTL_CACHE:
            return guardado["issues"]
    except (OSError, ValueError, KeyError, TypeError):
        pass
    campos = ("--json", "number,title,state,closedAt")
    issues = gh_json("issue", "list", "-R", repo, "--state", "open", "--limit", "500", *campos)
    issues += gh_json("issue", "list", "-R", repo, "--state", "closed", "--search", "closed:>=" + _desde(),
                      "--limit", "500", *campos)
    os.makedirs(os.path.dirname(ruta), mode=0o700, exist_ok=True)
    temporal = "{0}.{1}.tmp".format(ruta, os.getpid())
    fd = os.open(temporal, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
    with os.fdopen(fd, "w", encoding="utf-8") as f:
        json.dump({"leido": time.time(), "issues": issues}, f, ensure_ascii=False)
    os.replace(temporal, ruta)
    return issues


def similares(repo, titulo):
    """franja: «duplicada» (casi idéntico y abierto), «dudosa» (que decida un modelo) o «nueva»."""
    palabras = sorted({p for p in re.findall(r"\w+", titulo) if len(p) > 3}, key=lambda p: (-len(p), p))[:3]
    try:
        recientes = issues_recientes(repo)
        buscados = []
        if palabras:
            buscados = gh_json("issue", "list", "-R", repo, "--state", "all", "--search", " ".join(palabras),
                               "--limit", "20", "--json", "number,title,state,closedAt")
    except ErrorGh as error:
        return {"repo": repo, "franja": "dudosa", "candidatos": [], "error": str(error)}
    hallados = {i["number"] for i in buscados if _vigente(i)}
    todos = {i["number"]: i for i in recientes + [i for i in buscados if _vigente(i)]}
    candidatos = []
    for numero, issue in todos.items():
        nota = parecido(titulo, issue.get("title", ""))
        if nota >= PARECIDA or numero in hallados:
            candidatos.append({"numero": numero, "titulo": issue.get("title", ""),
                               "estado": str(issue.get("state", "")).upper(), "parecido": round(nota, 2)})
    candidatos.sort(key=lambda c: -c["parecido"])
    franja = "nueva"
    if candidatos:
        mejor = candidatos[0]
        mismos_numeros = re.findall(r"\d+", normalizar(titulo)) == re.findall(r"\d+", normalizar(mejor["titulo"]))
        casi_igual = mejor["parecido"] >= DUPLICADA and mismos_numeros
        # uno cerrado puede ser una regresión o un «no se hará»: que lo decida alguien
        franja = "duplicada" if casi_igual and mejor["estado"] == "OPEN" else "dudosa"
    return {"repo": repo, "franja": franja, "candidatos": candidatos[:5]}
