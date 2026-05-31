---
name: bd-ataques-oasis-feature
description: "feature BD de ataques a oasis (pegar reporte Travian → parsear → BD + stats animales) implementada full-stack, pendiente prueba manual + commit"
metadata: 
  node_type: memory
  type: project
  originSessionId: bf6b81c2-36fb-4b61-9aba-46ade170f887
---

Feature "BD de ataques a oasis": el usuario pega el texto crudo de un reporte de ataque de Travian a un oasis, se parsea y se guarda en SQLite para estadísticas de aparición/repoblación de animales.

Estado a 2026-05-31: **implementada full-stack, pendiente del gate humano (prueba manual del usuario) y commit.** No commiteado aún.

Decisiones de producto: cajón global (sin world_id), flujo parse→preview→guardar, duplicado avisa y no duplica (clave coords destino+timestamp+aldea origen), origen = solo nombre de aldea (el reporte no trae coords origen), borrar sí / editar no. Stats MVP: aparición de animales por oasis, repoblación (tiempo entre ataques), animales regenerados desde el ataque anterior (delta, calculado con LAG() en SQL), historial+totales. Sin rentabilidad por tropa (fuera de MVP). Parser autodetecta idioma invirtiendo catálogo NATURE (215 nombres únicos en 25 idiomas, sin colisiones). Router sin Accept-Language (datos numéricos/ISO).

Specs: docs/specs/bd-ataques-oasis.md (funcional, apis validadas) + docs/design/bd-ataques-oasis-ui.md.
Backend: core/entities/attack_report.py, core/use_cases/attack_report_parser.py, core/ports/attack_report_port.py, adapters/db/attack_report_sqlite_adapter.py, adapters/api/routes/attack_reports.py (6 endpoints, prefijo /attack-reports). 65 tests verdes.
Frontend: frontend/src/pages/AttackReportsPage.jsx + frontend/src/components/attack-reports/* + ui/TabBar + ui/DeletePopover; ruta /reportes-oasis; reutiliza TravianReport.jsx sin cambios.

OJO rama: se hizo sobre feature/optimizador-balance-multiraid, que NO encaja con el nombre; al commitear conviene rama propia feature/bd-ataques-oasis. Relacionado con [[branch-hygiene-one-feature-per-branch]].
