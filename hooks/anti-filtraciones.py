#!/usr/bin/env python3
import ast
import copy
import fnmatch
import json
import os
import re
import shlex
import shutil
import stat
import subprocess
import sys
import tempfile
import time

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import comandos  # noqa: E402
import redaccion  # noqa: E402
from redaccion import CONTENT_RULES  # noqa: E402

TIMEOUT = 5
ALLOW_MARK = "reglas:permitir"
HUNK_RE = re.compile(r"^@@ -\d+(?:,\d+)? \+(\d+)(?:,\d+)? @@")
SAT_RE = re.compile(r"\bSAT\b")
GH_RE = re.compile(r"\bgh\s+(?:(?:-R|--repo)[\s=]+\S+\s+)?(?:issue|pr)\s+(?:create|comment|edit|review)\b")
GH_REPO_RE = re.compile(r"(?:^|\s)(?:-R|--repo)(?:\s+|=)([\w.-]+/[\w.-]+)")
BODY_FILE_RE = re.compile(r'(?:^|\s)(?:--body-file|-F)(?:\s+|=)(?:"([^"]+)"|\'([^\']+)\'|(\S+))')
MAX_BODY = comandos.MAX_BODY
MAX_UNTRACKED_FILES = 2000
MAX_UNTRACKED_BYTES = 8 * MAX_BODY
COMMIT_RE = re.compile(r"\bgit\s+commit\b")
PUSH_RE = re.compile(r"\bgit\s+push\b")
DIFF_OPTIONS = ("--no-color", "--no-ext-diff", "--no-textconv", "--unified=0")
# Opciones de `git commit` que llevan valor: sin saltarlo, un mensaje parecería una opción o una ruta.
COMMIT_LONG_VALUE = {"--message", "--file", "--author", "--date", "--reuse-message", "--reedit-message",
                     "--template", "--fixup", "--squash", "--cleanup", "--trailer", "--pathspec-from-file"}
COMMIT_SHORT_VALUE = "mFCct"
PUSH_LONG_VALUE = {"--push-option", "--receive-pack", "--exec", "--repo"}


class HookFailure(Exception):
    pass


class Doubt(Exception):
    """Algo que git va a guardar o subir y no se puede revisar de antemano: se pregunta."""


class Unlocated(Doubt):
    """No se sabe en qué repo va a actuar git."""


def emit(decision, reason):
    print(json.dumps({"hookSpecificOutput": {
        "hookEventName": "PreToolUse",
        "permissionDecision": decision,
        "permissionDecisionReason": reason,
    }}, ensure_ascii=False))


def run(command, cwd, deadline, env=None):
    remaining = deadline - time.monotonic()
    if remaining <= 0:
        raise HookFailure("tiempo interno agotado")
    if command[0] == "git":
        # core.fsmonitor es un programa de la configuración del repo: revisar no debe ejecutarlo.
        command = ["git", "-c", "core.fsmonitor=false", *command[1:]]
    try:
        return subprocess.run(
            command,
            cwd=cwd,
            env=env,
            stdin=subprocess.DEVNULL,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            encoding="utf-8",
            errors="replace",
            timeout=remaining,
            check=False,
        )
    except subprocess.TimeoutExpired:
        raise HookFailure("tiempo interno agotado")


def git_command(subcommand, *args):
    # Prefijos a/ b/ fijos: diff.mnemonicPrefix o diff.noprefix del usuario rompen header_path.
    return ["git", "--no-pager", "-c", "core.quotePath=false", "-c", "diff.mnemonicPrefix=false",
            "-c", "diff.noprefix=false", "-c", "diff.relative=false", "-c", "log.showRoot=true",
            subcommand, *args]


def repository_root(cwd, deadline):
    result = run(["git", "rev-parse", "--show-toplevel"], cwd, deadline)
    if result.returncode != 0 or not result.stdout.strip():
        raise HookFailure("no se pudo localizar el repositorio Git")
    return os.path.realpath(result.stdout.strip())


def staged_patch(root, deadline, env=None):
    result = run(git_command("diff", "--cached", *DIFF_OPTIONS, "--"), root, deadline, env)
    if result.returncode != 0:
        raise HookFailure("git diff --cached no pudo completarse")
    return result.stdout


def pending_patch(root, deadline):
    upstream = run(["git", "rev-parse", "--abbrev-ref", "--symbolic-full-name", "@{u}"], root, deadline)
    if upstream.returncode != 0:
        return None
    result = run(git_command(
        "log", "--format=", "--patch", *DIFF_OPTIONS, "@{u}..HEAD", "--",
    ), root, deadline)
    if result.returncode != 0:
        raise HookFailure("git log de commits pendientes no pudo completarse")
    return result.stdout


def decode_path(value):
    value = value.strip()
    if value.startswith('"'):
        try:
            return ast.literal_eval(value)
        except (SyntaxError, ValueError):
            try:
                return shlex.split(value)[0]
            except (ValueError, IndexError):
                return value.strip('"')
    return value


def destination_path(value):
    value = decode_path(value)
    return value[2:] if value.startswith("b/") else value


def header_path(line):
    value = line[len("diff --git "):]
    if value.startswith('"'):
        try:
            return destination_path(shlex.split(value)[-1])
        except (ValueError, IndexError):
            return None
    marker = value.rfind(" b/")
    return destination_path(value[marker + 1:]) if marker >= 0 else None


def parse_patch(patch, deadline=None):
    paths = []
    added = {}
    current = None
    deleted = False
    in_diff = False
    new_line = None

    def finish_file():
        if in_diff and current and not deleted:
            paths.append(current)

    for index, line in enumerate(patch.splitlines()):
        if not index % 1000:
            check_time(deadline)
        if line.startswith("diff --git "):
            finish_file()
            current = header_path(line)
            deleted = False
            in_diff = True
            new_line = None
            continue
        if not in_diff:
            continue
        if line.startswith("deleted file mode"):
            deleted = True
        elif line.startswith("rename to "):
            current = decode_path(line[len("rename to "):])
            deleted = False
        elif line.startswith("+++ "):
            value = line[4:]
            if value == "/dev/null":
                deleted = True
            else:
                current = destination_path(value)
                deleted = False
            new_line = None
        else:
            hunk = HUNK_RE.match(line)
            if hunk:
                new_line = int(hunk.group(1))
            elif line.startswith("+") and not line.startswith("+++"):
                if current and not deleted and new_line is not None:
                    added.setdefault(current, []).append((new_line, line[1:]))
                    new_line += 1
            elif line.startswith("-") and not line.startswith("---"):
                continue
            elif line.startswith(" ") and new_line is not None:
                new_line += 1
    finish_file()
    return paths, added


def normalize_path(path):
    path = path.replace("\\", "/")
    while path.startswith("./"):
        path = path[2:]
    return path.lstrip("/")


def load_allowed_paths(root):
    try:
        with open(os.path.join(root, ".reglas-permitir"), encoding="utf-8") as source:
            lines = source.read().splitlines()
    except FileNotFoundError:
        return ()
    except OSError as error:
        raise HookFailure("no se pudo leer .reglas-permitir") from error
    patterns = []
    for line in lines:
        value = line.strip()
        if value and not value.startswith("#"):
            patterns.append(normalize_path(value))
    return tuple(patterns)


def path_allowed(path, patterns):
    path = normalize_path(path)
    for pattern in patterns:
        if fnmatch.fnmatchcase(path, pattern):
            return True
        directory = pattern.rstrip("/")
        if directory and path.startswith(directory + "/"):
            return True
    return False


def sensitive_kind(path):
    normalized = normalize_path(path)
    name = normalized.rsplit("/", 1)[-1]
    lower = name.lower()
    if (lower == ".env" or lower.startswith(".env.")) and lower != ".env.example":
        return "archivo .env"
    if lower.endswith(".pem") or lower.endswith(".key"):
        return "archivo de clave"
    if lower.startswith("id_rsa") or lower.startswith("id_ed25519"):
        return "clave SSH"
    if "_muestras" in normalized.split("/")[:-1]:
        return "carpeta _muestras"
    return None


def make_finding(path, line, label, value=""):
    return {"path": normalize_path(path), "line": max(1, int(line)), "label": label, "prefix": value[:4]}


def check_time(deadline):
    if deadline is not None and time.monotonic() >= deadline:
        raise HookFailure("tiempo interno agotado")


def scan_entries(paths, added, allowed_paths, deadline=None):
    findings = []
    for path in paths:
        if path_allowed(path, allowed_paths):
            continue
        kind = sensitive_kind(path)
        if kind:
            findings.append(make_finding(path, 1, "archivo sensible: " + kind))
    for path, entries in added.items():
        if path_allowed(path, allowed_paths):
            continue
        active_entries = []
        for index, (number, text) in enumerate(entries):
            if not index % 500:
                check_time(deadline)
            if ALLOW_MARK in text:
                continue
            active_entries.append((number, text))
            for label, pattern, group in CONTENT_RULES:
                match = pattern.search(text)
                if match:
                    findings.append(make_finding(path, number, label, match.group(group)))
                    break
        sat = any(SAT_RE.search(text) for _, text in active_entries)
        authorization = next((entry for entry in active_entries if "NumeroAutorizacion" in entry[1]), None)
        if sat and authorization:
            findings.append(make_finding(path, authorization[0], "XML de factura FEL", "NumeroAutorizacion"))
    return findings


def scan_patch(patch, allowed_paths, deadline=None):
    paths, added = parse_patch(patch, deadline)
    return scan_entries(paths, added, allowed_paths, deadline), added


def inline_allowed(added, path, line):
    entries = [(number, text) for number, text in added.get(path, []) if number == line]
    return bool(entries) and all(ALLOW_MARK in text for _, text in entries)


def relative_gitleaks_path(path, root):
    if os.path.isabs(path):
        path = os.path.relpath(path, root)
    return normalize_path(path)


def read_gitleaks_report(report_path, returncode):
    if not os.path.exists(report_path):
        if returncode == 0:
            return []
        raise HookFailure("gitleaks no generó su informe")
    try:
        with open(report_path, encoding="utf-8") as source:
            report = json.load(source)
    except (OSError, ValueError) as error:
        raise HookFailure("no se pudo leer el informe de gitleaks") from error
    if not isinstance(report, list):
        raise HookFailure("el informe de gitleaks tiene un formato desconocido")
    return report


def gitleaks_scan(executable, root, actions, deadline, allowed_paths, added_by_action, log_opts=None):
    findings = []
    warnings = []
    with tempfile.TemporaryDirectory(prefix="reglas-gitleaks-") as directory:
        for index, action in enumerate(actions):
            report_path = os.path.join(directory, "informe-{0}.json".format(index))
            command = [
                executable, "detect", "--source", root, "--no-banner",
                "--report-format", "json", "--report-path", report_path,
            ]
            if action == "commit":
                command.append("--staged")
            else:
                command.append("--log-opts=" + (log_opts or "@{u}..HEAD"))
            try:
                result = run(command, root, deadline)
                if result.returncode not in (0, 1):
                    raise HookFailure("gitleaks terminó con un error")
                report = read_gitleaks_report(report_path, result.returncode)
            except HookFailure as error:
                warnings.append(str(error))
                if deadline - time.monotonic() <= 0:
                    break
                continue
            added = added_by_action.get(action, {})
            for item in report:
                if not isinstance(item, dict):
                    continue
                path = relative_gitleaks_path(str(item.get("File") or "desconocido"), root)
                try:
                    line = int(item.get("StartLine") or 1)
                except (TypeError, ValueError):
                    line = 1
                if path_allowed(path, allowed_paths) or inline_allowed(added, path, line):
                    continue
                value = str(item.get("Secret") or item.get("Match") or "")
                findings.append(make_finding(path, line, "secreto detectado por gitleaks", value))
    return findings, warnings


def unique_findings(findings):
    unique = []
    seen = set()
    for finding in findings:
        key = (finding["path"], finding["line"], finding["label"], finding["prefix"])
        if key not in seen:
            seen.add(key)
            unique.append(finding)
    return unique


def format_finding(finding):
    text = "{0}:{1}: {2}".format(finding["path"], finding["line"], finding["label"])
    if finding["prefix"]:
        text += " (prefijo «{0}»)".format(finding["prefix"])
    return text


def decision_reason(findings, warnings):
    shown = findings[:20]
    details = "; ".join(format_finding(finding) for finding in shown)
    if len(findings) > len(shown):
        details += "; y {0} hallazgos más".format(len(findings) - len(shown))
    reason = "Anti-filtraciones: operación denegada por " + details
    if warnings:
        reason += ". Avisos: " + "; ".join(sorted(set(warnings)))
    return reason


def read_body_files(command, cwd):
    texts = []
    for match in BODY_FILE_RE.finditer(command):
        name = next(group for group in match.groups() if group)
        if name == "-":
            continue
        path = os.path.join(cwd, os.path.expanduser(name))
        try:
            with open(path, encoding="utf-8", errors="replace") as source:
                texts.append(source.read(MAX_BODY))
        except OSError:
            continue
    return texts


def repo_visibility(repo, cwd, deadline):
    args = ["gh", "repo", "view"] + ([repo] if repo else []) + ["--json", "visibility", "-q", ".visibility"]
    try:
        result = run(args, cwd, deadline)
    except (HookFailure, OSError):
        return None
    if result.returncode != 0:
        return None
    return result.stdout.strip().upper() or None


def active_text(texts):
    lines = []
    for text in texts:
        lines.extend(line for line in text.splitlines() if ALLOW_MARK not in line)
    return "\n".join(lines)


def without_references(text):
    """La ruta de --body-file y el valor de -R no se revisan como texto; el fichero sí."""
    return BODY_FILE_RE.sub(" ", GH_REPO_RE.sub(" ", text))


def split_command(command, calls):
    """(trozos propios de cada `gh`, resto del comando, que puede acabar en cualquiera de ellos)."""
    own = [[command[start:end] for start, end in call.tramos] for call in calls]
    rest = []
    position = 0
    for start, end in sorted(tuple(span) for call in calls for span in call.tramos):
        rest.append(command[position:start])
        position = max(position, end)
    rest.append(command[position:])
    return own, " ".join(rest)


def call_visibility(call, cwd, deadline, cache):
    """Visibilidad del repo destino; con varias carpetas posibles, la que más obliga."""
    if call.repo_desconocido or (call.repo and call.repo.startswith("-")):
        return None

    def visibility(folder):
        key = (call.repo, None if call.repo else folder)
        if key not in cache:
            cache[key] = repo_visibility(call.repo, folder, deadline)
        return cache[key]

    folders = [call.carpeta, *call.alternativas]
    known = [folder for folder in folders if folder and os.path.isdir(folder)]
    if call.repo:
        return visibility(call.carpeta if call.carpeta in known else cwd)
    found = [visibility(folder) for folder in known]
    unknown = len(known) < len(folders)
    if "PUBLIC" in found or (unknown and visibility(cwd) == "PUBLIC"):
        return "PUBLIC"
    if unknown or None in found:
        return None
    return found[0]


def unparsed_calls(command, cwd):
    """Sin ningún `gh` reconocido pero con su texto en el comando: se revisa el comando entero."""
    call = comandos.Gh(cwd, [(0, len(command))])
    repo = GH_REPO_RE.search(command)
    call.repo = repo.group(1) if repo else None
    call.textos = read_body_files(command, cwd)
    return [call]


def github_text_check(command, cwd, deadline, analysis=None):
    """Textos de gh issue/pr: secretos siempre; hosts, IPs, usuarios y rutas si el repo destino es público."""
    calls = analysis.gh if analysis else []
    if not calls:
        if not GH_RE.search(command):
            return None
        calls = unparsed_calls(command, cwd)
    own, rest = split_command(command, calls)
    everything = [without_references(command)] + [text for call in calls for text in call.textos]
    secrets = redaccion.buscar_secretos(active_text(everything))
    if secrets:
        label, value = secrets[0]
        return "deny", "Anti-filtraciones: el texto del issue o PR contiene {0} (prefijo «{1}»){2}. Quítalo y reescribe el texto.".format(
            label, value[:4], "" if len(secrets) == 1 else " y {0} hallazgos más".format(len(secrets) - 1))
    common = redaccion.buscar_privados(active_text([without_references(rest)]))
    cache = {}
    questions = []
    for call, slices in zip(calls, own):
        texts = [without_references(piece) for piece in slices] + call.textos
        private = redaccion.buscar_privados(active_text(texts)) + common
        if not private and not call.ilegible:
            continue
        visibility = call_visibility(call, cwd, deadline, cache)
        summary = "; ".join(sorted({label for label, _ in private}))
        if private and visibility == "PUBLIC":
            return "deny", ("Anti-filtraciones: el repo destino es público y el texto contiene {0}. "
                            "Quita hosts, IPs, usuarios y rutas de servidores (o pon el dato en el repo privado de runbooks).").format(summary)
        if private and visibility is None:
            questions.append(("Anti-filtraciones: el texto contiene {0} y no se pudo comprobar si el repo destino es público "
                              "(`gh repo view --json visibility`). ¿Seguro que es privado?").format(summary))
        if call.ilegible and visibility in ("PUBLIC", None):
            questions.append("Anti-filtraciones: no se puede leer de antemano el título o el cuerpo del issue o PR y el repo "
                             "destino {0}. Revisa lo que se va a publicar antes de aprobar (o escríbelo en un fichero y "
                             "usa --body-file).".format("es público" if visibility else "puede ser público"))
    if questions:
        return "ask", " ".join(dict.fromkeys(questions))
    return None


def option_text(word, text):
    return text if text is not None else word.prefijo()


def commit_options(arguments):
    """(opciones activas, rutas); una ruta None es la que no se puede saber."""
    flags = set()
    paths = []
    index = 0
    only_paths = False
    while index < len(arguments):
        word, text = arguments[index]
        option = option_text(word, text)
        if only_paths or not option.startswith("-") or option == "-":
            if text != "":
                paths.append(text)
        elif option == "--":
            only_paths = True
        elif option.startswith("--"):
            name, equals, _ = option.partition("=")
            flags.add(name)
            if name in COMMIT_LONG_VALUE and not equals:
                index += 1
        else:
            for position in range(1, len(option)):
                letter = option[position]
                if letter in COMMIT_SHORT_VALUE:
                    attached = position < len(option) - 1 or (text is None and not word.es_literal())
                    index += 0 if attached else 1
                    break
                if letter in "Su":
                    break
                flags.add({"a": "--all", "i": "--include", "p": "--patch"}.get(letter, "-" + letter))
        index += 1
    return flags, paths


def add_options(arguments):
    flags = set()
    paths = []
    only_paths = False
    names = {"A": "--all", "u": "--update", "f": "--force", "n": "--dry-run", "p": "--patch",
             "i": "--interactive", "e": "--edit"}
    for word, text in arguments:
        option = option_text(word, text)
        if only_paths or not option.startswith("-") or option == "-":
            if text != "":
                paths.append(text)
        elif option == "--":
            only_paths = True
        elif option.startswith("--"):
            flags.add(option.partition("=")[0])
        else:
            flags.update(names.get(letter, "-" + letter) for letter in option[1:])
    return flags, paths


def covers(spec, folder, path):
    """Si la ruta `spec`, escrita desde `folder`, alcanza a `path`."""
    target = os.path.realpath(os.path.join(folder, spec))
    return (path == target or path.startswith(target.rstrip(os.sep) + os.sep)
            or fnmatch.fnmatchcase(path, target))


class Review:
    def __init__(self, deadline):
        self.deadline = deadline
        self.findings = []
        self.warnings = []
        self.doubts = []
        self.gitleaks = {}  # (raíz, acción, rango) -> líneas añadidas

    def git(self, args, cwd, env):
        return run(args, cwd, self.deadline, env)

    def output(self, command, cwd, env, failure):
        result = self.git(command, cwd, env)
        if result.returncode != 0:
            raise HookFailure(failure)
        return result.stdout

    def scan(self, patch, allowed_paths, root=None, action=None, log_opts=None):
        findings, added = scan_patch(patch, allowed_paths, self.deadline)
        self.findings.extend(findings)
        if action:
            self.job(root, action, log_opts, added)

    def job(self, root, action, log_opts, added):
        lines = self.gitleaks.setdefault((root, action, log_opts), {})
        for path, entries in added.items():
            lines.setdefault(path, []).extend(entries)

    def locate(self, call):
        """(raíz, entorno) del repo en el que actúa `call`, o None si allí no hay repositorio."""
        name = "git " + call.suborden
        if call.carpeta is None or not os.path.isdir(call.carpeta):
            raise Unlocated("no se puede saber en qué carpeta actúa «{0}»".format(name))
        env = dict(os.environ, **call.variables) if call.variables else None
        result = self.git(["git", "rev-parse", "--show-toplevel"], call.carpeta, env)
        if result.returncode == 0 and result.stdout.strip():
            return os.path.realpath(result.stdout.strip()), env
        if call.suborden == "push" and self.git(["git", "rev-parse", "--git-dir"], call.carpeta, env).returncode == 0:
            return os.path.realpath(call.carpeta), env  # repo sin árbol de trabajo
        if call.repo_nuevo:
            raise Unlocated("«{0}» actúa en un repositorio que este mismo comando crea o clona".format(name))
        return None  # allí no hay repositorio: git no va a guardar ni subir nada

    def tree_patch(self, directory, env, paths):
        """Cambios de los ficheros versionados frente al último commit (estén preparados o no)."""
        base = "HEAD"
        if self.git(["git", "rev-parse", "--verify", "--quiet", "HEAD"], directory, env).returncode != 0:
            base = self.output(["git", "hash-object", "-t", "tree", os.devnull], directory, env,
                               "no se pudo preparar la comparación sin commits").strip()
        return self.output(git_command("diff", *DIFF_OPTIONS, base, "--", *paths), directory, env,
                           "git diff de los cambios sin preparar no pudo completarse")

    def commit(self, call, root, env, previous_adds):
        allowed_paths = load_allowed_paths(root)
        flags, paths = commit_options(call.argumentos)
        whole = bool(flags & {"--all", "--patch", "--interactive", "--pathspec-from-file"}) or None in paths
        only = bool(paths) and not whole and "--include" not in flags
        self.job(root, "commit", None, {})
        if not only:
            self.scan(staged_patch(root, self.deadline, env), allowed_paths, root, "commit")
        if whole:
            self.scan(self.tree_patch(root, env, []), allowed_paths, root, "commit")
        elif paths:
            self.scan(self.tree_patch(call.carpeta, env, paths), allowed_paths, root, "commit")
        if whole or paths:
            self.written(call, root, env, [] if whole else paths, True, False, allowed_paths)
        for add, add_root, add_env in previous_adds:
            if add_root == root:
                self.add(add, add_root, add_env, allowed_paths)

    def add(self, call, root, env, allowed_paths):
        """Lo que un `git add` anterior del mismo comando meterá en el commit."""
        flags, paths = add_options(call.argumentos)
        if "--dry-run" in flags:
            return
        everything = flags & {"--all", "--no-ignore-removal", "--update", "--patch", "--interactive",
                              "--edit", "--pathspec-from-file"}
        if not paths and not everything:
            return
        specs = [":/"] if not paths or None in paths else paths
        self.scan(self.tree_patch(call.carpeta, env, specs), allowed_paths)
        tracked_only = bool(flags & {"--update", "--patch", "--edit"})
        self.written(call, root, env, specs, tracked_only, "--force" in flags, allowed_paths)
        if tracked_only:
            return
        exclude = [] if "--force" in flags else ["--exclude-standard"]
        listed = self.output(["git", "ls-files", "--others", *exclude, "-z", "--full-name", "--", *specs],
                             call.carpeta, env, "git ls-files de los ficheros nuevos no pudo completarse")
        self.new_files(root, [name for name in listed.split("\0") if name], allowed_paths)

    def written(self, call, root, env, specs, tracked_only, force, allowed_paths):
        """Lo que el mismo comando escribe antes de guardarlo: en disco aún no está."""
        everything = not specs or ":/" in specs
        for path, content in call.escritos.items():
            if not os.path.isabs(path):
                continue
            check_time(self.deadline)
            real = os.path.realpath(path)
            name = os.path.relpath(real, root).replace(os.sep, "/")
            if name == "." or name.split("/")[0] in ("..", ".git"):
                continue
            if not everything and not any(covers(spec, call.carpeta, real) for spec in specs):
                continue
            if tracked_only:
                listed = ["git", "ls-files", "--error-unmatch", "--", ":(literal)" + name]
                if self.git(listed, root, env).returncode != 0:
                    continue
            elif not force and self.git(["git", "check-ignore", "-q", "--", name], root, env).returncode == 0:
                continue
            added = {}
            if content is not None:
                previous = self.git(["git", "show", "--no-textconv", "HEAD:" + name], root, env)
                saved = set(previous.stdout.splitlines()) if previous.returncode == 0 else set()
                added[name] = [(number, line) for number, line in enumerate(content.splitlines(), 1)
                               if line not in saved]
            self.findings.extend(scan_entries([name], added, allowed_paths, self.deadline))

    def new_files(self, root, names, allowed_paths):
        added = {}
        total = 0
        skipped = len(names) > MAX_UNTRACKED_FILES
        for name in names[:MAX_UNTRACKED_FILES]:
            check_time(self.deadline)
            if path_allowed(name, allowed_paths):
                continue
            path = os.path.join(root, name)
            try:
                info = os.lstat(path)
                if not stat.S_ISREG(info.st_mode):
                    continue
                with open(path, "rb") as source:
                    data = source.read(8000)
                    if b"\0" in data:  # binario, como lo decide git
                        continue
                    if info.st_size > MAX_BODY or total + info.st_size > MAX_UNTRACKED_BYTES:
                        skipped = True
                        continue
                    data += source.read(MAX_BODY)
            except OSError:
                continue
            total += len(data)
            added[name] = list(enumerate(data.decode("utf-8", "replace").splitlines(), 1))
        self.findings.extend(scan_entries(names, added, allowed_paths, self.deadline))
        if skipped:
            self.doubts.append("hay demasiados ficheros nuevos, o demasiado grandes, para revisarlos todos")

    def commits_of(self, root, env, namespaces):
        listed = self.output(
            ["git", "for-each-ref", "--format=%(objecttype) %(objectname) %(*objecttype) %(*objectname)", *namespaces],
            root, env, "git for-each-ref no pudo completarse")
        found = []
        for line in listed.splitlines():
            fields = line.split()
            found.extend(fields[i + 1] for i in range(0, len(fields) - 1, 2) if fields[i] == "commit")
        return found

    def default_remote(self, root, env):
        branch = self.git(["git", "symbolic-ref", "--quiet", "--short", "HEAD"], root, env).stdout.strip()
        keys = ["remote.pushDefault"]
        if branch:
            keys = ["branch.{0}.pushRemote".format(branch), *keys, "branch.{0}.remote".format(branch)]
        for key in keys:
            value = self.git(["git", "config", "--get", key], root, env).stdout.strip()
            if value:
                return value
        return "origin"

    def push_range(self, call, root, env):
        """Argumentos de `git log` con los commits que el push va a publicar, o None si no publica ninguno."""
        flags = set()
        positional = []
        option_remote = None
        arguments = call.argumentos
        index = 0
        only_positional = False
        while index < len(arguments):
            word, text = arguments[index]
            option = option_text(word, text)
            if only_positional or not option.startswith("-") or option == "-":
                if text != "":
                    positional.append(text)
            elif option == "--":
                only_positional = True
            elif option.startswith("--"):
                name, equals, value = option.partition("=")
                flags.add(name)
                if name in PUSH_LONG_VALUE and not equals:
                    index += 1
                    value = arguments[index][1] if index < len(arguments) else None
                if name == "--repo":
                    option_remote = value
            else:
                for position in range(1, len(option)):
                    if option[position] == "o":
                        index += 0 if position < len(option) - 1 else 1
                        break
                    flags.add({"d": "--delete", "n": "--dry-run"}.get(option[position], "-" + option[position]))
            index += 1
        if "--delete" in flags:
            return None
        remote = positional[0] if positional else option_remote or self.default_remote(root, env)
        specs = positional[1:]
        revisions = []
        if flags & {"--all", "--branches", "--mirror"}:
            revisions += self.commits_of(root, env, ["refs/heads"])
        if flags & {"--tags", "--mirror"}:
            revisions += self.commits_of(root, env, ["refs/tags"])
        sources = []
        position = 0
        while position < len(specs):
            spec = specs[position]
            position += 1
            if spec is None:
                raise Doubt("no se puede saber qué rama o etiqueta sube «git push»")
            if spec == "tag" and position < len(specs) and specs[position] is not None:
                sources.append("refs/tags/" + specs[position])
                position += 1
                continue
            spec = spec.lstrip("+")
            source = spec.partition(":")[0]
            if spec == ":" or "*" in source:
                namespace = "refs/tags" if source.startswith("refs/tags/") else "refs/heads"
                revisions += self.commits_of(root, env, [namespace])
            elif source:  # sin origen es un borrado
                sources.append(source)
        if not specs and not flags & {"--all", "--branches", "--mirror", "--tags"}:
            sources.append("HEAD")
        for source in sources:
            # Un nombre que aún no existe (rama creada en el mismo comando) saldrá del commit actual.
            for candidate in (source, "HEAD"):
                result = self.git(["git", "rev-parse", "--verify", "--quiet", "--end-of-options",
                                   candidate + "^{commit}"], root, env)
                if result.returncode == 0:
                    revisions.append(result.stdout.strip())
                    break
        if not revisions:
            return None
        revisions = list(dict.fromkeys(revisions))
        if remote and self.git(["git", "for-each-ref", "--count=1", "refs/remotes/" + remote], root, env).stdout:
            return [*revisions, "--not", "--remotes=" + remote]
        return revisions  # no se sabe qué tiene ese remoto (puede ser nuevo): recibe toda la historia

    def push(self, call, root, env):
        allowed_paths = load_allowed_paths(root)
        revisions = self.push_range(call, root, env)
        if revisions is None:
            return
        patch = self.output(git_command("log", "--format=", "--patch", *DIFF_OPTIONS, *revisions, "--"),
                            root, env, "git log de commits pendientes no pudo completarse")
        self.scan(patch, allowed_paths, root, "push", " ".join(revisions))

    def invoke(self, call, adds, unchecked_add):
        located = self.locate(call)
        if located is None:
            return
        if call.suborden == "commit":
            if unchecked_add:
                self.doubts.append("no se puede saber qué añade un «git add» anterior")
            self.commit(call, *located, adds)
        elif call.suborden == "push":
            self.push(call, *located)
        else:
            adds.append((call, *located))

    def invocations(self, calls, cwd):
        adds = []
        unchecked_add = False
        for call in calls:
            folders = list(call.alternativas)
            try:
                self.invoke(call, adds, unchecked_add)
            except (Doubt, HookFailure) as error:
                # Un `git add` suelto no publica nada: la duda la plantea el commit que lo siga.
                if call.suborden in ("commit", "push"):
                    self.doubts.append(str(error))
                else:
                    unchecked_add = True
                if isinstance(error, Unlocated):
                    folders.append(cwd)  # lo más probable sigue siendo la carpeta de la sesión
            for folder in dict.fromkeys(folders):
                self.alternative(call, folder, adds)

    def alternative(self, call, folder, adds):
        """Otra carpeta en la que `call` puede acabar actuando: sus hallazgos cuentan, sus dudas no."""
        if folder is None:
            return
        variant = copy.copy(call)
        variant.carpeta, variant.variables, variant.repo_nuevo = folder, {}, False
        asked = len(self.doubts)
        try:
            self.invoke(variant, adds, False)
        except Doubt:
            pass
        except HookFailure as error:
            self.doubts.append(str(error))
            return
        del self.doubts[asked:]

    def textual(self, command, cwd, kinds):
        """`git commit` o `git push` en un texto que no se ha reconocido como orden: carpeta de la sesión."""
        root = repository_root(cwd, self.deadline)
        allowed_paths = load_allowed_paths(root)
        if "commit" in kinds:
            self.scan(staged_patch(root, self.deadline), allowed_paths, root, "commit")
        if "push" in kinds:
            patch = pending_patch(root, self.deadline)
            if patch is not None:
                self.scan(patch, allowed_paths, root, "push")

    def run_gitleaks(self):
        executable = shutil.which("gitleaks")
        if not executable:
            return
        for (root, action, log_opts), added in self.gitleaks.items():
            try:
                extra, warnings = gitleaks_scan(
                    executable, root, [action], self.deadline, load_allowed_paths(root), {action: added}, log_opts)
            except (HookFailure, OSError) as error:
                extra, warnings = [], ["gitleaks no pudo ejecutarse ({0})".format(type(error).__name__)]
            self.findings.extend(extra)
            self.warnings.extend(warnings)

    def decision(self):
        findings = unique_findings(self.findings)
        if findings:
            return "deny", decision_reason(findings, self.warnings)
        warnings = "; ".join(sorted(set(self.warnings)))
        if self.doubts:
            reason = "Anti-filtraciones: no se pudo revisar todo lo que git va a guardar o subir: {0}. " \
                     "Compruébalo antes de aprobar.".format("; ".join(dict.fromkeys(self.doubts)))
            return "ask", reason + (" Avisos: " + warnings if warnings else "")
        if warnings:
            return "allow", "Anti-filtraciones: revisión propia sin hallazgos, pero {0}; se permite la operación.".format(
                warnings)
        return None


def git_check(command, cwd, deadline, analysis=None):
    """Lo que guardan o suben los git commit/push del comando: devuelve (decisión, motivo) o None."""
    calls = analysis.git if analysis else []
    recognized = {call.suborden for call in calls} & {"commit", "push"}
    plain = [call.suborden for call in calls if call.directa]
    unrecognized = {kind for kind, pattern in (("commit", COMMIT_RE), ("push", PUSH_RE))
                    if len(pattern.findall(command)) > plain.count(kind)}
    if not unrecognized and not recognized:
        return None
    # Formas que antes el hook ni miraba (`git -C …`): pueden bloquear o preguntar, pero un fallo o un
    # aviso no emite «allow», que se saltaría la confirmación de permisos de Claude Code.
    new_form = not (COMMIT_RE.search(command) or PUSH_RE.search(command))
    try:
        review = Review(deadline)
        review.invocations(calls, cwd)
        if unrecognized:
            try:
                review.textual(command, cwd, unrecognized)
            except HookFailure:
                if not recognized:
                    raise
        review.run_gitleaks()
        decision = review.decision()
    except Exception:
        if new_form:
            return None
        raise
    return None if new_form and decision and decision[0] == "allow" else decision


def analyze(command, cwd, deadline):
    """Órdenes git y gh del comando; None si no las hay o no se pueden leer (queda la búsqueda en el texto)."""
    if not re.search(r"\b(?:git|gh)\b", command):
        return None

    def root(folder):
        try:
            return repository_root(folder, deadline)
        except (HookFailure, OSError):
            return None

    try:
        return comandos.analizar(command, cwd, root)
    except Exception:
        return None


def main():
    deadline = time.monotonic() + TIMEOUT
    data = json.load(sys.stdin)
    tool_input = data.get("tool_input") or {}
    command = tool_input.get("command") or ""
    cwd = data.get("cwd") or os.getcwd()
    analysis = analyze(command, cwd, deadline)
    github = github_text_check(command, cwd, deadline, analysis)
    if github and github[0] == "deny":
        emit(*github)
        return
    # Un «ask» sobre el texto de gh no exime de revisar lo que el mismo comando sube con git.
    try:
        git = git_check(command, cwd, deadline, analysis)
    except Exception as error:
        if not github:
            raise
        git = ("allow", "No se pudo revisar la parte de git ({0}).".format(type(error).__name__))
    if git and git[0] == "deny":
        emit(*git)
    elif github:
        emit(github[0], github[1] + (" " + git[1] if git else ""))
    elif git:
        emit(*git)


if __name__ == "__main__":
    try:
        main()
    except Exception as error:
        emit("allow", "Anti-filtraciones: fallo interno ({0}); se permite la operación.".format(
            type(error).__name__,
        ))
    sys.exit(0)
