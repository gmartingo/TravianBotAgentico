# Internacionalización del backend (i18n)

Documento de negocio — para stakeholders, Product Owner y responsables de producto.

Spec técnico de referencia: [`docs/specs/i18n-backend.md`](../../docs/specs/i18n-backend.md)

---

## Qué aporta esta funcionalidad

El bot de Travian tiene un dashboard de control donde el operador puede ver el estado de sus aldeas, edificios y tropas. Antes de esta funcionalidad, todos los nombres de edificios, tropas y mensajes de error llegaban al dashboard siempre en español, sin importar el idioma del operador.

Con i18n-backend, el backend puede servir esos nombres en el idioma que el operador elija. La cabecera HTTP `Accept-Language` de cada petición controla el idioma de la respuesta.

**Objetivo de negocio**: hacer el dashboard usable para operadores que no hablan español, sin duplicar la lógica de Travian en el frontend.

---

## A quién afecta

| Actor | Qué cambia |
|---|---|
| Operador humano (usa el dashboard) | Puede elegir su idioma y ver nombres de edificios y tropas localizados; los mensajes de error también llegan en su idioma |
| Desarrolladores del frontend | El campo `language` de cada item del catálogo indica exactamente qué idioma se sirvió para ese item (puede ser diferente al pedido si falta la traducción — ver fallback) |
| Desarrolladores del backend | Toda excepción del core ahora lleva un `error_code` estándar que la capa API traduce; no es necesario hardcodear mensajes de error en inglés o español en los endpoints |

---

## Idiomas soportados

| Código | Idioma | Edificios | Tropas | Mensajes de error |
|---|---|---|---|---|
| `es` | Español | Completo | Completo | Completo |
| `en` | Inglés | Completo | Completo | Completo |
| `de` | Alemán | Completo | Cae a `es` | Parcial (solo ACCOUNT_NOT_FOUND completo) |
| `fr` | Francés | Completo | Cae a `es` | Parcial (solo ACCOUNT_NOT_FOUND completo) |
| `ru` | Ruso | Completo | Cae a `es` | Parcial (solo ACCOUNT_NOT_FOUND completo) |

"Cae a `es`" significa que si el backend no tiene la traducción para ese item en ese idioma, devuelve el nombre en español como sustituto. El cliente puede detectarlo porque el campo `language` de ese item tendrá la clave `"es"` en lugar de la clave del idioma pedido.

---

## Reglas de negocio

1. **Los idiomas soportados son fijos en código**: `es`, `en`, `de`, `fr`, `ru`. Añadir o eliminar un idioma requiere un cambio en `core/i18n/languages.py`. No hay panel de administración.

2. **El idioma por defecto es español (`es`)**: si un endpoint recibe una petición sin cabecera `Accept-Language`, devuelve error 400 — no asume ningún idioma. Solo el handler de errores del sistema usa español como fallback silencioso (para no añadir complejidad cuando ya hay un error en curso).

3. **Fallback granular a español, nunca error por traducción faltante**: si falta la traducción de un edificio o tropa concreta en el idioma pedido, ese item se devuelve en español. La respuesta sigue siendo 200; el resto del catálogo se sirve en el idioma pedido. El cliente puede detectar qué items cayeron a fallback mirando la clave del campo `language`.

4. **El catálogo de edificios es global**: los edificios son los mismos para todas las tribus (el gid es único por tipo de edificio en Travian). No hay un catálogo por tribu para edificios.

5. **Las tropas se piden por tribu**: cada tribu tiene exactamente 10 tropas (posiciones del 1 al 10). Se pide el catálogo de una tribu a la vez.

6. **Las tribus válidas son**: `romans`, `teutons`, `gauls`, `egyptians`, `huns`. Pedir una tribu fuera de esta lista devuelve error 422 automáticamente.

7. **Los nombres traducidos son solo para mostrar al humano**: no se usan para navegar por Travian. Los selectores del browser del bot siempre usan identificadores técnicos (gid de edificio, clases CSS). Un nombre traducido que cambia entre versiones del juego no rompe el bot.

8. **El catálogo se versionan en git**: añadir o corregir traducciones es un cambio de código, no una operación de base de datos. Los archivos viven en `core/i18n/catalog/`.

9. **Los mensajes de error se traducen por su código, no por su texto**: cada tipo de error tiene un código interno (ej. `ACCOUNT_NOT_FOUND`). El catálogo `messages.json` tiene la plantilla en cada idioma. Esto desacopla el idioma del código del dominio.

10. **Los errores de sistema (500) llegan siempre en el idioma del cliente**: antes, un error interno llegaba con el texto en español hardcodeado. Ahora el handler global lo traduce con la misma lógica que cualquier otro error.

---

## Qué queda fuera de esta funcionalidad

Los siguientes elementos gestionan su propia traducción de forma independiente y no están afectados por i18n-backend:

- Textos del propio dashboard (menús, botones, etiquetas de formularios). Eso es i18n del frontend, gestionado por React.
- Niveles de edificios, costes de recursos y tiempos de construcción. Solo se implementa la capa de nombres; los datos numéricos del juego van en una feature futura.
- Edición del catálogo de traducciones a través de la API. El catálogo es de solo lectura desde la API.

---

## Cómo sabe el cliente qué idioma se usó en cada item

El campo `language` de cada item en la respuesta del catálogo tiene como clave el idioma realmente servido. Si el cliente pide `Accept-Language: de` y un edificio no tiene traducción en alemán, ese item llega con `"language": {"es": "Leñador"}` en lugar de `"language": {"de": "..."}`. El cliente puede filtrar estos items para saber qué traducciones faltan.

Ejemplo de respuesta con fallback mixto:
```json
{
  "buildings": [
    {"gid": 1, "alias": "woodcutter", "language": {"de": "Holzfäller"}},
    {"gid": 999, "alias": "unknown",  "language": {"es": "building_999"}}
  ]
}
```

---

## Divergencias con la planificación original

Durante la implementación, el equipo completó las traducciones de edificios en alemán, francés y ruso, lo que estaba fuera del alcance planificado. El spec original declaraba que esos idiomas tendrían el catálogo vacío en la primera iteración. El resultado es más completo de lo previsto.

Las traducciones de tropas en `de`, `fr` y `ru` sí quedaron pendientes tal como se planificó.

---

🔖 Última revisión: 2026-05-24
