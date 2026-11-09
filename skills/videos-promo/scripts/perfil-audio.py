#!/usr/bin/env python3
"""Perfil del sonido de uno o varios vídeos, para comparar el nuestro con anuncios de referencia.

    python3 perfil-audio.py out/video.mp4 [referencia1.mp4 ...]

Solo necesita ffmpeg y numpy. Por cada vídeo imprime:
  - huecos: cortes a casi silencio (≥ 100 ms a −35 dB del nivel alto). Los anuncios de software de
    referencia tienen 1–4 cada 30 s, en los golpes de texto; 0–1 suena a «tema de fondo».
  - modulación 80–500 Hz: mediana de (p90 − p10) del nivel de esa banda en ventanas de 2 s.
    Pocos dB = un colchón sostenido (pads, cuerdas, reverb, acorde largo) = el «tono de fondo».
    Referencias rítmicas: 13–26 dB. Por debajo de ~10 dB, revisa música y efectos tonales.
  - perfil: una barra por segundo del nivel relativo (para ver respiros y el final).
"""
import subprocess
import sys

import numpy as np
from numpy.lib.stride_tricks import sliding_window_view as sw

SR, N, H = 16000, 800, 400  # ventana 50 ms, paso 25 ms


def perfil(path: str) -> None:
    raw = subprocess.run(['ffmpeg', '-v', 'error', '-i', path, '-ac', '1', '-ar', str(SR), '-f', 'f32le', '-'],
                         capture_output=True, check=True).stdout
    x = np.frombuffer(raw, np.float32)
    X = np.abs(np.fft.rfft(sw(x, N)[::H] * np.hanning(N), axis=1)) ** 2
    fq = np.fft.rfftfreq(N, 1 / SR)

    def band(a, b):
        return 10 * np.log10(X[:, (fq >= a) & (fq < b)].sum(1) + 1e-10)

    rel = band(20, 8000)
    rel -= np.percentile(rel, 90)
    huecos, run = 0, 0
    for v in rel:
        run = run + 1 if v < -35 else 0
        huecos += run == 4
    lm, seg = band(80, 500), 80
    mod = np.median([np.percentile(lm[i:i + seg], 90) - np.percentile(lm[i:i + seg], 10)
                     for i in range(0, max(1, len(lm) - seg), seg)])
    barras = ''.join(' ▁▂▃▄▅▆▇█'[int(np.clip((rel[i:i + 40].max() + 40) / 40 * 8, 0, 8))]
                     for i in range(0, len(rel), 40))
    print(f'{path}\n  {len(x) / SR:.0f} s · huecos {huecos} · modulación 80–500 Hz {mod:.1f} dB\n  {barras}')


if __name__ == '__main__':
    if len(sys.argv) < 2:
        sys.exit(__doc__)
    for p in sys.argv[1:]:
        perfil(p)
