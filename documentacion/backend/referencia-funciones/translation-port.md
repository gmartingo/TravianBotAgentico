# Referencia de funciones — TranslationPort y JsonTranslationAdapter

Módulos: `core/ports/translation_port.py`, `adapters/translations/json_translation_adapter.py`

---

## `TranslationPort` (interfaz abstracta)

Clase base abstracta (`ABC`). El core solo depende de esta interfaz; nunca importa `JsonTranslationAdapter` directamente.

---

### `get_building_name(gid: int, lang: str) -> str`

**Qué hace**: devuelve el nombre del edificio identificado por `gid` en el idioma `lang`.

**Entradas**:
- `gid`: identificador numérico del edificio (ej. `1` = Leñador, `15` = Cuartel). Los gids son estables en Travian.
- `lang`: código de idioma de dos letras (`es`, `en`, `de`, `fr`, `ru`).

**Salida**: nombre como `str`. Nunca `None`, nunca lanza excepción.

**Comportamiento de fallback**:
1. Si `entry[lang]` existe y no está vacío → devuelve ese nombre.
2. Si no → devuelve `entry["es"]` (fallback a español).
3. Si tampoco hay español → devuelve `f"building_{gid}"` (fallback defensivo).
4. Si `gid` no existe en el catálogo → devuelve `f"building_{gid}"` directamente.

**Por qué existe**: permite a cualquier parte del core obtener el nombre de un edificio en el idioma del usuario sin acoplarse a archivos JSON.

**Impacto en negocio**: esta función es para mostrar nombres al humano (dashboard). NUNCA para construir selectores del browser de Travian.

---

### `get_all_buildings(lang: str) -> list[dict]`

**Qué hace**: devuelve todos los edificios del catálogo con el idioma realmente servido por cada item.

**Entradas**: `lang` — código de idioma.

**Salida**: lista de dicts con estructura:
```python
{
    "gid": int,
    "alias": str,       # identificador semántico legible (ej. "woodcutter")
    "lang_servido": str, # idioma real usado — puede diferir de lang por fallback
    "nombre": str
}
```

**Por qué devuelve `lang_servido` en vez de simplemente el nombre**: el router necesita construir el campo `language: {idioma_servido: nombre}` del DTO de respuesta. Si el adaptador solo devolviera el nombre, el router no sabría qué clave usar en el mapa. El `lang_servido` permite que el cliente detecte item a item qué entradas aún no tienen traducción en su idioma.

**Impacto en negocio**: regla de negocio 6 del spec — el catálogo de edificios es global (no por tribu), por lo que esta función devuelve todos los gids sin filtrar.

---

### `get_troop_name(tribe: Tribe, ordinal: int, lang: str) -> str`

**Qué hace**: devuelve el nombre de la tropa en la posición `ordinal` de la `tribe`.

**Entradas**:
- `tribe`: valor del enum `Tribe` (`ROMANS`, `TEUTONS`, `GAULS`, `EGYPTIANS`, `HUNS`).
- `ordinal`: posición de la tropa en su tribu, base 1 (ej. `1` = primera tropa).
- `lang`: código de idioma.

**Salida**: nombre como `str`. Nunca lanza excepción por idioma faltante.

**Lanza `TroopNotFoundError`** si la clave `"{TRIBE}_{ordinal}"` no existe en el catálogo (ordinal fuera de rango para esa tribu).

**Implementación** (`JsonTranslationAdapter`):
```python
key = f"{tribe.value.upper()}_{ordinal}"  # ej. "ROMANS_1"
entry = self._troops.get(key)
if entry is None:
    raise TroopNotFoundError(tribe=tribe, ordinal=ordinal)
```

**Impacto en negocio**: regla de negocio 7 del spec — la clave es `{TRIBE_ENUM_VALUE_UPPER}_{ordinal}`.

---

### `get_troop_names_by_tribe(tribe: Tribe, lang: str) -> list[dict]`

**Qué hace**: devuelve todas las tropas de una tribu con el idioma realmente servido por cada item.

**Entradas**: `tribe`, `lang`.

**Salida**: lista de dicts con estructura:
```python
{
    "ordinal": int,
    "key": str,         # ej. "ROMANS_1"
    "lang_servido": str,
    "nombre": str
}
```
La lista está ordenada por `ordinal` ascendente.

**Lanza `TroopNotFoundError`** (con `ordinal=None`) si la tribu no tiene ninguna entrada en el catálogo.

**Implementación** (`JsonTranslationAdapter`): filtra `self._troops` por prefijo `"{TRIBE}_"`, ordena por el número tras el último `_`:
```python
sorted(entries.items(), key=lambda kv: int(kv[0].split("_")[-1]))
```

**Impacto en negocio**: permite al dashboard mostrar la lista completa de tropas de una tribu en el idioma del operador.

---

### `get_message(code: str, lang: str, **params) -> str`

**Qué hace**: devuelve el mensaje de error localizado para el código `code`, con los `params` interpolados.

**Entradas**:
- `code`: `error_code` de la excepción (ej. `"ACCOUNT_NOT_FOUND"`).
- `lang`: código de idioma.
- `**params`: valores para interpolar (ej. `account_id=42`).

**Salida**: `str`. Nunca lanza excepción.

**Comportamiento**:
1. Si `code` no está en el catálogo → devuelve `f"{code} {params}"` (aviso de catálogo incompleto).
2. Si la plantilla del idioma existe y no está vacía → interpola con `.format(**params)`.
3. Si falta para `lang` → usa plantilla en `es`.
4. Si tampoco hay `es` → devuelve `f"{code} {params}"`.
5. Si `.format(**params)` falla por `KeyError` (params incompletos) → devuelve la plantilla sin interpolar.

**Por qué existe**: desacopla el dominio (que lanza excepciones agnósticas de idioma) de la capa HTTP (que necesita mensajes localizados para el cliente).

---

## `JsonTranslationAdapter.__init__(base_dir: Path, override_dir: Path)`

**Qué hace**: carga los tres catálogos JSON (buildings, troops, messages) del directorio base y los fusiona con los overrides. Guarda los resultados en `self._buildings`, `self._troops`, `self._messages`.

**Reglas de carga**:

| Archivo | Comportamiento si falta | Comportamiento si JSON inválido |
|---|---|---|
| `base/buildings.json` | `RuntimeError` — app no arranca | `RuntimeError` — app no arranca |
| `base/troops.json` | `RuntimeError` — app no arranca | `RuntimeError` — app no arranca |
| `base/messages.json` | `RuntimeError` — app no arranca | `RuntimeError` — app no arranca |
| `override/buildings.json` | Ignorado silenciosamente | `RuntimeError` — app no arranca |
| `override/troops.json` | Ignorado silenciosamente | `RuntimeError` — app no arranca |
| `override/messages.json` | Ignorado silenciosamente | `RuntimeError` — app no arranca |

**Merge de override**: `effective = {**base, **override}`. Es un merge de primer nivel: si la misma clave (gid para edificios, `"TRIBE_n"` para tropas, `error_code` para mensajes) existe en ambos, el valor completo del override reemplaza al del base.

**Por qué no es un merge profundo**: los valores son dicts de idioma (`{"es": ..., "en": ..., ...}`). Un merge profundo campo a campo requeriría lógica adicional y no hay un caso de uso actual que lo justifique. El override más común es "ajustar la traducción de un edificio concreto", para lo que el reemplazo total es suficiente.

---

## `JsonTranslationAdapter._load_json_required(path: Path) -> dict` (estático)

**Qué hace**: abre el archivo JSON en `path` y devuelve el dict parseado.

**Lanza**:
- `RuntimeError` (wrapping `FileNotFoundError`) si el archivo no existe.
- `RuntimeError` (wrapping `json.JSONDecodeError`) si el JSON es inválido.

El `from None` / `from exc` en el `raise` limpia el traceback de anidamiento innecesario en el primer caso, y lo preserva en el segundo.

---

## `JsonTranslationAdapter._load_json_optional(path: Path) -> dict` (estático)

**Qué hace**: igual que `_load_json_required` pero devuelve `{}` si el archivo no existe.

Si el archivo existe pero es JSON inválido, sí lanza `RuntimeError` (el override corrompido no se ignora silenciosamente — solo la ausencia del archivo es ignorable).

---

🔖 Última revisión: 2026-05-24
