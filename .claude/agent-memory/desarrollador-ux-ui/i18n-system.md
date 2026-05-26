---
name: i18n-system
description: Sistema i18n del dashboard: 25 idiomas, fallback es, RTL para ar/he/fa
metadata:
  type: project
---

Ficheros clave:
- `src/i18n/languages.js` — array LANGUAGES con { code, name (endónimo), rtl }
- `src/i18n/catalog/es.js` — catálogo base COMPLETO (fuente de verdad de claves)
- `src/i18n/catalog/en.js` — catálogo EN completo (segundo idioma redactado con cuidado)
- `src/i18n/catalog/<código>.js` — otros 23 idiomas con claves principales; marcados `[AUTO]`
- `src/i18n/catalog/index.js` — importa todos y exporta CATALOG
- `src/i18n/index.jsx` — I18nProvider + useI18n hook (context)

Uso en componentes:
```jsx
const { t, lang, setLang } = useI18n()
t('nav.accounts')                          // → "Cuentas"
t('wizard.step', { current: 1, total: 2 }) // → "Paso 1 de 2"
t('page.accounts.caption', { n: 3 })       // usa .pl si n≠1
```

Fallback: si clave no existe en idioma activo → cae a 'es'. Nunca undefined.

RTL (ar, he, fa): al setLang() se aplica `document.documentElement.dir = 'rtl'`.
Propiedades CSS lógicas en todos los componentes (ms-*, me-*, ps-*, start-*, end-*).

Para añadir nueva clave:
1. Añadirla en `es.js` (obligatorio, es el base)
2. Añadirla en `en.js` (recomendado)
3. Los otros 23 la omiten → fallback a es automáticamente

Truco: los catálogos que contienen apostrofes en francés/italiano usan comillas dobles
para los valores afectados (p.ej. "Nom d'utilisateur", "Aucun compte pour l'instant").
