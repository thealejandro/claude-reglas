"""Pruebas aisladas del módulo: nunca invocan los CLI reales."""
import json
import os
from pathlib import Path
import subprocess
import tempfile
import threading
import time
import unittest

RAIZ = Path(__file__).resolve().parents[1]
INSTALAR = RAIZ / 'scripts/instalar-servidor.sh'


class ServidorTest(unittest.TestCase):
    def setUp(self):
        self.temporal = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporal.cleanup)
        self.home = Path(self.temporal.name)
        self.bin = self.home / 'bin'
        self.bin.mkdir()
        self.env = dict(os.environ, HOME=str(self.home), PATH=f'{self.bin}:/usr/bin:/bin')
        # Centinelas: un test falla si la simulación intenta ejecutar un CLI.
        for nombre in ('sudo', 'systemctl', 'loginctl', 'tmux', 'claude'):
            self.ejecutable(nombre, '#!/bin/bash\necho "CLI PROHIBIDO" >&2\nexit 99\n')
        self.ejecutable('getent', '#!/bin/bash\nprintf "prueba:x:1234:1234::%s:/bin/bash\\n" "$HOME"\n')

    def ejecutable(self, nombre, contenido):
        p = self.bin / nombre
        p.write_text(contenido)
        p.chmod(0o755)

    def ejecutar(self, script, *args):
        return subprocess.run(['bash', str(script), *args], env=self.env,
                              text=True, capture_output=True, timeout=10)

    def test_render_y_simulacion_sin_escrituras(self):
        antes = sorted(self.home.rglob('*'))
        r = self.ejecutar(INSTALAR, '--simular', 'prueba', 'servidor-uno')
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertEqual(antes, sorted(self.home.rglob('*')))
        self.assertIn('--name servidor-uno --spawn same-dir --capacity 16 --permission-mode auto', r.stdout)
        self.assertIn(f'PATH={self.home}/.local/bin:', r.stdout)
        for marcador in ('@PATH@', '@EQUIPO@', '/home/dev', 'DOCKER_HOST'):
            self.assertNotIn(marcador, r.stdout)
        self.assertIn('OnUnitActiveSec=15min', r.stdout)
        self.assertIn('ABIERTAS=/dev/null', r.stdout)
        self.assertIn('ExecStop=/usr/local/bin/claude-guardar-abiertas', r.stdout)
        self.assertIn('systemctl --user enable --now', r.stdout)
        self.assertIn('instalar-actualizacion.sh prueba', r.stdout)
        self.assertIn('claude-reiniciar-sesiones.timer', r.stdout)
        self.assertIn('OnCalendar=*-*-* 04:45', r.stdout)
        self.assertIn('ExecStart=/usr/local/bin/claude-reiniciar-sesiones --actualizar', r.stdout)

    def test_argumentos_invalidos(self):
        for args in ((), ('--simular',), ('--simular', 'prueba'),
                     ('--simular', '-usuario', 'equipo'),
                     ('--simular', 'prueba', 'equipo con espacios'),
                     ('--simular', 'prueba', 'equipo%h'),
                     ('--simular', 'prueba', 'equipo', 'extra')):
            with self.subTest(args=args):
                r = self.ejecutar(INSTALAR, *args)
                self.assertEqual(r.returncode, 2, r.stderr)
                self.assertNotIn('CLI PROHIBIDO', r.stderr)

    def test_actualizacion_simulada_y_argumentos(self):
        r = self.ejecutar(RAIZ / 'scripts/instalar-actualizacion.sh', '--simular', 'prueba', 'root')
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertIn('claude-actualizar-reglas@prueba.timer', r.stdout)
        self.assertIn('claude-actualizar-reglas@root.timer', r.stdout)
        self.assertIn('User=%i', r.stdout)
        self.assertIn('Persistent=true', r.stdout)
        for args in (('--simular',), ('--simular', '-x'), ('--simular', 'a b')):
            with self.subTest(args=args):
                self.assertEqual(self.ejecutar(RAIZ / 'scripts/instalar-actualizacion.sh', *args).returncode, 2)

    def test_actualizador_registra_y_falla_si_falla_claude(self):
        # El actualizador antepone ~/.local/bin al PATH: ahí va el claude falso.
        local = self.home / '.local/bin'
        local.mkdir(parents=True)
        (local / 'claude').write_text('#!/bin/bash\necho "claude $*"\n[[ $2 == update ]] && exit 1\nexit 0\n')
        (local / 'claude').chmod(0o755)
        r = self.ejecutar(RAIZ / 'scripts/actualizar/claude-actualizar-reglas')
        self.assertNotEqual(r.returncode, 0)
        registro = (self.home / '.local/state/claude-actualizar-reglas.log').read_text()
        self.assertIn('claude plugin marketplace update thealejandro', registro)
        self.assertIn('claude plugin update reglas@thealejandro', registro)

    def test_actualizador_renueva_solo_los_lanzadores_instalados(self):
        local = self.home / '.local/bin'
        local.mkdir(parents=True)
        (local / 'claude').write_text('#!/bin/bash\nexit 0\n')
        (local / 'claude').chmod(0o755)
        cache = self.home / '.claude/plugins/cache/thealejandro/reglas/9.9.9'
        for rel in ('scripts/servidor', 'scripts/actualizar'):
            (cache / rel).mkdir(parents=True)
        (cache / 'scripts/ajustes.py').write_text('')
        for rel in ('servidor/claude-arranque', 'servidor/claude-nueva-sesion', 'servidor/claude-nuevo',
                    'servidor/claude-arranque.service', 'qa-pedir', 'agente-lanzar'):
            (cache / 'scripts' / rel).write_text(f'nuevo {rel}\n')
            (cache / 'scripts' / rel).chmod(0o644)
        destino = self.home / 'destino'
        destino.mkdir()
        (destino / 'claude-arranque').write_text('viejo\n')
        (destino / 'qa-pedir').write_text('nuevo qa-pedir\n')
        (cache / 'scripts/agente-lanzar').chmod(0o666)
        (destino / 'agente-lanzar').write_text('viejo\n')
        self.env['REGLAS_DESTINO_LANZADORES'] = str(destino)
        r = self.ejecutar(RAIZ / 'scripts/actualizar/claude-actualizar-reglas')
        self.assertEqual(r.returncode, 0, r.stderr)
        registro = (self.home / '.local/state/claude-actualizar-reglas.log').read_text()
        self.assertEqual((destino / 'claude-arranque').read_text(), 'nuevo servidor/claude-arranque\n')
        self.assertEqual(os.stat(destino / 'claude-arranque').st_mode & 0o777, 0o755)
        self.assertIn('renovado', registro)
        # No instala lo que falta (avisa si es del módulo), ni unidades, ni desde un archivo escribible por otros.
        self.assertEqual(sorted(p.name for p in destino.iterdir()), ['agente-lanzar', 'claude-arranque', 'qa-pedir'])
        self.assertIn('claude-nuevo y no está instalado', registro)
        self.assertEqual((destino / 'agente-lanzar').read_text(), 'viejo\n')
        self.assertIn('no renuevo agente-lanzar', registro)
        self.assertNotIn('qa-pedir', registro)

    def test_usuario_inexistente(self):
        self.ejecutable('getent', '#!/bin/bash\nexit 2\n')
        self.assertEqual(self.ejecutar(INSTALAR, '--simular', 'nadie', 'equipo').returncode, 2)

    def test_argumentos_lanzadores(self):
        for nombre, args in (('claude-arranque', []), ('claude-nueva-sesion', []),
                             ('claude-nueva-sesion', ['--retomar']),
                             ('claude-nueva-sesion', ['', str(self.home)]),
                             ('claude-reiniciar-sesiones', ['--loquesea']),
                             ('claude-reiniciar-sesiones', ['--quietud', 'mucho'])):
            r = self.ejecutar(RAIZ / 'scripts/servidor' / nombre, *args)
            self.assertEqual(r.returncode, 2, r.stderr)
            self.assertNotIn('CLI PROHIBIDO', r.stderr)

    def test_arranque_no_duplica_vivas_ni_ids_repetidos(self):
        self.ejecutable('curl', '#!/bin/bash\nexit 0\n')
        self.ejecutable('tmux', '#!/bin/bash\n[[ $1 == has-session || $1 == list-windows ]] && exit 1\n'
                        'printf "%s\\n" "$*" >> "$HOME/tmux.log"\n')
        sesiones = self.home / '.claude/sessions'
        sesiones.mkdir(parents=True)
        (sesiones / 'viva.json').write_text(json.dumps(dict(
            pid=os.getpid(), sessionId='viva', entrypoint='sdk-cli')))
        conf = self.home / 'fijas.conf'
        conf.write_text(f'v|viva|Viva|{self.home}\na|caida|Caída|{self.home}\nb|caida|Repetida|{self.home}\n')
        r = self.ejecutar(RAIZ / 'scripts/servidor/claude-arranque', 'sesiones', str(conf))
        self.assertEqual(r.returncode, 0, r.stderr)
        llamadas = (self.home / 'tmux.log').read_text().splitlines()
        self.assertEqual(len(llamadas), 1)
        self.assertIn('--resume caida', llamadas[0])
        self.assertNotIn('--resume viva', llamadas[0])

    def test_arranque_no_duplica_ventanas_con_el_mismo_nombre(self):
        self.ejecutable('curl', '#!/bin/bash\nexit 0\n')
        # Ya hay una ventana «Ocupada»; la sesión tmux existe.
        self.ejecutable('tmux', '#!/bin/bash\n[[ $1 == has-session ]] && exit 0\n'
                        '[[ $1 == list-windows ]] && { echo Ocupada; exit 0; }\n'
                        'printf "%s\\n" "$*" >> "$HOME/tmux.log"\n')
        conf = self.home / 'fijas.conf'
        conf.write_text(f'o|vieja|Ocupada|{self.home}\nl|libre|Libre|{self.home}\nd|otra|Libre|{self.home}\n')
        r = self.ejecutar(RAIZ / 'scripts/servidor/claude-arranque', 'sesiones', str(conf))
        self.assertEqual(r.returncode, 0, r.stderr)
        llamadas = (self.home / 'tmux.log').read_text().splitlines()
        self.assertEqual(len(llamadas), 1)
        self.assertIn('--resume libre', llamadas[0])

    def test_guardar_omite_app_muertas_y_sin_conversacion(self):
        sesiones = self.home / '.claude/sessions'
        proyectos = self.home / '.claude/projects/proyecto'
        sesiones.mkdir(parents=True)
        proyectos.mkdir(parents=True)
        for i, extra in enumerate(({}, {'entrypoint': 'sdk-cli'}, {'pid': 999999999},
                                   {'kind': 'otro'}, {'sessionId': 'sin-transcripcion'})):
            datos = dict(pid=os.getpid(), kind='interactive', entrypoint='cli',
                         sessionId=str(i), name='Proyecto', cwd=str(self.home))
            datos.update(extra)
            (sesiones / f'{i}.json').write_text(json.dumps(datos))
            (proyectos / f'{i}.jsonl').write_text('{}\n')
        r = self.ejecutar(RAIZ / 'scripts/servidor/claude-guardar-abiertas')
        self.assertEqual(r.returncode, 0, r.stderr)
        lineas = (self.home / '.config/claude-arranque/abiertas.conf').read_text().splitlines()
        self.assertEqual(lineas, [f'a1|0|Proyecto|{self.home}'])

    def test_nueva_sesion_ignora_la_vieja_y_sustituye_su_linea(self):
        sesiones = self.home / '.claude/sessions'
        sesiones.mkdir(parents=True)
        vieja = dict(pid=os.getpid(), sessionId='vieja', name='Proyecto (equipo)', entrypoint='cli')
        (sesiones / 'vieja.json').write_text(json.dumps(vieja))
        # tmux falso: al abrir la ventana, la nueva sesión se registra con el mismo nombre.
        (self.home / 'nueva.json').write_text(json.dumps(dict(vieja, sessionId='nueva')))
        self.ejecutable('tmux', '#!/bin/bash\n[[ $1 == has-session || $1 == list-windows ]] && exit 1\n'
                        'cp "$HOME/nueva.json" "$HOME/.claude/sessions/nueva.json"\n')
        self.ejecutable('claude', '#!/bin/bash\nexit 0\n')
        conf = self.home / '.config/claude-arranque/sesiones.conf'
        conf.parent.mkdir(parents=True)
        conf.write_text(f'a1|vieja|Proyecto (equipo)|{self.home}\notra|x|Otra|{self.home}\n')
        r = self.ejecutar(RAIZ / 'scripts/servidor/claude-nueva-sesion', 'Proyecto (equipo)', str(self.home))
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertEqual(conf.read_text().splitlines(),
                         [f'otra|x|Otra|{self.home}', f'Proyecto-equipo|nueva|Proyecto (equipo)|{self.home}'])

    def confianza(self, *carpetas):
        proyectos = {str(c): {'hasTrustDialogAccepted': True} for c in carpetas}
        (self.home / '.claude.json').write_text(json.dumps({'projects': proyectos}))

    def test_nueva_sesion_avisa_si_la_carpeta_no_esta_aceptada(self):
        # Aceptar ~/work no cubre un repo de dentro: la confianza va por la raíz del repo.
        trabajo = self.home / 'work'
        repo = trabajo / 'repo'
        (repo / 'sub').mkdir(parents=True)
        subprocess.run(['git', 'init', '-q', str(repo)], check=True)
        self.confianza(trabajo)
        self.ejecutable('tmux', '#!/bin/bash\n[[ $1 == has-session || $1 == list-windows ]] && exit 1\n'
                        'printf "%s\\n" "$*" >> "$HOME/tmux.log"\n')
        self.ejecutable('claude', '#!/bin/bash\nexit 0\n')
        r = self.ejecutar(RAIZ / 'scripts/servidor/claude-nueva-sesion', 'Repo (equipo)', str(repo / 'sub'))
        self.assertEqual(r.returncode, 3, r.stderr)
        self.assertIn('tmux attach -t sesiones:Repo-equipo', r.stderr)
        self.assertIn('claude-nueva-sesion --registrar Repo\\ \\(equipo\\)', r.stderr)
        self.assertIn('new-session', (self.home / 'tmux.log').read_text())
        self.assertFalse((self.home / '.config/claude-arranque/sesiones.conf').exists())

    def test_confianza_por_raiz_del_repo_o_carpeta_padre(self):
        trabajo = self.home / 'work'
        repo = trabajo / 'repo'
        suelta = trabajo / 'suelta/honda'
        suelta.mkdir(parents=True)
        subprocess.run(['git', 'init', '-q', str(repo)], check=True)
        (repo / 'sub').mkdir()
        self.confianza(trabajo, repo)
        self.ejecutable('tmux', '#!/bin/bash\n[[ $1 == has-session || $1 == list-windows ]] && exit 1\n'
                        'cp "$HOME/nueva.json" "$HOME/.claude/sessions/nueva.json"\n')
        self.ejecutable('claude', '#!/bin/bash\nexit 0\n')
        (self.home / '.claude/sessions').mkdir(parents=True)
        for carpeta in (repo / 'sub', suelta):
            with self.subTest(carpeta=carpeta):
                (self.home / '.claude/sessions/nueva.json').unlink(missing_ok=True)
                (self.home / 'nueva.json').write_text(json.dumps(dict(
                    pid=os.getpid(), sessionId=carpeta.name, name='Prueba', entrypoint='cli')))
                r = self.ejecutar(RAIZ / 'scripts/servidor/claude-nueva-sesion', 'Prueba', str(carpeta))
                self.assertEqual(r.returncode, 0, r.stderr)

    def test_registrar_apunta_una_sesion_abierta_sin_relanzarla(self):
        # tmux y claude siguen siendo centinelas: --registrar no debe lanzar nada.
        sesiones = self.home / '.claude/sessions'
        sesiones.mkdir(parents=True)
        (sesiones / 'a.json').write_text(json.dumps(dict(
            pid=os.getpid(), sessionId='abierta', name='Repo (equipo)', entrypoint='cli', cwd=str(self.home))))
        r = self.ejecutar(RAIZ / 'scripts/servidor/claude-nueva-sesion', '--registrar', 'Repo (equipo)')
        self.assertEqual(r.returncode, 0, r.stderr)
        conf = self.home / '.config/claude-arranque/sesiones.conf'
        self.assertEqual(conf.read_text().splitlines(), [f'Repo-equipo|abierta|Repo (equipo)|{self.home}'])
        r = self.ejecutar(RAIZ / 'scripts/servidor/claude-nueva-sesion', '--registrar', 'Otra')
        self.assertEqual(r.returncode, 1)
        self.assertIn('No hay ninguna sesión viva', r.stderr)

    ID = '0123abcd-0123-4abc-8def-0123456789ab'
    REINICIAR = RAIZ / 'scripts/servidor/claude-reiniciar-sesiones'

    def entorno_reinicio(self, instalada='2.0.5 (Claude Code)', ventanas='@5|Proyecto', display='0|0|@5'):
        """CLIs falsos para el reinicio: tmux y claude solo registran llamadas."""
        self.env.update(REINICIAR_ESPERA_SALIDA='1', REINICIAR_ESPERA_TERM='1',
                        REINICIAR_ESPERA_RETOMA='1', REINICIAR_PAUSA='0')
        self.ejecutable('curl', '#!/bin/bash\nexit 0\n')
        self.ejecutable('claude', f'#!/bin/bash\necho "claude $*" >> "$HOME/claude.log"\n'
                        f'[[ $1 == --version ]] && echo "{instalada}"\nexit 0\n')
        self.ejecutable('tmux', f"""#!/bin/bash
printf '%s\\n' "$*" >> "$HOME/tmux.log"
case $1 in
  display-message) echo '{display}' ;;
  list-windows) [[ -e "$HOME/cerrada" ]] && exit 0
    case "$*" in *window_id*) printf '%s\\n' '{ventanas}' ;; *) echo Proyecto ;; esac ;;
  has-session) exit 0 ;;
  send-keys) [[ -e "$HOME/pid" ]] && kill "$(cat "$HOME/pid")" ;;
  kill-window) touch "$HOME/cerrada" ;;
  new-window|new-session) cp "$HOME/nueva.json" "$HOME/.claude/sessions/nueva.json" ;;
esac
exit 0
""")

    def proceso(self, orden=('sleep', '1000')):
        p = subprocess.Popen(list(orden))
        self.addCleanup(p.kill)
        threading.Thread(target=p.wait, daemon=True).start()  # sin zombis: kill -0 los vería vivos
        (self.home / 'pid').write_text(str(p.pid))
        return p

    def sesion(self, nombre, pid, **extra):
        """Escribe el json de una sesión con transcript antiguo; por defecto es candidata."""
        carpeta = self.home / '.claude/sessions'
        proyectos = self.home / '.claude/projects/p'
        carpeta.mkdir(parents=True, exist_ok=True)
        proyectos.mkdir(parents=True, exist_ok=True)
        antes = time.time() - 3600
        datos = dict(pid=pid, sessionId=self.ID, kind='interactive', entrypoint='cli', version='2.0.1',
                     status='idle', statusUpdatedAt=int(antes * 1000), tmux='sesiones:@5.%9',
                     name='Proyecto (equipo)', cwd=str(self.home))
        datos.update(extra)
        (carpeta / f'{nombre}.json').write_text(json.dumps(datos))
        transcript = proyectos / f"{datos['sessionId']}.jsonl"
        transcript.write_text('{}\n')
        os.utime(transcript, (antes, antes))
        return datos

    def test_reiniciar_simula_sin_tocar_nada(self):
        self.entorno_reinicio()
        pid = self.proceso().pid
        self.sesion('valida', pid)
        self.sesion('ocupada', pid, status='busy', sessionId='a' * 36)
        self.sesion('reciente', pid, statusUpdatedAt=int(time.time() * 1000), sessionId='b' * 36)
        self.sesion('igual', pid, version='2.0.5', sessionId='c' * 36)
        self.sesion('app', pid, entrypoint='sdk-cli', sessionId='d' * 36)
        self.sesion('sin-tmux', pid, tmux=None, sessionId='e' * 36)
        self.sesion('otra-tmux', pid, tmux='otra:@5.%9', sessionId='f' * 36)
        self.sesion('transcript-reciente', pid, sessionId='1' * 36)
        os.utime(self.home / ('.claude/projects/p/' + '1' * 36 + '.jsonl'))
        self.sesion('muerta', 999999999, sessionId='2' * 36)
        (self.home / '.claude/sessions/corrupta.json').write_text('{no es json')
        r = self.ejecutar(self.REINICIAR, '--simular')
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertEqual(r.stdout.count('reiniciaría'), 1, r.stdout)
        self.assertIn(f'reiniciaría «Proyecto (equipo)» ({self.ID}) de 2.0.1 a 2.0.5', r.stdout)
        self.assertEqual(r.stdout.count('omito'), 9, r.stdout)
        llamadas = (self.home / 'tmux.log').read_text()
        self.assertNotIn('send-keys', llamadas)
        self.assertNotIn('kill-window', llamadas)
        self.assertFalse((self.home / '.local/state/claude-reiniciar').exists())
        self.assertNotIn('update', (self.home / 'claude.log').read_text())

    def test_reiniciar_marca_cierra_y_retoma(self):
        self.entorno_reinicio()
        pid = self.proceso().pid
        datos = self.sesion('vieja', pid)
        (self.home / 'nueva.json').write_text(json.dumps(dict(datos, pid=os.getpid(), version='2.0.5')))
        r = self.ejecutar(self.REINICIAR)
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        llamadas = (self.home / 'tmux.log').read_text().splitlines()
        orden = [next(i for i, l in enumerate(llamadas) if l.startswith(p) or p in l)
                 for p in ('send-keys -t %9 /exit Enter', 'kill-window -t @5', f'--resume {self.ID}')]
        self.assertEqual(orden, sorted(orden))
        marca = json.loads((self.home / f'.local/state/claude-reiniciar/{self.ID}.json').read_text())
        self.assertEqual((marca['de'], marca['a'], marca['nombre']), ('2.0.1', '2.0.5', 'Proyecto (equipo)'))
        self.assertIn('retomada «Proyecto (equipo)»', (self.home / '.local/state/claude-reiniciar.log').read_text())
        self.assertFalse(list((self.home / '.config/claude-arranque').glob('reiniciar.conf.*')))

    def test_reiniciar_usa_sigterm_y_sigkill_si_no_sale(self):
        self.entorno_reinicio()
        self.ejecutable('tmux', '#!/bin/bash\n[[ $1 == display-message ]] && echo "0|0|@5"\n'
                        '[[ $1 == list-windows && "$*" == *window_id* ]] && echo "@5|Proyecto"\n'
                        '[[ $1 == has-session ]] && exit 1\n'
                        'printf "%s\\n" "$*" >> "$HOME/tmux.log"\nexit 0\n')
        for nombre, orden, esperado in (
                ('term', ('sleep', '1000'), 'SIGTERM'),
                ('kill', ('bash', '-c', 'trap "" TERM; while :; do sleep 1; done'), 'SIGKILL')):
            with self.subTest(nombre):
                p = self.proceso(orden)
                time.sleep(0.3)
                self.sesion('vieja', p.pid)
                r = self.ejecutar(self.REINICIAR)
                self.assertEqual(r.returncode, 1, r.stdout)  # sin retoma real: FALLO
                self.assertIn(esperado, r.stdout)
                self.assertIn(f'FALLO «Proyecto (equipo)» ({self.ID})', r.stdout)
                self.assertIn(f'claude-nueva-sesion --retomar {self.ID}', r.stdout)
                self.assertIn('kill-window', (self.home / 'tmux.log').read_text())

    def test_reiniciar_omite_con_cliente_adjunto_o_ventana_homonima(self):
        for display, ventanas in (('1|1|@5', '@5|Proyecto'), ('0|0|@5', '@5|Proyecto-equipo\n@9|Proyecto-equipo')):
            with self.subTest(display=display):
                self.entorno_reinicio(display=display, ventanas=ventanas)
                self.sesion('vieja', self.proceso().pid)
                (self.home / 'tmux.log').unlink(missing_ok=True)
                r = self.ejecutar(self.REINICIAR)
                self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
                self.assertIn('omito «Proyecto (equipo)»', r.stdout)
                self.assertNotIn('send-keys', (self.home / 'tmux.log').read_text())

    def test_reiniciar_aborta_con_version_rara(self):
        self.entorno_reinicio(instalada='rara')
        self.sesion('vieja', self.proceso().pid)
        r = self.ejecutar(self.REINICIAR)
        self.assertEqual(r.returncode, 1)
        self.assertFalse((self.home / 'tmux.log').exists())

    def test_reiniciar_actualiza_y_sigue_si_falla(self):
        self.entorno_reinicio()
        self.ejecutable('claude', '#!/bin/bash\necho "claude $*" >> "$HOME/claude.log"\n'
                        '[[ $1 == update ]] && exit 1\n[[ $1 == --version ]] && echo "2.0.5"\nexit 0\n')
        r = self.ejecutar(self.REINICIAR, '--actualizar')
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        self.assertIn('claude update falló', r.stdout)
        self.assertIn('claude update', (self.home / 'claude.log').read_text())


if __name__ == '__main__':
    unittest.main()
