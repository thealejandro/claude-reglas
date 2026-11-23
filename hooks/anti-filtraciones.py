#!/usr/bin/env python3
import ast
import fnmatch
import json
import os
import re
import shlex
import shutil
import subprocess
import sys
import tempfile
import time

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import redaccion  # noqa: E402
from redaccion import CONTENT_RULES  # noqa: E402

TIMEOUT = 5
ALLOW_MARK = "reglas:permitir"
HUNK_RE = re.compile(r"^@@ -\d+(?:,\d+)? \+(\d+)(?:,\d+)? @@")
SAT_RE = re.compile(r"\bSAT\b")
GH_RE = re.compile(r"\bgh\s+(?:(?:-R|--repo)[\s=]+\S+\s+)?(?:issue|pr)\s+(?:create|comment|edit|review)\b")
GH_REPO_RE = re.compile(r"(?:^|\s)(?:-R|--repo)(?:\s+|=)([\w.-]+/[\w.-]+)")
BODY_FILE_RE = re.compile(r'(?:^|\s)(?:--body-file|-F)(?:\s+|=)(?:"([^"]+)"|\'([^\']+)\'|(\S+))')
MAX_BODY = 1024 * 1024


class HookFailure(Exception):
    pass


def emit(decision, reason):
    print(json.dumps({"hookSpecificOutput": {
        "hookEventName": "PreToolUse",
        "permissionDecision": decision,
        "permissionDecisionReason": reason,
    }}, ensure_ascii=False))


def run(command, cwd, deadline):
    remaining = deadline - time.monotonic()
    if remaining <= 0:
        raise HookFailure("tiempo interno agotado")
    try:
        return subprocess.run(
            command,
            cwd=cwd,
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
            "-c", "diff.noprefix=false", subcommand, *args]


def repository_root(cwd, deadline):
    result = run(["git", "rev-parse", "--show-toplevel"], cwd, deadline)
    if result.returncode != 0 or not result.stdout.strip():
        raise HookFailure("no se pudo localizar el repositorio Git")
    return os.path.realpath(result.stdout.strip())


def staged_patch(root, deadline):
    result = run(git_command(
        "diff", "--cached", "--no-color", "--no-ext-diff", "--no-textconv",
        "--unified=0", "--",
    ), root, deadline)
    if result.returncode != 0:
        raise HookFailure("git diff --cached no pudo completarse")
    return result.stdout


def pending_patch(root, deadline):
    upstream = run(["git", "rev-parse", "--abbrev-ref", "--symbolic-full-name", "@{u}"], root, deadline)
    if upstream.returncode != 0:
        return None
    result = run(git_command(
        "log", "--format=", "--patch", "--no-color", "--no-ext-diff",
        "--no-textconv", "--unified=0", "@{u}..HEAD", "--",
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


def parse_patch(patch):
    paths = []
    added = {}
    current = None
    deleted = False
    in_diff = False
    new_line = None

    def finish_file():
        if in_diff and current and not deleted:
            paths.append(current)

    for line in patch.splitlines():
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


def scan_patch(patch, allowed_paths):
    paths, added = parse_patch(patch)
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
        for number, text in entries:
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
    return findings, added


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


def repo_visibility(command, cwd, deadline):
    repo = GH_REPO_RE.search(command)
    args = ["gh", "repo", "view"] + ([repo.group(1)] if repo else []) + ["--json", "visibility", "-q", ".visibility"]
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


def github_text_check(command, cwd, deadline):
    """Cuerpos de gh issue/pr: secretos siempre; hosts, IPs, usuarios y rutas si el repo destino es público."""
    if not GH_RE.search(command):
        return None
    text = active_text([BODY_FILE_RE.sub(" ", GH_REPO_RE.sub(" ", command))] + read_body_files(command, cwd))
    secrets = redaccion.buscar_secretos(text)  # (la ruta de --body-file y el valor de -R no se revisan; el fichero sí)
    if secrets:
        label, value = secrets[0]
        return "deny", "Anti-filtraciones: el texto del issue o PR contiene {0} (prefijo «{1}»){2}. Quítalo y reescribe el texto.".format(
            label, value[:4], "" if len(secrets) == 1 else " y {0} hallazgos más".format(len(secrets) - 1))
    private = redaccion.buscar_privados(text)
    if not private:
        return None
    visibility = repo_visibility(command, cwd, deadline)
    summary = "; ".join(sorted({label for label, _ in private}))
    if visibility == "PUBLIC":
        return "deny", ("Anti-filtraciones: el repo destino es público y el texto contiene {0}. "
                        "Quita hosts, IPs, usuarios y rutas de servidores (o pon el dato en el repo privado de runbooks).").format(summary)
    if visibility is None:
        return "ask", ("Anti-filtraciones: el texto contiene {0} y no se pudo comprobar si el repo destino es público "
                       "(`gh repo view --json visibility`). ¿Seguro que es privado?").format(summary)
    return None


def main():
    deadline = time.monotonic() + TIMEOUT
    data = json.load(sys.stdin)
    tool_input = data.get("tool_input") or {}
    command = tool_input.get("command") or ""
    cwd = data.get("cwd") or os.getcwd()
    github = github_text_check(command, cwd, deadline)
    if github:
        emit(*github)
        return
    commit = bool(re.search(r"\bgit\s+commit\b", command))
    push = bool(re.search(r"\bgit\s+push\b", command))
    if not commit and not push:
        return
    root = repository_root(cwd, deadline)
    allowed_paths = load_allowed_paths(root)
    findings = []
    actions = []
    added_by_action = {}
    if commit:
        patch = staged_patch(root, deadline)
        own, added = scan_patch(patch, allowed_paths)
        findings.extend(own)
        actions.append("commit")
        added_by_action["commit"] = added
    if push:
        patch = pending_patch(root, deadline)
        if patch is not None:
            own, added = scan_patch(patch, allowed_paths)
            findings.extend(own)
            actions.append("push")
            added_by_action["push"] = added
    warnings = []
    executable = shutil.which("gitleaks")
    if executable and actions:
        extra, warnings = gitleaks_scan(
            executable, root, actions, deadline, allowed_paths, added_by_action,
        )
        findings.extend(extra)
    findings = unique_findings(findings)
    if findings:
        emit("deny", decision_reason(findings, warnings))
    elif warnings:
        emit("allow", "Anti-filtraciones: revisión propia sin hallazgos, pero {0}; se permite la operación.".format(
            "; ".join(sorted(set(warnings))),
        ))


if __name__ == "__main__":
    try:
        main()
    except Exception as error:
        emit("allow", "Anti-filtraciones: fallo interno ({0}); se permite la operación.".format(
            type(error).__name__,
        ))
    sys.exit(0)
