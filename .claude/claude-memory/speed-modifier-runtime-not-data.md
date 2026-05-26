---
name: speed-modifier-runtime-not-data
description: "La velocidad del servidor (x1/x2/x3/x5/x10) es un modificador de tiempos en RUNTIME, no un dato a scrapear/almacenar"
metadata: 
  node_type: memory
  type: project
  originSessionId: 77687a70-a3df-46b1-9d4f-f10022f688de
---

Decisión del usuario sobre los datos de juego de kirilloid ([[deferred-game-data-layer]], [[kirilloid-scraper-gotchas]]):

El parámetro `s` de kirilloid es `{velocidad}.{versión}`: el entero = velocidad (1,2,3,5,10 = x1/x2/x3/x5/x10), el decimal = versión del juego (45=T4.5, 46=T4.6).

**La velocidad SOLO divide los tiempos** (construcción/entrenamiento): tiempo_real = tiempo_base_x1 / velocidad. Los **costes, puntos de cultura, stats y consumo NO cambian con la velocidad** — solo con la versión del juego.

**Por tanto:** se scrapea UNA sola vez a **x1** (`s=1.45` = x1 T4.5, que es lo cargado para tropas y edificios). NO se re-scrapea por velocidad. La velocidad es un **modificador en RUNTIME** (un divisor sobre los campos de tiempo) que vive en la capa API/core, NO en la carga de la BD. Aplica igual a tropas y edificios (sus `train_time_s`/`build_time_s` están en base x1).

**How to apply:** si el usuario pide una feature de "velocidad", es un parámetro de cálculo (p.ej. `?speed=3` que divide los tiempos servidos), no un cambio en el scraper ni en `building_stats`/`troop_stats`. La VERSIÓN del juego (T4.5 vs T4.6) sí es dimensión de datos (cambia edificios/costes); la velocidad no.
