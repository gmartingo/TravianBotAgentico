---
name: perf-drawer-pattern
description: Patrón de rendimiento para drawers: mantener montados + hoisting de fetch al padre para evitar re-fetch en cada apertura
metadata:
  type: feedback
---

Al optimizar un drawer lateral que se montaba/desmontaba con `if (!open) return null`:

**Patrón aplicado en `NoiseDestinationDrawer`:**
- Reemplazar `if (!open) return null` por visibilidad CSS: `visibility`, `opacity`, `transform`, `pointerEvents` controlados por la prop `open`.
- Usar `aria-hidden={!open}` para excluir el contenido de lectores de pantalla cuando está cerrado.
- Subir los fetches costosos (EP-N12 orígenes) al componente padre (`NoiseTab`) para que se hagan una sola vez, y pasarlos como props al wizard.
- Cachear el resultado del fetch de paths por destino (`loadedDestId.current`) para no re-pedir al reabrir el mismo destino.
- Reducir duración de animación de 220ms a 150ms.

**Resultado medido:** 5 aperturas consecutivas bajaron de ~36ms avg (primera apertura) a ~7ms avg con 0 peticiones de red durante las aperturas 2-5 (solo `paths` en la primera apertura de cada destino).

**Por qué:** El re-montaje total del subárbol (wizard + pathlist) en cada apertura disparaba EP-N12 en cada `useEffect` del wizard. Con drawer siempre montado + orígenes en el padre, el subárbol ya existe y las props llegan sin fetch.

**Cómo aplicar:** Cuando un drawer tiene subcomponentes que hacen fetch en su `useEffect` inicial, considerar el patrón "siempre montado + fetch hoisting". Mantener la a11y con `aria-hidden` + `visibility: hidden` en lugar de desmontaje.

**Ver:** `frontend/src/components/world/noise/NoiseDestinationDrawer.jsx`, `NoiseTab.jsx`, `NoisePathWizard.jsx`
