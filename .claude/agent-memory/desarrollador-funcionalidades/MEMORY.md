# Memory index

- [project-stack](project_stack.md) — stack Python 3.14 + FastAPI 0.136 + pytest; comando de tests
- [fastapi-conventions](fastapi-conventions.md) — lifespan, headers, Accept-Language opcional, exception handler
- [test-client-lifespan](test-client-lifespan.md) — TestClient necesita `with` para disparar lifespan/startup
- [async-tests-pattern](async-tests-pattern.md) — tests async usan asyncio.run() directo, NO @pytest.mark.asyncio (modo STRICT)
- [game-data-port-pattern](game-data-port-pattern.md) — GameDataPort singleton en app.state, mismo patrón que translation_port
- [zendriver-api-real](zendriver-api-real.md) — API real verificada: query_selector/query_selector_all, text/parent como @property, attrs["class_"], screenshot_b64
- [troops-json-preloaded](troops-json-preloaded.md) — troops.json ya rellenado por prueba manual; test fallback "de" falla en develop (preexistente, no regresión)
- [overview-trunk-pattern](overview-trunk-pattern.md) — port/adaptadores/caché/VillageMapUseCase del tronco de overview; 4 bloques futuros lo reusan
- [parsing-utils-bidi](parsing-utils-bidi.md) — parse_int/parse_int_or_none/parse_time en core/utils/parsing.py; eliminan bidi U+202D/U+202C de Travian
- [scraper-utils-extraction](scraper-utils-extraction.md) — adapters/scraper/utils.py centraliza _remove_background/_wait_for_element; kirilloid_scraper.py los re-exporta
- [building-header-map-pattern](building-header-map-pattern.md) — kirilloid build.php: cabecera usa <td> NO <th>; mapeo por clase CSS img; _make_icon_id(gid,name) prioriza name sobre alias
- [units-parsers-helpers](units-parsers-helpers.md) — rangos uNN→tribu verificados + helpers _common.py; reutilizables en los 4 bloques de overview
- [resources-block-pattern](resources-block-pattern.md) — bloque RESOURCES: use case llama al parser internamente (vs overview donde lo llama el handler); valores de fixtures de los 6 aldeas
- [troops-block-pattern](troops-block-pattern.md) — bloque TROOPS: 5 parsers estáticos, use case enriquece, parser devuelve troop_types como list[str] y buildings=[]/troop_names={} vacíos
- [upgrades-per-unit-pattern](upgrades-per-unit-pattern.md) — kirilloid #upg_table es por unidad; about:blank→get(url&unit=N); cabecera 6 td.upg; 13 celdas por fila; mapeo eye→scouting/def_s→counter_scouting/point→destructive
- [troop-display-consolidation](troop-display-consolidation.md) — helper resolve_troop_display en core/use_cases/; use cases async; TroopNotFoundError(tribe, ordinal); edificios training icon_url forward-compatible
- [session-registry-pattern](session-registry-pattern.md) — SessionRegistry singleton + patrón _StateOverride en tests de API; 9 fallos preexistentes en suite
- [fernet-in-use-case-pattern](fernet-in-use-case-pattern.md) — descifrado en LoginUseCase (no en adaptador); _StateOverride necesita fernet=_TEST_FERNET en tests de POST; field(repr=False) en Account.password
