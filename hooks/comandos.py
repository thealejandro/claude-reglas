"""Lectura de comandos de shell para anti-filtraciones: qué git y gh se ejecutan, dónde y con qué texto.

No ejecuta nada del comando. Interpreta lo suficiente de la sintaxis de bash para saber en qué
carpeta actúa cada `git` o `gh` y qué contiene el texto que se va a publicar. Lo que no se puede
saber de antemano queda como desconocido (None) y decide quien llama.
"""
import os
import re
import stat

MAX_BODY = 1024 * 1024
MAX_VALOR = 4 * MAX_BODY
MAX_NIVEL = 25
MAX_CARPETAS = 8
MAX_PENDIENTES = 64
MAX_RUTA = 4096

TUBERIA = ("|", "|&")
OPERADORES = (";;&", ";;", ";&", "&&", "||", "|&", ";", "&", "|")
REDIRECCIONES = ("&>>", "<<<", "<<-", "&>", "<<", ">>", "<&", ">&", "<>", ">|", "<", ">")
ENTRADA = ("<", "<<", "<<-", "<<<")
SALIDA = (">", ">>", ">|", "&>", "&>>")
RESERVADAS = {"if", "then", "else", "elif", "fi", "do", "done", "while", "until", "!", "{", "}", "coproc"}
ABREN_BLOQUE = {"if", "while", "until", "for", "select", "case"}
CIERRAN_BLOQUE = {"fi", "done", "esac"}
FIN_DE_CASO = (";;", ";&", ";;&")
EN_CADENA = ("&&",) + TUBERIA
FUNCION = "función"  # marca en el guion: lo que sigue es el cuerpo de una función
VARIABLE_CON_DEFECTO = re.compile(r"^([A-Za-z_]\w*)(:?)-(.*)$", re.DOTALL)
LLAVES = re.compile(r"\{[^{}]*(?:,|\.\.)[^{}]*\}")
ENVOLTORIOS = {"command", "builtin", "exec", "nohup", "env", "sudo", "doas", "nice", "ionice", "time",
               "timeout", "stdbuf", "setsid", "xargs", "chronic", "unbuffer"}
SHELLS = {"bash", "sh", "zsh", "dash", "ksh"}
ENTRADA_ESTANDAR = ("-", "/dev/stdin", "/dev/fd/0")
GH_VERBOS = {"create", "new", "comment", "edit", "review"}
# Opciones cortas de gh que llevan valor: de ellas depende dónde acaba un grupo como -abc.
GH_CON_VALOR = {"comment": "bFR", "review": "bFR"}
GH_CON_VALOR_RESTO = "abBFHlmprRtT"
# Tramos sin nada especial: se leen de una vez (carácter a carácter, un cuerpo largo agota el tiempo).
EN_PALABRA = re.compile(r"[^ \t\r\n;&|()<>\\'\"`$]+")
EN_DOBLES = re.compile(r'[^"\\`$]+')
EN_HEREDOC = re.compile(r"[^\\`$]+")
GH_URL = re.compile(r"^https?://([\w.-]+)/([\w.-]+/[\w.-]+)/(?:issues|pull)/")
ASIGNACION = re.compile(r"^([A-Za-z_]\w*)(\+?)=")
NOMBRE = re.compile(r"[A-Za-z_]\w*")


class ErrorLectura(Exception):
    pass


class Parte:
    def __init__(self, tipo, texto="", guion=None, citada=False):
        self.tipo = tipo      # lit, var, sub, proc, arit, lista
        self.texto = texto    # literal, nombre de variable o texto original
        self.guion = guion    # comandos de $(...), `...`, <(...) o x=(...)
        self.citada = citada


class Palabra:
    def __init__(self, partes):
        self.partes = partes

    def prefijo(self):
        """Texto literal con el que empieza la palabra."""
        trozos = []
        for parte in self.partes:
            if parte.tipo != "lit":
                break
            trozos.append(parte.texto)
        return "".join(trozos)

    def es_literal(self):
        return all(parte.tipo == "lit" for parte in self.partes)

    def tras(self, cuantos):
        """La palabra sin sus `cuantos` primeros caracteres literales."""
        partes = []
        for parte in self.partes:
            if cuantos and parte.tipo == "lit":
                quitar = min(cuantos, len(parte.texto))
                cuantos -= quitar
                if quitar < len(parte.texto):
                    partes.append(Parte("lit", parte.texto[quitar:], citada=parte.citada))
            else:
                partes.append(parte)
        return Palabra(partes)

    def visible(self):
        return "".join("$" + parte.texto if parte.tipo == "var" else parte.texto for parte in self.partes)


class Redireccion:
    def __init__(self, operador, descriptor, destino):
        self.operador = operador
        self.descriptor = descriptor
        self.destino = destino
        self.cuerpo = Palabra([])  # solo en heredocs


class Orden:
    def __init__(self, fuente, anterior):
        self.fuente = fuente
        self.palabras = []
        self.redirecciones = []
        self.tramos = []
        self.antes = anterior
        self.despues = ""
        self.previa = None  # orden que alimenta su entrada por una tubería


class Lector:
    def __init__(self, texto, nivel=0):
        self.s = texto
        self.i = 0
        self.nivel = nivel

    def guion(self, cierre=False):
        """Lista de órdenes y paréntesis. Con `cierre`, termina en el `)` que abrió la sustitución."""
        self.nivel += 1
        if self.nivel > MAX_NIVEL:
            raise ErrorLectura("demasiado anidado")
        s = self.s
        elementos = []
        pendientes = []
        orden = None
        anterior = ""
        previa = None
        abiertos = 0

        def terminar(operador):
            nonlocal orden, anterior, previa
            if orden is not None:
                orden.despues = operador
                previa = orden if operador in TUBERIA else None
                orden = None
                anterior = operador
            elif operador != "\n":
                anterior = operador

        def actual(inicio):
            nonlocal orden
            if orden is None:
                orden = Orden(s, anterior)
                orden.previa = previa
                orden.tramos.append([inicio, inicio])
                elementos.append(orden)
            return orden

        while self.i < len(s):
            c = s[self.i]
            if c in " \t\r":
                self.i += 1
            elif s.startswith("\\\n", self.i):
                self.i += 2
            elif c == "#":
                fin = s.find("\n", self.i)
                self.i = len(s) if fin < 0 else fin
            elif c == "\n":
                terminar("\n")
                self.i += 1
                self._heredocs(pendientes, cierre)
            elif c in ";&|" and not s.startswith("&>", self.i):
                operador = next(op for op in OPERADORES if s.startswith(op, self.i))
                terminar(operador)
                self.i += len(operador)
            elif c == "(":
                if orden is None and s.startswith("((", self.i):
                    self._aritmetica(1)
                elif orden is None:
                    elementos.append("(")
                    abiertos += 1
                    self.i += 1
                elif orden.palabras and orden.palabras[-1].visible().endswith("="):
                    self.i += 1
                    orden.palabras[-1].partes.append(Parte("lista", guion=self.guion(cierre=True)))
                    orden.tramos[0][1] = self.i
                else:
                    self.i += 1
                    resto = re.compile(r"[ \t]*\)").match(s, self.i)
                    if resto:  # definición de función: el cuerpo se lee como órdenes normales
                        self.i = resto.end()
                        elementos.remove(orden)
                        elementos.append(FUNCION)
                        orden = None
                    else:
                        terminar(";")
                        elementos.append("(")
                        abiertos += 1
            elif c == ")":
                terminar(")")
                self.i += 1
                if abiertos:
                    abiertos -= 1
                    elementos.append(")")
                elif cierre:
                    self.nivel -= 1
                    return elementos
            elif (c in "<>" and not s.startswith("(", self.i + 1)) or s.startswith("&>", self.i):
                self._redireccion(actual(self.i), "", pendientes)
            else:
                inicio = self.i
                palabra = self.palabra()
                crudo = s[inicio:self.i]
                if crudo.isdigit() and s[self.i:self.i + 1] in ("<", ">") and not s.startswith("(", self.i + 1):
                    self._redireccion(actual(inicio), crudo, pendientes)
                else:
                    destino = actual(inicio)
                    destino.palabras.append(palabra)
                    destino.tramos[0][1] = self.i
        if cierre:
            raise ErrorLectura("sustitución sin cerrar")
        terminar("")
        self.nivel -= 1
        return elementos

    def _redireccion(self, orden, descriptor, pendientes):
        s = self.s
        operador = next(op for op in REDIRECCIONES if s.startswith(op, self.i))
        self.i += len(operador)
        while s[self.i:self.i + 1] in (" ", "\t"):
            self.i += 1
        inicio = self.i
        destino = self.palabra()
        redireccion = Redireccion(operador, descriptor, destino)
        orden.redirecciones.append(redireccion)
        orden.tramos[0][1] = self.i
        if operador in ("<<", "<<-"):
            crudo = s[inicio:self.i]
            citado = any(marca in crudo for marca in "'\"\\")
            pendientes.append((orden, redireccion, destino.visible(), citado))

    def _heredocs(self, pendientes, cierre):
        s = self.s
        for orden, redireccion, fin_de_texto, citado in pendientes:
            inicio = self.i
            lineas = []
            while self.i < len(s):
                fin = s.find("\n", self.i)
                fin = len(s) if fin < 0 else fin
                linea = s[self.i:fin]
                limpia = linea.lstrip("\t") if redireccion.operador == "<<-" else linea
                if limpia == fin_de_texto:
                    self.i = fin + 1
                    break
                if cierre and fin_de_texto and limpia.startswith(fin_de_texto) \
                        and limpia[len(fin_de_texto):].lstrip().startswith(")"):
                    self.i += linea.index(fin_de_texto) + len(fin_de_texto)
                    break
                lineas.append(limpia + "\n")
                self.i = fin + 1
            cuerpo = "".join(lineas)
            orden.tramos.append([inicio, min(self.i, len(s))])
            if citado:
                redireccion.cuerpo = Palabra([Parte("lit", cuerpo, citada=True)])
            else:
                redireccion.cuerpo = Lector(cuerpo, self.nivel).texto_expandible()
        del pendientes[:]

    def palabra(self):
        s = self.s
        partes = []
        while self.i < len(s):
            c = s[self.i]
            if c in " \t\r\n;&|()":
                break
            if c in "<>":
                if not s.startswith("(", self.i + 1):
                    break
                inicio = self.i
                self.i += 2
                guion = self.guion(cierre=True)
                partes.append(Parte("proc", s[inicio:self.i], guion))
            elif c == "\\":
                siguiente = s[self.i + 1:self.i + 2]
                if siguiente != "\n":
                    self._literal(partes, siguiente, True)
                self.i += 2
            elif c == "'":
                fin = s.find("'", self.i + 1)
                if fin < 0:
                    raise ErrorLectura("comillas sin cerrar")
                self._literal(partes, s[self.i + 1:fin], True)
                self.i = fin + 1
            elif c == '"':
                self._dobles(partes)
            elif c == "`":
                self._invertidas(partes)
            elif c == "$":
                self._dolar(partes, False)
            else:
                trozo = EN_PALABRA.match(s, self.i).group()
                self._literal(partes, trozo, False)
                self.i += len(trozo)
        return Palabra(partes)

    def texto_expandible(self):
        """Cuerpo de un heredoc sin comillas: expande `$` y comillas invertidas."""
        s = self.s
        partes = []
        while self.i < len(s):
            c = s[self.i]
            if c == "\\" and s[self.i + 1:self.i + 2] in ("$", "`", "\\", "\n"):
                if s[self.i + 1] != "\n":
                    self._literal(partes, s[self.i + 1], True)
                self.i += 2
            elif c == "`":
                self._invertidas(partes)
            elif c == "$":
                self._dolar(partes, True)
            else:
                encaja = EN_HEREDOC.match(s, self.i)
                trozo = encaja.group() if encaja else c
                self._literal(partes, trozo, True)
                self.i += len(trozo)
        return Palabra(partes)

    @staticmethod
    def _literal(partes, texto, citada):
        ultima = partes[-1] if partes else None
        if ultima and ultima.tipo == "lit" and ultima.citada == citada:
            ultima.texto += texto
        else:
            partes.append(Parte("lit", texto, citada=citada))

    def _dobles(self, partes):
        s = self.s
        self.i += 1
        self._literal(partes, "", True)
        while self.i < len(s):
            c = s[self.i]
            if c == '"':
                self.i += 1
                return
            if c == "\\" and s[self.i + 1:self.i + 2] in ("$", "`", '"', "\\", "\n"):
                if s[self.i + 1] != "\n":
                    self._literal(partes, s[self.i + 1], True)
                self.i += 2
            elif c == "`":
                self._invertidas(partes)
            elif c == "$":
                self._dolar(partes, True)
            else:
                encaja = EN_DOBLES.match(s, self.i)
                trozo = encaja.group() if encaja else c
                self._literal(partes, trozo, True)
                self.i += len(trozo)
        raise ErrorLectura("comillas sin cerrar")

    def _invertidas(self, partes):
        s = self.s
        inicio = self.i
        self.i += 1
        while self.i < len(s) and s[self.i] != "`":
            self.i += 2 if s[self.i] == "\\" else 1
        if self.i >= len(s):
            raise ErrorLectura("comillas invertidas sin cerrar")
        interior = re.sub(r"\\([`\\$])", r"\1", s[inicio + 1:self.i])
        self.i += 1
        partes.append(Parte("sub", s[inicio:self.i], Lector(interior, self.nivel).guion()))

    def _aritmetica(self, salto):
        """Avanza hasta cerrar el paréntesis que empieza `salto - 1` caracteres más allá."""
        s = self.s
        abiertos = 0
        self.i += salto - 1
        while self.i < len(s):
            abiertos += {"(": 1, ")": -1}.get(s[self.i], 0)
            self.i += 1
            if not abiertos:
                return
        raise ErrorLectura("paréntesis sin cerrar")

    def _dolar(self, partes, citada):
        s = self.s
        inicio = self.i
        siguiente = s[self.i + 1:self.i + 2]
        if s.startswith("$((", self.i):
            self._aritmetica(2)
            partes.append(Parte("arit", s[inicio:self.i]))
        elif siguiente == "(":
            self.i += 2
            guion = self.guion(cierre=True)
            partes.append(Parte("sub", s[inicio:self.i], guion))
        elif siguiente == "{":
            abiertos = 0
            self.i += 1
            while self.i < len(s):
                abiertos += {"{": 1, "}": -1}.get(s[self.i], 0)
                self.i += 1
                if not abiertos:
                    break
            if abiertos:
                raise ErrorLectura("llave sin cerrar")
            partes.append(Parte("var", s[inicio + 2:self.i - 1]))
        elif siguiente == "'" and not citada:
            fin = self.i + 2
            while fin < len(s) and s[fin] != "'":
                fin += 2 if s[fin] == "\\" else 1
            if fin >= len(s):
                raise ErrorLectura("comillas sin cerrar")
            escapes = {"n": "\n", "t": "\t", "r": "\r"}
            texto = re.sub(r"\\(.)", lambda m: escapes.get(m.group(1), m.group(1)), s[self.i + 2:fin])
            self._literal(partes, texto, True)
            self.i = fin + 1
        elif siguiente == '"' and not citada:
            self.i += 1
            self._dobles(partes)
        else:
            nombre = NOMBRE.match(s, self.i + 1)
            if nombre:
                partes.append(Parte("var", nombre.group()))
                self.i = nombre.end()
            elif siguiente and siguiente in "0123456789?#@*$!-":
                partes.append(Parte("var", siguiente))
                self.i += 2
            else:
                self._literal(partes, "$", citada)
                self.i += 1


class Entorno:
    def __init__(self, carpeta, variables=None, pila=None, comun=None, dudosas=None):
        self.carpeta = carpeta
        self.variables = dict(variables or {})
        self.pila = list(pila or [])  # pushd: [(carpeta, dudosas)]
        # Lo que sobrevive a un subshell: ficheros escritos y si se ha creado algún repo.
        self.comun = comun if comun is not None else {"ficheros": {}, "repo_nuevo": False}
        # Un `cd` que quizá no ocurra: mientras se sabe que sí (misma cadena `&&`, mismo bloque) queda
        # pendiente; después, las carpetas anteriores pasan a ser también posibles.
        self.dudosas = list(dudosas or [])
        self.pendientes = []  # [(sigue la cadena &&, nivel de bloque, carpetas anteriores)]
        self.bloque = 0
        self.llaves = []      # por cada `{` abierta, si cuenta como bloque
        self.funcion = False  # la próxima `{` abre el cuerpo de una función

    def copia(self):
        return Entorno(self.carpeta, self.variables, self.pila, self.comun, self.dudosas)

    def posibles(self, carpetas):
        """Añade carpetas en las que también se puede acabar."""
        for carpeta in carpetas:
            if carpeta != self.carpeta and carpeta not in self.dudosas and len(self.dudosas) < MAX_CARPETAS:
                self.dudosas.append(carpeta)

    def activar(self, condicion):
        quedan = []
        for pendiente in self.pendientes:
            if condicion(*pendiente[:2]):
                self.posibles(pendiente[2])
            else:
                quedan.append(pendiente)
        self.pendientes = quedan


class Git:
    def __init__(self, suborden, carpeta, argumentos, variables, repo_nuevo, directa,
                 alternativas=(), escritos=None):
        self.suborden = suborden
        self.directa = directa        # la suborden va justo detrás de `git`, sin opciones globales
        self.carpeta = carpeta        # None: no se puede saber
        self.argumentos = argumentos  # [(Palabra, texto o None)]
        self.variables = variables    # GIT_DIR y GIT_WORK_TREE
        self.repo_nuevo = repo_nuevo  # el comando crea o clona un repo antes
        self.alternativas = list(alternativas)  # otras carpetas en las que también puede actuar
        self.escritos = escritos or {}  # ficheros que el comando escribe antes: ruta -> contenido o None


class Gh:
    def __init__(self, carpeta, tramos):
        self.carpeta = carpeta
        self.alternativas = []
        self.tramos = tramos          # posiciones de la orden en el comando original
        self.repo = None              # None: el de la carpeta
        self.repo_desconocido = False
        self.textos = []              # título y cuerpo ya leídos
        self.ilegible = False


def tiene_llaves(palabra):
    """`{a,b}` o `{1..3}` sin comillas: la shell lo convierte en varios argumentos."""
    return bool(LLAVES.search("".join(p.texto for p in palabra.partes if p.tipo == "lit" and not p.citada)))


def unir(carpeta, ruta):
    if ruta is None:
        return None
    if os.path.isabs(ruta):
        return ruta
    if carpeta is None:
        return None
    return os.path.join(carpeta, ruta) if ruta else carpeta


class Analisis:
    def __init__(self, comando, raiz):
        self.comando = comando
        self.raiz = raiz  # función carpeta -> raíz del repo (o None)
        self.git = []
        self.gh = []

    # --- Valores que se pueden conocer sin ejecutar nada ---

    def valor(self, entorno, nombre):
        con_defecto = VARIABLE_CON_DEFECTO.match(nombre)
        if con_defecto:
            return self.valor_con_defecto(entorno, *con_defecto.groups())
        if nombre == "PWD":
            return entorno.carpeta
        if nombre in entorno.variables:
            return entorno.variables[nombre]
        # El OLDPWD del hook no es el de la shell: solo se sabe si lo fija un `cd` del comando.
        return None if nombre == "OLDPWD" else os.environ.get(nombre)

    def valor_con_defecto(self, entorno, nombre, dos_puntos, defecto):
        """`${X:-d}` y `${X-d}`; solo si el valor por defecto es texto sin más expansiones."""
        valor = self.valor(entorno, nombre)
        if valor is None and (nombre in entorno.variables or nombre in ("PWD", "OLDPWD")):
            return None
        if valor is None or (dos_puntos and not valor):
            if any(marca in defecto for marca in "$`'\"\\"):
                return None
            return os.path.expanduser(defecto)
        return valor

    def expandir(self, palabra, entorno, nivel=0):
        if nivel > MAX_NIVEL:
            raise ErrorLectura("demasiado anidado")
        trozos = []
        largo = 0
        for indice, parte in enumerate(palabra.partes):
            if parte.tipo == "lit":
                texto = parte.texto
                if not indice and not parte.citada and (texto == "~" or texto.startswith("~/")):
                    texto = os.path.expanduser(texto)
            elif parte.tipo == "var":
                texto = self.valor(entorno, parte.texto)
            elif parte.tipo == "sub":
                texto = self.salida(parte.guion, entorno.copia(), nivel + 1)
                texto = None if texto is None else texto.rstrip("\n")
            elif parte.tipo == "arit":
                texto = "0"
            else:
                texto = None
            if texto is None:
                return None
            largo += len(texto)
            if largo > MAX_VALOR:
                return None
            trozos.append(texto)
        return "".join(trozos)

    def leer(self, palabra, entorno):
        """Contenido del fichero que nombra `palabra`, o None si no se puede saber."""
        if len(palabra.partes) == 1 and palabra.partes[0].tipo == "proc":
            return self.salida(palabra.partes[0].guion, entorno.copia())
        ficheros = entorno.comun["ficheros"]
        ruta = self.expandir(palabra, entorno)
        if ruta is None:
            return ficheros.get(palabra.visible())
        completa = unir(entorno.carpeta, ruta)
        if completa is None:
            return None
        completa = os.path.normpath(completa)
        if completa in ficheros:
            return ficheros[completa]
        return leer_fichero(completa)

    def entrada(self, orden, entorno, nivel=0):
        for redireccion in reversed(orden.redirecciones):
            if redireccion.operador not in ENTRADA or redireccion.descriptor not in ("", "0"):
                continue
            if redireccion.operador == "<":
                return self.leer(redireccion.destino, entorno)
            if redireccion.operador == "<<<":
                texto = self.expandir(redireccion.destino, entorno, nivel)
                return None if texto is None else texto + "\n"
            return self.expandir(redireccion.cuerpo, entorno, nivel)
        if orden.previa is not None:
            return self.salida_de_orden(orden.previa, entorno, nivel + 1)
        return None

    def salida(self, guion, entorno, nivel=0):
        """Lo que escribiría un `$(...)` formado por cat, echo, printf y poco más."""
        trozos = []
        for orden in guion:
            if not isinstance(orden, Orden) or orden.despues in TUBERIA:
                continue
            palabras = self.sin_prefijos(orden)[1]
            if palabras and palabras[0].visible() == "cd":
                self.cambiar_carpeta("cd", palabras[1:], orden, entorno)
                continue
            texto = self.salida_de_orden(orden, entorno, nivel)
            if texto is None:
                return None
            trozos.append(texto)
        return "".join(trozos)

    def salida_de_orden(self, orden, entorno, nivel=0):
        if nivel > MAX_NIVEL:
            raise ErrorLectura("demasiado anidado")
        palabras = self.sin_prefijos(orden)[1]
        if not palabras:
            return self.entrada(orden, entorno, nivel) if any(
                r.operador == "<" for r in orden.redirecciones) else ""
        nombre = os.path.basename(self.expandir(palabras[0], entorno, nivel) or "")
        argumentos = palabras[1:]
        textos = [self.expandir(palabra, entorno, nivel) for palabra in argumentos]
        if nombre == "cat":
            trozos = []
            ficheros = 0
            for palabra, texto in zip(argumentos, textos):
                if texto == "--":
                    continue
                if texto is not None and texto.startswith("-") and texto != "-":
                    return None
                ficheros += 1
                if texto in ENTRADA_ESTANDAR:
                    trozos.append(self.entrada(orden, entorno, nivel))
                else:
                    trozos.append(self.leer(palabra, entorno))
            if not ficheros:
                return self.entrada(orden, entorno, nivel)
            if any(trozo is None for trozo in trozos) or sum(map(len, trozos)) > MAX_VALOR:
                return None
            return "".join(trozos)
        if nombre in ("echo", "printf"):
            while textos and textos[0] in (("-n", "-e", "-E") if nombre == "echo" else ("--",)):
                textos = textos[1:]
            if any(texto is None for texto in textos):
                return None
            return (" " if nombre == "echo" else "\n").join(textos) + "\n"
        if nombre in ("true", ":"):
            return ""
        if nombre == "pwd":
            return entorno.carpeta
        if nombre == "git":
            carpeta = entorno.carpeta
            while len(textos) > 1 and textos[0] == "-C":
                carpeta = unir(carpeta, textos[1])
                textos = textos[2:]
            if textos in (["branch", "--show-current"], ["rev-parse", "--abbrev-ref", "HEAD"]):
                return "HEAD\n"
            if textos == ["rev-parse", "--show-toplevel"] and carpeta is not None:
                raiz = self.raiz(carpeta)
                return None if raiz is None else raiz + "\n"
        return None

    # --- Recorrido del comando ---

    def sin_prefijos(self, orden):
        """([(nombre, añade, valor)], palabras) sin palabras reservadas ni asignaciones delante."""
        palabras = orden.palabras
        inicio = 0
        while inicio < len(palabras) and palabras[inicio].es_literal() and palabras[inicio].visible() in RESERVADAS:
            inicio += 1
        asignaciones = []
        while inicio < len(palabras):
            asignacion = self.asignacion(palabras[inicio])
            if not asignacion:
                break
            asignaciones.append(asignacion)
            inicio += 1
        return asignaciones, palabras[inicio:]

    @staticmethod
    def asignacion(palabra):
        if not palabra.partes or palabra.partes[0].tipo != "lit" or palabra.partes[0].citada:
            return None
        encaja = ASIGNACION.match(palabra.partes[0].texto)
        if not encaja:
            return None
        return encaja.group(1), bool(encaja.group(2)), palabra.tras(encaja.end())

    def asignar(self, asignaciones, entorno):
        for nombre, añade, palabra in asignaciones:
            texto = self.expandir(palabra, entorno)
            if añade:
                previo = self.valor(entorno, nombre) or ""
                texto = None if texto is None or len(previo) + len(texto) > MAX_VALOR else previo + texto
            entorno.variables[nombre] = texto

    def recorrer(self, guion, entorno, nivel=0):
        if nivel > MAX_NIVEL:
            raise ErrorLectura("demasiado anidado")
        pila = []
        for orden in guion:
            if orden == "(":
                pila.append((entorno.carpeta, dict(entorno.variables), list(entorno.pila),
                             list(entorno.dudosas), list(entorno.pendientes)))
                entorno.funcion = False
            elif orden == ")":
                if pila:
                    (entorno.carpeta, entorno.variables, entorno.pila,
                     entorno.dudosas, entorno.pendientes) = pila.pop()
            elif orden == FUNCION:
                entorno.funcion = True
            else:
                self.bloques(orden, entorno)
                self.sustituciones(orden, entorno, nivel)
                self.ejecutar(orden, entorno, nivel)
                self.escrituras(orden, entorno)

    def bloques(self, orden, entorno):
        """Sigue las cadenas `&&` y los bloques para saber qué `cd` han ocurrido seguro."""
        if orden.antes not in EN_CADENA:
            entorno.activar(lambda cadena, bloque: cadena)
        if orden.antes in FIN_DE_CASO:
            entorno.activar(lambda cadena, bloque: bloque >= entorno.bloque)
        palabras = orden.palabras
        indice = 0
        while indice < len(palabras) and palabras[indice].es_literal():
            palabra = palabras[indice].visible()
            if palabra in ("else", "elif"):
                entorno.activar(lambda cadena, bloque: bloque >= entorno.bloque)
            elif palabra in ABREN_BLOQUE:
                entorno.bloque += 1
            elif palabra in CIERRAN_BLOQUE:
                self.cerrar_bloque(entorno)
            elif palabra == "function":
                entorno.funcion = True
                indice += 1  # su nombre
            elif palabra == "{":
                es_bloque = entorno.funcion or orden.antes in EN_CADENA + ("||",)
                entorno.llaves.append(es_bloque)
                entorno.bloque += es_bloque
                entorno.funcion = False
            elif palabra == "}":
                if entorno.llaves and entorno.llaves.pop():
                    self.cerrar_bloque(entorno)
            elif palabra not in RESERVADAS:
                break
            if palabra in ("for", "select", "case"):
                break
            indice += 1

    @staticmethod
    def cerrar_bloque(entorno):
        entorno.bloque = max(0, entorno.bloque - 1)
        entorno.activar(lambda cadena, bloque: bloque > entorno.bloque)

    def sustituciones(self, orden, entorno, nivel):
        """Los `$(...)` y `<(...)` se ejecutan antes que la orden, cada uno en su subshell."""
        palabras = list(orden.palabras)
        for redireccion in orden.redirecciones:
            palabras += [redireccion.destino, redireccion.cuerpo]
        for palabra in palabras:
            for parte in palabra.partes:
                if parte.tipo == "lista":  # los elementos de x=(...) no son órdenes
                    for elemento in parte.guion:
                        if isinstance(elemento, Orden):
                            self.sustituciones(elemento, entorno, nivel + 1)
                elif parte.guion is not None:
                    self.recorrer(parte.guion, entorno.copia(), nivel + 1)

    def escrituras(self, orden, entorno):
        destinos = [(r.destino, r.operador in (">>", "&>>"), None) for r in orden.redirecciones
                    if r.operador in SALIDA and r.descriptor in ("", "1")]
        palabras = self.sin_prefijos(orden)[1]
        if palabras and palabras[0].visible() == "tee":
            añade = any(p.visible() in ("-a", "--append") for p in palabras[1:])
            destinos += [(p, añade, "tee") for p in palabras[1:] if not p.visible().startswith("-")]
        ficheros = entorno.comun["ficheros"]
        for palabra, añade, origen in destinos:
            ruta = self.expandir(palabra, entorno)
            if ruta is not None:
                ruta = unir(entorno.carpeta, ruta)
                if ruta is None or ruta.startswith("/dev/"):
                    continue
                ruta = os.path.normpath(ruta)
            clave = ruta if ruta is not None else palabra.visible()
            texto = self.entrada(orden, entorno) if origen else self.salida_de_orden(orden, entorno)
            if añade:
                if clave in ficheros:
                    previo = ficheros[clave]
                elif ruta is not None and os.path.exists(ruta):
                    previo = leer_fichero(ruta)
                else:
                    previo = ""
                texto = None if texto is None or previo is None or len(previo) + len(texto) > MAX_VALOR \
                    else previo + texto
            ficheros[clave] = texto

    def cambiar_carpeta(self, nombre, argumentos, orden, entorno):
        # En una tubería o en segundo plano el cambio no sale de su subshell; tras `||` es el caso de error.
        if orden.antes in TUBERIA + ("||",) or orden.despues in TUBERIA + ("&",):
            return
        textos = [self.expandir(palabra, entorno) for palabra in argumentos]
        while textos and textos[0] in ("-L", "-P", "-e", "-@", "--", "-n"):
            textos = textos[1:]
        anteriores = [entorno.carpeta, *entorno.dudosas]
        if nombre == "popd":
            destino = entorno.pila.pop() if entorno.pila and not textos else (None, [])
            nuevas = [destino[0], *destino[1]]
        else:
            if not textos:
                destino = os.environ.get("HOME") if nombre == "cd" else None
            else:
                destino = textos[0]
                if destino == "-" and nombre == "cd":
                    destino = entorno.variables.get("OLDPWD")
                elif destino is not None and destino.startswith(("-", "+")):
                    destino = None
            nuevas = []
            for anterior in anteriores:
                nueva = None if destino is None else unir(anterior, destino)
                nuevas.append(None if nueva is None or len(nueva) > MAX_RUTA else os.path.normpath(nueva))
        if nombre == "pushd":
            entorno.pila.append((entorno.carpeta, list(entorno.dudosas)))
        entorno.variables["OLDPWD"] = entorno.carpeta
        entorno.carpeta = nuevas[0]
        entorno.dudosas = []
        entorno.posibles(nuevas[1:])
        if orden.antes == "&&" or entorno.bloque:
            if len(entorno.pendientes) < MAX_PENDIENTES:
                entorno.pendientes.append((orden.antes == "&&", entorno.bloque, anteriores))
            else:
                entorno.posibles(anteriores)

    def ejecutar(self, orden, entorno, nivel):
        asignaciones, palabras = self.sin_prefijos(orden)
        if not palabras:
            self.asignar(asignaciones, entorno)
            return
        propio = entorno.copia()  # las asignaciones delante de una orden solo valen para ella
        self.asignar(asignaciones, propio)
        temporales = {nombre: propio.variables[nombre] for nombre, _, _ in asignaciones}
        nombre = os.path.basename(self.expandir(palabras[0], entorno) or "")
        carpeta = entorno.carpeta
        alternativas = list(entorno.dudosas)
        if nombre in ENVOLTORIOS:
            buscadas = {"git", "gh", "cd", "eval"} | SHELLS
            for indice in range(1, len(palabras)):
                if os.path.basename(palabras[indice].visible()) in buscadas:
                    saltadas = palabras[1:indice]
                    for palabra in saltadas:
                        asignacion = self.asignacion(palabra)
                        if asignacion:
                            temporales[asignacion[0]] = self.expandir(asignacion[2], entorno)
                    if nombre in ("env", "sudo", "doas") and any(
                            p.visible().startswith(("-C", "-D", "--chdir")) for p in saltadas):
                        carpeta = None
                        alternativas = []
                    resto = palabras[indice:]
                    if nombre == "xargs" and os.path.basename(resto[0].visible()) == "git":
                        resto = resto + [Palabra([Parte("xargs")])]  # argumentos que llegan por la entrada
                    palabras = resto
                    nombre = os.path.basename(palabras[0].visible())
                    break
        argumentos = palabras[1:]
        if nombre in ("export", "declare", "typeset", "local", "readonly"):
            self.asignar([a for a in map(self.asignacion, argumentos) if a], entorno)
        elif nombre in ("unset", "read", "mapfile", "readarray"):
            for palabra in argumentos:
                if NOMBRE.fullmatch(palabra.visible()):
                    entorno.variables[palabra.visible()] = None
        elif nombre in ("for", "select"):
            if argumentos:
                entorno.variables[argumentos[0].visible()] = None
        elif nombre in ("cd", "pushd", "popd"):
            self.cambiar_carpeta(nombre, argumentos, orden, entorno)
        elif nombre in SHELLS:
            self.shell(orden, argumentos, entorno, (carpeta, alternativas), temporales, nivel)
        elif nombre == "eval":
            texto = " ".join(self.texto_de_guion(p, entorno) for p in argumentos)
            self.recorrer(Lector(texto, nivel).guion(), entorno, nivel + 1)
        elif nombre == "git":
            self.anotar_git(argumentos, entorno, (carpeta, alternativas), temporales)
        elif nombre == "gh":
            self.anotar_gh(orden, argumentos, entorno, (carpeta, alternativas), temporales)

    def texto_de_guion(self, palabra, entorno):
        texto = self.expandir(palabra, entorno)
        return palabra.visible() if texto is None else texto

    def shell(self, orden, argumentos, entorno, lugar, temporales, nivel):
        con_c = False
        indice = 0
        while indice < len(argumentos):
            texto = argumentos[indice].visible()
            if not texto.startswith(("-", "+")) or texto == "--":
                break
            if not texto.startswith("--"):
                con_c = con_c or "c" in texto
                if texto.endswith(("o", "O")):
                    indice += 1
            indice += 1
        if indice < len(argumentos) and argumentos[indice].visible() == "--":
            indice += 1
        if con_c and indice < len(argumentos):
            guion = self.texto_de_guion(argumentos[indice], entorno)
        elif not con_c and indice >= len(argumentos):
            guion = self.entrada(orden, entorno)
        else:
            return
        if guion is None:
            return
        hijo = entorno.copia()
        hijo.carpeta, hijo.dudosas = lugar
        hijo.variables.update(temporales)
        self.recorrer(Lector(guion, nivel).guion(), hijo, nivel + 1)

    def anotar_git(self, argumentos, entorno, lugar, temporales):
        carpeta, alternativas = lugar
        variables = {}
        for nombre in ("GIT_DIR", "GIT_WORK_TREE"):
            if nombre in temporales or nombre in entorno.variables:
                variables[nombre] = temporales.get(nombre, entorno.variables.get(nombre))
        indice = 0
        while indice < len(argumentos):
            palabra = argumentos[indice]
            opcion = palabra.prefijo()
            if not opcion.startswith("-"):
                break
            siguiente = argumentos[indice + 1] if indice + 1 < len(argumentos) else None
            valor = None if siguiente is None else self.expandir(siguiente, entorno)
            if opcion == "-C":
                carpeta = unir(carpeta, valor)
                alternativas = [unir(alternativa, valor) for alternativa in alternativas]
                indice += 1
            elif opcion in ("--git-dir", "--work-tree"):
                variables["GIT_DIR" if opcion == "--git-dir" else "GIT_WORK_TREE"] = valor
                indice += 1
            elif opcion in ("-c", "--namespace", "--config-env"):
                indice += 1
            else:
                for larga, nombre in (("--git-dir=", "GIT_DIR"), ("--work-tree=", "GIT_WORK_TREE")):
                    if opcion.startswith(larga):
                        variables[nombre] = self.expandir(palabra.tras(len(larga)), entorno)
            indice += 1
        if indice >= len(argumentos):
            return
        suborden = self.expandir(argumentos[indice], entorno)
        if suborden in ("init", "clone"):
            entorno.comun["repo_nuevo"] = True
        if suborden not in ("commit", "push", "add", "stage"):
            return
        for nombre, valor in list(variables.items()):
            variables[nombre] = unir(carpeta, valor)
            if variables[nombre] is None:
                carpeta = None
        resto = [(p, None if tiene_llaves(p) else self.expandir(p, entorno)) for p in argumentos[indice + 1:]]
        if variables:
            alternativas = []
        self.git.append(Git(suborden, carpeta, resto, variables, entorno.comun["repo_nuevo"], not indice,
                            alternativas, dict(entorno.comun["ficheros"])))

    def anotar_gh(self, orden, argumentos, entorno, lugar, temporales):
        carpeta, alternativas = lugar
        gh = Gh(carpeta, orden.tramos if orden.fuente is self.comando else [])
        gh.alternativas = alternativas
        grupo = verbo = url = repo = None
        cuerpos = []
        indice = 0
        while indice < len(argumentos):
            palabra = argumentos[indice]
            opcion = palabra.prefijo()
            siguiente = argumentos[indice + 1] if indice + 1 < len(argumentos) else None
            if opcion.startswith("--"):
                nombre, igual, _ = opcion.partition("=")
                if nombre in ("--repo", "--body", "--title", "--body-file"):
                    valor = palabra.tras(len(nombre) + 1) if igual else siguiente
                    indice += 0 if igual else 1
                    if nombre == "--repo":
                        repo = valor
                    elif valor is not None:
                        cuerpos.append((nombre == "--body-file", valor))
            elif opcion.startswith("-") and len(opcion) > 1:
                con_valor = GH_CON_VALOR.get(verbo, GH_CON_VALOR_RESTO) if verbo else "R"
                for posicion in range(1, len(opcion)):
                    letra = opcion[posicion]
                    if letra not in con_valor:
                        continue
                    pegado = palabra.tras(posicion + 1)
                    if pegado.prefijo().startswith("="):
                        pegado = pegado.tras(1)
                    if not pegado.partes:
                        pegado = siguiente
                        indice += 1
                    if letra == "R":
                        repo = pegado
                    elif letra in "bFt" and pegado is not None:
                        cuerpos.append((letra == "F", pegado))
                    break
            else:
                texto = self.expandir(palabra, entorno)
                if grupo is None:
                    if texto not in ("issue", "pr"):
                        return
                    grupo = texto
                elif verbo is None:
                    if texto not in GH_VERBOS:
                        return
                    verbo = texto
                elif texto:
                    encaja = GH_URL.match(texto)
                    if encaja and verbo not in ("create", "new"):
                        url = encaja.group(1) + "/" + encaja.group(2)
            indice += 1
        if verbo is None:
            return
        if url:
            gh.repo = url
        elif repo is not None:
            gh.repo = self.expandir(repo, entorno)
            gh.repo_desconocido = gh.repo is None
        elif "GH_REPO" in temporales or "GH_REPO" in entorno.variables:
            gh.repo = temporales.get("GH_REPO", entorno.variables.get("GH_REPO"))
            gh.repo_desconocido = gh.repo is None
        else:
            gh.repo = os.environ.get("GH_REPO") or None
        propio = entorno.copia()
        propio.carpeta = carpeta
        for es_fichero, palabra in cuerpos:
            if not es_fichero:
                texto = self.expandir(palabra, propio)
            elif self.expandir(palabra, propio) in ENTRADA_ESTANDAR:
                texto = self.entrada(orden, propio)
            else:
                texto = self.leer(palabra, propio)
            if texto is None:
                gh.ilegible = True
            else:
                gh.textos.append(texto)
        self.gh.append(gh)


def leer_fichero(ruta):
    """Texto de un fichero normal de tamaño razonable; None si no lo es o no se puede abrir."""
    try:
        datos = os.stat(ruta)
        if not stat.S_ISREG(datos.st_mode) or datos.st_size > MAX_BODY:
            return None
        with open(ruta, encoding="utf-8", errors="replace") as fichero:
            return fichero.read(MAX_BODY)
    except (OSError, ValueError):
        return None


def analizar(comando, carpeta, raiz):
    """Los `git` y `gh` que ejecuta `comando` desde `carpeta`."""
    analisis = Analisis(comando, raiz)
    analisis.recorrer(Lector(comando).guion(), Entorno(carpeta))
    return analisis
