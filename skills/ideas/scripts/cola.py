#!/usr/bin/env python3
"""Ayudante de la skill /ideas para la cola local (formato v1 documentado en hooks/ideas_cola.py).

  cola.py pendientes [--sesion ID] [--repo owner/repo]   JSON con las ideas pendientes
  cola.py resolver HASH ESTADO [--issue owner/repo#N]    ESTADO: creada|comentada|duplicada|descartada
  cola.py aplazar HASH --motivo TEXTO                    sigue pendiente
  cola.py destino HASH [HASH…]                           repo destino, si está permitido y qué confirmar
  cola.py similares --repo owner/repo --titulo TEXTO     franja duplicada|dudosa|nueva frente a sus issues
  cola.py hoy owner/repo                                 issues creados hoy (UTC) en ese repo y tope diario
  cola.py compactar                                      borra ideas resueltas hace más de 30 días
"""
import argparse
import datetime
import json
import os
import sys

AQUI = os.path.dirname(os.path.abspath(__file__))
sys.path[:0] = [AQUI, os.path.join(AQUI, "..", "..", "..", "hooks")]
import destinos  # noqa: E402
import ideas_cola  # noqa: E402

TOPE = int(os.environ.get("IDEAS_TOPE_DIARIO", "5") or 5)

def compactar():
    registros = ideas_cola.leer()
    limite = (datetime.datetime.now(datetime.timezone.utc) - datetime.timedelta(days=30)).strftime("%Y-%m-%dT%H:%M:%SZ")
    viejas = {r["hash"] for r in registros if r["tipo"] == "resuelta" and str(r.get("fecha", "")) < limite and r.get("hash")}
    quedan = [r for r in registros if r.get("hash") not in viejas and not (r["tipo"] == "aviso" and str(r.get("fecha", "")) < limite)]
    ruta = ideas_cola.ruta_cola()
    tmp = ruta + ".tmp"
    fd = os.open(tmp, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
    with os.fdopen(fd, "w", encoding="utf-8") as f:
        for r in quedan:
            f.write(json.dumps(r, ensure_ascii=False, separators=(",", ":")) + "\n")
    os.replace(tmp, ruta)
    print(json.dumps({"antes": len(registros), "despues": len(quedan)}))


def main():
    p = argparse.ArgumentParser()
    sub = p.add_subparsers(dest="orden", required=True)
    a = sub.add_parser("pendientes"); a.add_argument("--sesion"); a.add_argument("--repo")
    a = sub.add_parser("resolver"); a.add_argument("hash"); a.add_argument("estado", choices=ideas_cola.ESTADOS_RESUELTA); a.add_argument("--issue")
    a = sub.add_parser("aplazar"); a.add_argument("hash"); a.add_argument("--motivo", required=True)
    a = sub.add_parser("destino"); a.add_argument("hash", nargs="+")
    a = sub.add_parser("similares"); a.add_argument("--repo", required=True); a.add_argument("--titulo", required=True)
    a = sub.add_parser("hoy"); a.add_argument("repo")
    sub.add_parser("compactar")
    args = p.parse_args()
    registros = ideas_cola.leer()
    if args.orden == "pendientes":
        lista = ideas_cola.pendientes(registros, args.sesion)
        if args.repo:
            lista = [r for r in lista if r.get("remoto") == args.repo]
        print(json.dumps(lista, ensure_ascii=False, indent=1))
    elif args.orden == "resolver":
        conocidos = {r.get("hash") for r in registros if r["tipo"] == "idea"}
        if args.hash not in conocidos:
            sys.exit("hash desconocido: " + args.hash)
        reg = {"tipo": "resuelta", "hash": args.hash, "estado": args.estado}
        if args.issue:
            reg["issue"] = args.issue
        ideas_cola.añadir(reg)
        if args.issue and args.estado in ("creada", "comentada"):
            destinos.olvidar_cache(args.issue.split("#")[0])
    elif args.orden == "destino":
        ideas = {r.get("hash"): r for r in registros if r["tipo"] == "idea"}
        desconocidos = [h for h in args.hash if h not in ideas]
        if desconocidos:
            sys.exit("hash desconocido: " + ", ".join(desconocidos))
        try:
            config = destinos.configuracion()
        except ValueError as error:
            sys.exit(str(error))
        print(json.dumps([destinos.destino(ideas[h], config) for h in args.hash], ensure_ascii=False, indent=1))
    elif args.orden == "similares":
        if not destinos.REPO.match(args.repo):
            sys.exit("repo no válido: " + args.repo)
        print(json.dumps(destinos.similares(args.repo, args.titulo), ensure_ascii=False, indent=1))
    elif args.orden == "aplazar":
        ideas_cola.añadir({"tipo": "aplazada", "hash": args.hash, "motivo": args.motivo[:200]})
    elif args.orden == "hoy":
        hoy = ideas_cola.ahora()[:10]
        n = sum(1 for r in registros if r["tipo"] == "resuelta" and r.get("estado") == "creada"
                and str(r.get("fecha", "")).startswith(hoy)
                and str(r.get("issue", "")).lower().startswith(args.repo.lower() + "#"))
        print(json.dumps({"repo": args.repo, "creados_hoy": n, "tope": TOPE, "queda": max(0, TOPE - n)}))
    elif args.orden == "compactar":
        with ideas_cola.bloqueo():
            compactar()


if __name__ == "__main__":
    main()
