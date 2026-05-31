---
name: travian-report-hora-verbatim
description: "en reportes Travian el \"Server time\" es el reloj de visualización, NO la hora del ataque; guardar attacked_at verbatim sin convertir a UTC"
metadata: 
  node_type: memory
  type: project
  originSessionId: b7059202-0426-4c69-99ad-621eb63e9279
---

En un reporte de ataque de Travian hay DOS horas con semánticas distintas:
- Línea bajo el título del oasis (`31.05.26, 13:39:30`) = **HORA DEL ATAQUE** (la que el usuario quiere).
- `Server time: 19:22:21 (UTC +01:00)` = **reloj de visualización** (cuándo MIRÓ el reporte), NO la hora del ataque. En reportes reales difieren varias horas; NO usarlo nunca para derivar `attacked_at`.

Bug original (doble): el parser cogía la hora del ataque y le **restaba** el offset del Server time (guardaba 12:39:30); y el frontend reinterpretaba ese UTC con la zona del PC (España en verano = UTC+2, pero el servidor de Travian va FIJO en UTC+1 sin DST) → mostraba 14:39. El usuario veía la hora desfasada 1h.

**Decisión (acordada con el usuario):** guardar y mostrar la hora **verbatim**, exactamente como la pone Travian, sin conversión de zona. Los gaps de repoblación siguen exactos porque todas las filas quedan en el mismo reloj. `utc_offset` se conserva solo como metadato. Spec: docs/specs/bd-ataques-oasis-fix-hora-balance.md. Relacionado con [[bd-ataques-oasis-feature]].
