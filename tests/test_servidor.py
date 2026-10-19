"""Pruebas aisladas del módulo: nunca invocan los CLI reales."""
import json
import os
from pathlib import Path
import subprocess
import tempfile
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

    def test_usuario_inexistente(self):
        self.ejecutable('getent', '#!/bin/bash\nexit 2\n')
        self.assertEqual(self.ejecutar(INSTALAR, '--simular', 'nadie', 'equipo').returncode, 2)

    def test_argumentos_lanzadores(self):
        for nombre, args in (('claude-arranque', []), ('claude-nueva-sesion', []),
                             ('claude-nueva-sesion', ['--retomar']),
                             ('claude-nueva-sesion', ['', str(self.home)])):
            r = self.ejecutar(RAIZ / 'scripts/servidor' / nombre, *args)
            self.assertEqual(r.returncode, 2, r.stderr)
            self.assertNotIn('CLI PROHIBIDO', r.stderr)

    def test_arranque_no_duplica_vivas_ni_ids_repetidos(self):
        self.ejecutable('curl', '#!/bin/bash\nexit 0\n')
        self.ejecutable('tmux', '#!/bin/bash\n[[ $1 == has-session ]] && exit 1\nprintf "%s\\n" "$*" >> "$HOME/tmux.log"\n')
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


if __name__ == '__main__':
    unittest.main()
