---
name: videos-promo
description: Flujo para hacer o mejorar vídeos promocionales de thealejandro (anuncios de producto, reels de Instagram, historias, estados de WhatsApp, demos para la web o los README) con Remotion. Úsala siempre que se hable de un vídeo promocional, reel, demo en vídeo, música o sonido de un vídeo, render, o de subir vídeos a una release o a la web. Cubre guion y ritmo, marca, grabación del escritorio, música con licencia que no suene a IA, efectos, mezcla y su verificación, formatos por plataforma y publicación.
---

# Vídeos promocionales

Objetivo: anuncios de nivel profesional, al estilo de las presentaciones de Apple, que **no parezcan ni suenen hechos con IA**. Todo en español con el usuario.

Referencias que mandan sobre esta skill (léelas al empezar):
- Runbook del vídeo: carpeta `omarchy-promo/` del repo de runbooks (opción `repo_runbooks` del plugin): `RUNBOOK.md` (decisiones y flujo) y `mejoras-2026-11/INFORME.md` (informe de mejoras con fuentes).
- Proyecto de referencia: repo `thealejandro/omarchy-promo` (README: estructura, sonido, licencias).
- Técnica de Remotion: skills oficiales del proyecto en `.agents/skills/` (empieza por `remotion-best-practices`). En un proyecto nuevo: `npx remotion skills add` (pide OK al usuario: es una descarga).
- Marca: el `MARCA.md` del canal (manda §0) y sus logotipos, en la carpeta de diseño del usuario, **solo lectura**: copia al proyecto lo que necesites. Si no está en esta máquina, usa los logotipos ya copiados en `omarchy-promo/public/` o en `thealejandro/portfolio`.

**Si falta algún repo en esta máquina, clónalo tú sin preguntar** (es solo lectura): `gh repo clone <owner>/<repo>` por HTTPS en el directorio de trabajo donde estén los demás repos, o `git -C <repo> pull` si ya existe. Si `gh` no tiene sesión, dile al usuario el comando exacto (`gh auth login`). La grabación del escritorio (§3) solo aplica en un equipo con Omarchy.

## 1. Antes de programar

1. Pregunta solo lo que no puedas deducir: producto, plataforma(s), idioma(s), duración, llamada a la acción.
2. Guion en tiempos (tabla escena → segundos → texto en pantalla → qué se ve → qué suena). Reglas:
   - **Gancho en el fotograma 0**: producto en movimiento a sangre + golpe de sonido. Nunca texto sobre negro al empezar.
   - Duraciones: reel 25–30 s, horizontal ~60 s, historia ≤ 15 s por pieza.
   - **Enseñar el producto en uso** (grabaciones reales, cámara que sigue la acción) antes que capturas estáticas.
   - Sin fundidos a negro entre escenas: cortes en los golpes de música y continuidad de objeto (`TransitionSeries`, capa persistente).
   - **Una sola llamada a la acción** al final (URL o «enlace en el perfil») + firma, ~5 s.
3. Idiomas: textos en pantalla parametrizados (prop `lang`); renderiza **es y en**. La web usa la versión de su idioma; los README, la inglesa.

## 2. Marca

- Firma al cierre con el logotipo de thealejandro (Gafas, MARCA §0). Sobre fondo oscuro: montura loza y disco `#7f98f5`; **sobre claro, nunca la lente cobalto-claro**: usa mono oscuro.
- Paleta AZULEJO: esmalte `#0e0c0b`, loza `#f4ecdc`, cobalto `#2648c8`, lente `#7f98f5`. Tres colores por pieza como máximo.
- Si aparece el retrato: crédito «Retrato: @SC.ASTRO».
- Tipografía con licencia libre incluida en el repo con su OFL (en omarchy-promo: Inter y JetBrains Mono).

## 3. Grabar el escritorio

- Siempre en un escritorio aparte (el 9) y **con OK del usuario antes de grabar**: dile qué se graba, cuánto dura y que no toque ratón ni teclado.
- Sin datos personales: una carpeta de proyecto falsa (autor `demo`), btop con `net_iface = "lo"`, «no molestar» activado durante la toma, sin ubicación del clima, cierra notificaciones antes (`qs ipc -p /usr/share/omarchy/shell/shell.qml call notifications dismissAll`).
- `trap` que restaure tema, fondo, barra, escritorio y «no molestar» tal como estaban. Nunca tocar `/usr/share/omarchy`.
- Herramientas: `gpu-screen-recorder` (o `omarchy capture`, ver la skill `omarchy`/`capture.md`); `ydotool` para mover el cursor. Ejemplos: `scripts/capture-clips.sh` de `omarchy-promo` y `omarchy-themes/herramientas/capture-extras.sh` del repo de runbooks.

## 4. Música (que no suene a IA)

- **Prohibido**: voces sintéticas, música generada por IA, pads genéricos sintetizados a mano y pistas cuya página declare herramientas de IA (el crédito CC BY enlaza a esa página).
- Fuentes válidas, con licencia que permita uso comercial y crédito: Kevin MacLeod / incompetech (CC BY 4.0), compositores con catálogo propio revisado. Comprueba la licencia **en la página de la pista** y guarda URL + texto de crédito.
- Antes de descargar: pide OK al usuario (nombre, origen, tamaño); a una carpeta nueva y vacía; nunca ejecutes nada descargado.
- Arreglo minimalista, no un tema sonando de principio a fin: trocea por compases respetando la progresión, estira ≤ 4 % para que los golpes caigan en su fotograma, **silencios** de 1–2 pulsos antes de los momentos clave, filtrado y volumen por escena (se apaga en los respiros, se abre en los clímax), final con acorde que se apaga.
- Crédito obligatorio en: README, notas de la release y la página web donde se muestre el vídeo.

## 5. Efectos de sonido

- Síntesis propia en el script de audio (código del repo → MIT) o packs CC0 (Kenney). Sin packs con atribución dudosa.
- Discretos y a fotograma: tic por elemento que aparece, soplido solo en transiciones grandes (pocos), golpe grave en los cortes clave, tono suave para el producto (p. ej. la isla al abrirse).
- Niveles orientativos: ticks y soplidos 20–40 dB bajo la música; tonos ~16–19 dB; golpes graves casi al nivel pero en el sub.

## 6. Mezcla y verificación (Claude no puede escuchar)

- Objetivo: **−16 LUFS** integrado (web/YouTube) y **−14 LUFS** para Reels; pico real ≤ −1 dBTP; LRA ~7–9 LU (contraste entre partes suaves y fuertes).
- Comprueba siempre, sobre el MP4 final:
  ```bash
  ffmpeg -nostats -i out/video.mp4 -af ebur128=peak=true -f null - 2>&1 | grep -E '^\s+(I|LRA|Peak):'
  ffmpeg -v error -y -i out/video.mp4 -lavfi showspectrumpic=s=1920x600:legend=1 espectrograma.png
  ```
  y mira el espectrograma (clics, zumbidos, silencios limpios) y la sincronía de los ataques (±1 fotograma).
- Mosaico de fotogramas para revisar imagen: `ffmpeg -i out/video.mp4 -vf "fps=1/2,scale=480:-1,tile=5x3" mosaico.png`; míralo con Read.
- **El usuario aprueba de oído**: envíale el vídeo (SendUserFile) y pide que lo escuche con auriculares antes de mergear.

## 7. Formatos

| Destino | Formato | Notas |
|---|---|---|
| Reel / historia / estado | 1080×1920, 30–60 fps, < 25 MB para el móvil | Zonas libres: 14 % arriba, 35 % abajo, 6 % lados. Texto ≥ 40 px. Portada pensada para el recorte 3:4. Subir con nuestra música como «audio original». |
| Horizontal | 1920×1080 | Release de GitHub y YouTube. |
| Web | 720p (`media="(max-width: 1024px)"`) y 1440p, WebM (VP9 crf ~30) + MP4 (H.264 crf ~18–24), `preload="none"` + póster | Sin opción de descarga si el usuario no la quiere. Mide nitidez a 2K, no solo a 1080p. |
| README | GIF o MP4 corto en inglés | |

## 8. Repo y publicación

- Repo nuevo: público con licencia (MIT para el código; la música y las fuentes con la suya; logotipo y nombre excluidos de la MIT), Dependabot y escaneo de secretos.
- Trabaja en rama y PR; commits con la skill `reglas:commit`. Nada de merges, releases ni push a `main`/`master` sin el resumen de producción y el OK del usuario.
- Publicar: `gh release upload <tag> out/*.mp4 --clobber` (o release nueva) con el crédito de la música en las notas, y PR en `thealejandro/portfolio` (`public/omarchy/`, `src/components/omarchy/media.ts`).
- Actualiza el runbook del proyecto en el repo de runbooks con decisiones nuevas.
- Limpieza al terminar: renders intermedios, copias sin audio obsoletas, fotogramas y temporales.
