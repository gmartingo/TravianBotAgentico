---
name: deferred-game-data-layer
description: La capa de datos de juego (niveles/costes/stats de edificios y tropas) está aplazada a una feature futura con scraper de kirilloid
metadata: 
  node_type: memory
  type: project
  originSessionId: 86a504b6-afa5-4d74-af61-2f20bcc1e568
---

La feature i18n-backend (spec en docs/specs/i18n-backend.md) cubre SOLO la capa de traducción: nombres de edificios/tropas por idioma + mensajes de error. Los DATOS de juego (niveles, costes de recursos, tiempos de construcción, stats de tropas) quedan FUERA de alcance y aplazados a una feature futura propia.

Fuente prevista de esos datos: un scraper a construir contra http://travian.kirilloid.ru/ (el usuario aportará el HTML de la página y explicará cómo funciona) y/o portar la lógica de los scripts del "otro bot" del usuario (funcionaban bien pero nunca definieron qué datos se recogían y cuáles no — por eso necesita su propio análisis con material delante).

**SIGUIENTE FEATURE acordada (2026-05-24):** crear el script de scraping de la web. Carga TRES cosas: tropas, edificios E IDIOMAS (las traducciones de nombres). Es decir, el scraper alimenta DOS capas: (a) el catálogo de traducciones del i18n ya construido (hoy son JSON manuales en core/i18n/catalog/base — el scraper los poblará/sustituirá automáticamente, especialmente tropas en de/fr/ru que hoy están vacías), y (b) la futura capa de datos de juego (niveles/costes/stats). Arrancar por palantir→analista cuando el usuario traiga el HTML de kirilloid.

**Why:** El usuario decidió no apresurar el esquema de datos sin tener delante el material real; el otro bot nunca definió el contrato de "qué se recoge". Y el scraper va contra un sitio TERCERO (kirilloid), no contra Travian.

**How to apply:** (1) Los objetos Building/Troop del i18n se diseñan extensibles (aditivos) para recibir esos campos luego sin romper el contrato. (2) Cuando se aborde el scraper, abrir feature nueva con su spec; el [[guardian-agent-not-invocable|guardian]] debe auditarlo porque conduce un browser/HTTP, y NO debe reutilizar la sesión/perfil de Chrome del bot de Travian (es un sitio distinto).

**Taxonomía de endpoints decidida con el usuario (2026-05-24), estilo recurso REST:** `/catalog/*` se queda como la capa LIGERA de solo-nombres (ya construida: GET /catalog/buildings, GET /catalog/troops/{tribe}). La capa de datos de juego (futura) irá en endpoints recurso propios: `GET /buildings` y `GET /buildings/{gid}`; `GET /troops/{tribe}` y `GET /troops/{tribe}/{ordinal}` — devolverán nombre traducido + datos (niveles/costes/stats). Ambas capas usan el mismo TranslationPort para el nombre; no se duplica traducción. NO meter datos de juego en /catalog (el usuario fue explícito).
