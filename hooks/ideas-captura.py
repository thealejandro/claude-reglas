#!/usr/bin/env python3
"""UserPromptSubmit: detecta ideas, bugs y pendientes en el prompt y los apunta en la cola local.

Sin modelo, sin red, sin subprocesos (< 50 ms). El extracto se redacta antes de escribirse.
Salida: una línea de additionalContext. Ante cualquier fallo no hace nada (nunca bloquea el prompt).
"""
import hashlib
import json
import os
import re
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import ideas_cola  # noqa: E402
import redaccion  # noqa: E402

BUG = re.compile(r"\bbugs?\b", re.IGNORECASE)
PENDIENTE = re.compile(r"\bpendientes?\b|\bno (?:se )?(?:nos )?olvid(?:es|e|emos)\b|\btodo:", re.IGNORECASE)
IDEA = re.compile(
    r"habr[ií]a que|estar[ií]a bien|m[aá]s adelante|tambi[eé]n quiero|\bidea:|deber[ií]amos|deber[ií]a\b|se me ocurre|alg[uú]n d[ií]a|ojal[aá]",
    re.IGNORECASE,
)
ATRAS = 200
BLOQUE = re.compile(r"```.*?(?:```|\Z)", re.DOTALL)
PROMPT_TERMINAL = re.compile(r"^\s*(?:\$ |[\w.-]+@[\w.-]+:\S*[$#] )")


def limpiar(prompt):
    """Quita lo que no es del usuario: bloques de código, citas «> » y salida de terminal pegada."""
    salida = []
    en_terminal = False
    for linea in BLOQUE.sub("\n", prompt).splitlines():
        if not linea.strip():
            en_terminal = False
        elif PROMPT_TERMINAL.match(linea):
            en_terminal = True
        if en_terminal or linea.lstrip().startswith(">"):
            continue
        salida.append(linea)
    return "\n".join(salida)


def categoria(texto):
    for nombre, patron in (("bug", BUG), ("pendiente", PENDIENTE), ("idea", IDEA)):
        m = patron.search(texto)
        if m:
            return nombre, m.start()
    return None, 0


def extracto(prompt, inicio):
    desde = max(0, inicio - ATRAS)
    corte = max(prompt.rfind("\n", desde, inicio), prompt.rfind(". ", desde, inicio) + 1 or -1)
    if corte >= 0:
        desde = corte + 1
    texto = " ".join(prompt[desde:desde + 2 * ideas_cola.MAX_EXTRACTO].split())
    return redaccion.redactar(texto)[:ideas_cola.MAX_EXTRACTO]


def main():
    datos = json.load(sys.stdin)
    prompt = datos.get("prompt")
    if not isinstance(prompt, str) or not prompt.strip():
        return
    inicio = prompt.lstrip()
    if inicio.startswith(("/", "<")):  # comandos y mensajes del sistema, no ideas del usuario
        return
    prompt = limpiar(prompt)
    nombre, pos = categoria(prompt)
    if not nombre:
        return
    texto = extracto(prompt, pos)
    sesion = datos.get("session_id") if isinstance(datos.get("session_id"), str) else ""
    cwd = datos.get("cwd") if isinstance(datos.get("cwd"), str) else os.getcwd()
    remoto = ideas_cola.remoto_de(cwd)
    clave = " ".join(texto.lower().split()) + "|" + remoto
    hash_ = hashlib.sha256(clave.encode("utf-8")).hexdigest()[:16]
    if any(r.get("hash") == hash_ for r in ideas_cola.leer() if r["tipo"] == "idea"):
        return
    ideas_cola.añadir({
        "tipo": "idea", "sesion": sesion, "cwd": redaccion.redactar(cwd), "remoto": remoto,
        "categoria": nombre, "extracto": texto, "hash": hash_,
    })
    pendientes = len(ideas_cola.pendientes(ideas_cola.leer()))
    print(json.dumps({"hookSpecificOutput": {
        "hookEventName": "UserPromptSubmit",
        "additionalContext": (
            "Idea anotada en la cola local ({0}, {1} en cola). No interrumpas la tarea; "
            "al terminar el paso, procésalas con /ideas.".format(nombre, pendientes)),
    }}, ensure_ascii=False))


if __name__ == "__main__":
    try:
        main()
    except Exception:
        pass
    sys.exit(0)
