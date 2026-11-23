#!/usr/bin/env python3
"""Stop: si la sesión tiene ideas sin resolver, bloquea UNA sola vez con la lista.

Guardas contra bucles: `stop_hook_active` (el Stop ya fue bloqueado en este turno) y un registro
`aviso` en la cola (ya se bloqueó una vez en esta sesión).
"""
import json
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import ideas_cola  # noqa: E402

MOSTRAR = 8


def main():
    datos = json.load(sys.stdin)
    if datos.get("stop_hook_active"):
        return
    sesion = datos.get("session_id")
    if not isinstance(sesion, str) or not sesion:
        return
    registros = ideas_cola.leer()
    if any(r["tipo"] == "aviso" and r.get("sesion") == sesion for r in registros):
        return
    pendientes = ideas_cola.pendientes(registros, sesion)
    if not pendientes:
        return
    ideas_cola.añadir({"tipo": "aviso", "sesion": sesion})
    lista = "\n".join("- [{0}] {1}".format(r.get("categoria", "idea"), " ".join(str(r.get("extracto", "")).split())[:120])
                      for r in pendientes[:MOSTRAR])
    if len(pendientes) > MOSTRAR:
        lista += "\n- … y {0} más".format(len(pendientes) - MOSTRAR)
    print(json.dumps({"decision": "block", "reason": (
        "Quedan {0} {2} de esta sesión sin resolver en la cola:\n{1}\n"
        "Procésalas ahora con la skill /ideas (o dile al usuario que quedan en cola si no procede). "
        "Este aviso no se repite en esta sesión.").format(len(pendientes), lista, "idea" if len(pendientes) == 1 else "ideas")}, ensure_ascii=False))


if __name__ == "__main__":
    try:
        main()
    except Exception:
        pass
    sys.exit(0)
