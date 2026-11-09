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
3. Lenguaje visual (de anuncios de Apple, Linear, Notion, Raycast, Arc y Stripe, revisados fotograma a fotograma en 2026-11):
   - **Una idea por plano**: 2–4 palabras en pantalla («Prompt it.», «Select it.», «Cloud Sync»), nunca frases largas sobre la interfaz. Los textos van solos sobre fondo limpio o encima del producto, no los dos compitiendo.
   - Fondo neutro (negro, blanco o un degradado suave de la marca) y **el producto grande**: UI a tamaño legible, inclinada en perspectiva 3D o con zoom a la parte que importa (Linear, Raycast); la ventana completa y diminuta no vende.
   - Ritmo sostenido: un plano cada ~1–2 s; texto cinético que entra palabra a palabra con el pulso.
   - Si encaja, contexto humano (Notion: la persona usando el producto con la UI flotando encima).
   - Cierre: nombre + frase de marca de 3–5 palabras («Linear. At your command.», «For your life's work.») + logo, a menudo con precio o URL. Pocos elementos.
4. Idiomas: textos en pantalla parametrizados (prop `lang`); renderiza **es y en**. La web usa la versión de su idioma; los README, la inglesa.

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
- Arreglo minimalista, no un tema sonando de principio a fin: trocea por compases respetando la progresión, estira ≤ 4 % para que los golpes caigan en su fotograma, **silencios** de 1–2 pulsos antes de los momentos clave, volumen por escena.

### Nada de «tono de fondo» (error repetido; el usuario lo detecta enseguida)

En los anuncios de producto de referencia la música **no es un colchón**: es rítmica, seca y va en primer plano, y se **para en seco** en los golpes de texto. Lo que suena a «tono de fondo» es lo sostenido: pads, cuerdas largas, notas pedal, colas de reverb, acordes que se apagan durante segundos, tonos senoidales y golpes graves sintetizados, y la música filtrada (pasa-bajos) que deja solo un zumbido grave.

- Elige pistas **de ataques** (percusión, pizzicato, piano o sintes cortos, bajo rítmico), no ambient, cinematográficas ni de cuerdas. Descarta las que en el espectrograma muestran bandas horizontales continuas en 80–500 Hz.
- **Cortes a silencio digital** de 0,2–1 s sincronizados con los cambios de texto o de plano: 1–4 cada 30 s (Apple Creator Studio, Raycast). Corte seco, sin reverb que rellene el hueco.
- Para bajar la energía, **quita instrumentos o para la música**; no la escondas con pasa-bajos ni bajando el volumen bajo un zumbido.
- Final: termina en un golpe (*button*) o en silencio sobre el logo; nada de acordes de 5–6 s apagándose.
- Si la pista elegida es de colchón, cambia de pista en vez de maquillarla.
- La prueba de oro: en todo momento hay **algo en primer plano** (ritmo, melodía o voz). Un fondo sostenido es aceptable si algo con forma va encima (Vercel, Shopify, Copilot); un zumbido sin forma, nunca.
- Suave, no ensordecedor: ataques redondos, percusión discreta, nada de golpes graves ni chasquidos agresivos.
- Comprobación orientativa (§6): `perfil-audio.py`. No es un aprobado/suspenso: sirve para comparar con las referencias y con el oído del usuario.

- Crédito obligatorio en: README, notas de la release y la página web donde se muestre el vídeo.

## 5. Efectos de sonido

- Síntesis propia en el script de audio (código del repo → MIT) o packs CC0 (Kenney). Sin packs con atribución dudosa.
- Los efectos suenan **a la interfaz**, no a sintetizador: clics de ratón y teclado, *toggles*, un *pop* corto al aparecer una tarjeta, todo seco y < 150 ms, en el fotograma exacto en que se ve la acción (si llega tarde, se nota).
- Pocos: un sonido de héroe solo en el momento clave; los repetidos, cortos y variados para que no cansen ([Material Design](https://m2.material.io/design/sound/applying-sound-to-ui.html)). Si un sonido no aporta información ni emoción, silencio.
- **Prohibido** añadir tonos senoidales sostenidos, *drones*, golpes graves (sub) en cada corte o envíos de reverb largos: son justo el «tono de fondo» de §4. Un golpe grave, como mucho uno y solo si la música no lo trae.
- Niveles orientativos: clics 20–30 dB bajo la música; soplidos (si hay) 25–35 dB.

## 6. Mezcla y verificación (Claude no puede escuchar)

- Objetivo: **−16 LUFS** integrado (web/YouTube) y **−14 LUFS** para Reels; pico real ≤ −1 dBTP; LRA ~7–9 LU (contraste entre partes suaves y fuertes).
- Comprueba siempre, sobre el MP4 final:
  ```bash
  ffmpeg -nostats -i out/video.mp4 -af ebur128=peak=true -f null - 2>&1 | grep -E '^\s+(I|LRA|Peak):'
  ffmpeg -v error -y -i out/video.mp4 -lavfi showspectrumpic=s=1920x600:legend=1 espectrograma.png
  ```
  y mira el espectrograma (clics, zumbidos, silencios limpios) y la sincronía de los ataques (±1 fotograma).
- **Compara con referencias**: baja 2–3 anuncios oficiales de producto recientes (con OK del usuario; `yt-dlp -f "bv*[height<=720][ext=mp4]+ba[ext=m4a]"` a una carpeta temporal, solo para analizar, nunca al repo) y pasa los dos por `python3 <skill>/scripts/perfil-audio.py out/video.mp4 ref1.mp4 ref2.mp4`. Medido en 2026-11 sobre 35 anuncios: la modulación en 80–500 Hz va de 4,6 dB (Shopify) a 26 dB (Notion) y los huecos de 0 a 12 (GitHub), así que **la cifra sola no decide**. El reel de xaSeguros v1 (10 dB, 1 hueco) estaba dentro del rango; lo que fallaba era el timbre: cuerdas sostenidas + tonos y sub sintetizados + reverb, sin nada en primer plano. Mira los espectrogramas uno encima de otro y deja el veredicto al oído del usuario.
- Mosaico de las referencias (`tile=5x3`) para comparar también el lenguaje visual (§1.3).
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

## Fuentes (sonido y lenguaje visual)

- Análisis propio (2026-11) de 35 anuncios oficiales: Apple, Linear, Notion, Arc, Raycast, Stripe, Google (Pixel 10, Gemini), Microsoft (Copilot, Surface), Samsung, Shopify, Vercel, GitHub, Figma, Framer, Canva, Dropbox, Duolingo, Anthropic (Claude) y OpenAI (ChatGPT). Unos 14 llevan voz en off; con voz, la música va debajo; sin voz, la música rítmica + efectos de interfaz lleva el anuncio.
- Cada marca tiene un **concepto visual propio**, no solo capturas: Shopify (collage de pintura clásica), Duolingo (personajes), Surface (tonos cálidos, manos), Copilot (interfaz de cristal sobre personas), Gemini/GitHub (UI brillante sobre negro azulado), Vercel (blanco mínimo), Anthropic (objetos analógicos y cine cálido, tipografía con serifa), OpenAI (vida cotidiana con texto encima, punto y blanco). Define el de la marca antes del guion y no copies el de otra.
- [Material Design — Applying sound to UI](https://m2.material.io/design/sound/applying-sound-to-ui.html): sonidos de héroe escasos, el silencio cuenta tanto como el sonido.
- [IRPR — Spotting music cues](https://sounddesign.irpr.agency/guides/how-to-spot-music-cues-with-a-composer/): la música «de pared a pared» sin plan compite con el diseño sonoro y cansa; decide dónde no suena.
- Olsen, *Journal of Advertising* (1995): cortar a silencio justo antes del mensaje clave mejora el recuerdo frente a música de fondo continua.
- [IRPR — Launch films](https://sounddesign.irpr.agency/applications/launch-films/) y [XO3D — Sound design for product films](https://xo3d.co.uk/guides/sound-design-product-films/): anticipación → sonido de héroe en la revelación; el silencio transmite confianza.
