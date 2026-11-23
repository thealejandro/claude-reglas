#!/usr/bin/env python3
"""SessionStart: reinyecta «N ideas en cola» (también tras compactar) si hay pendientes."""
import json
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import ideas_cola  # noqa: E402


def main():
    datos = json.load(sys.stdin)
    registros = ideas_cola.leer()
    total = len(ideas_cola.pendientes(registros))
    if not total:
        return
    sesion = datos.get("session_id")
    propias = len(ideas_cola.pendientes(registros, sesion)) if isinstance(sesion, str) and sesion else 0
    texto = "{0} {1} en cola sin resolver".format(total, "idea" if total == 1 else "ideas")
    if propias:
        texto += " ({0} de esta sesión)".format(propias)
    print(json.dumps({"hookSpecificOutput": {
        "hookEventName": "SessionStart",
        "additionalContext": texto + ". Procésalas con /ideas cuando termines el paso en curso.",
    }}, ensure_ascii=False))


if __name__ == "__main__":
    try:
        main()
    except Exception:
        pass
    sys.exit(0)
