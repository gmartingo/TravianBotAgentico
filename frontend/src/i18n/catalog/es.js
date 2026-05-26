/**
 * Catálogo ES — Español (idioma base, redactado con cuidado).
 * Todas las claves deben existir aquí. Los demás idiomas pueden
 * omitir claves; el sistema cae de vuelta al español.
 *
 * Convención de claves: jerarquía con puntos (nav.accounts, wizard.btn.next, …)
 * Plantillas con interpolación: "Hola {name}" → t('key', { name: 'Mundo' })
 */
const es = {
  // ── App ────────────────────────────────────────────────
  'app.name': 'TravianBot',

  // ── Navegación (sidebar) ────────────────────────────────
  'nav.accounts':     'Cuentas',
  'nav.resources':    'Recursos',
  'nav.troops':       'Tropas',
  'nav.construction': 'Construcción',
  'nav.comingSoon':   'Próximamente',

  // ── Topbar ─────────────────────────────────────────────
  'topbar.toggleTheme':    'Cambiar tema',
  'topbar.selectLanguage': 'Seleccionar idioma',
  'topbar.backToWorlds':   '← Mundos',
  'topbar.searchLanguage': 'Buscar idioma…',

  // ── S2 — Lista de cuentas ───────────────────────────────
  'page.accounts.title':        'Cuentas',
  'page.accounts.caption':      '{n} cuenta',
  'page.accounts.caption.pl':   '{n} cuentas',
  'page.accounts.newAccount':   'Nueva cuenta',
  'page.accounts.empty.title':  'Aún no tienes cuentas',
  'page.accounts.empty.desc':   'Añade la primera para empezar a usar el bot.',
  'page.accounts.col.email':    'Email',
  'page.accounts.col.username': 'Usuario',
  'page.accounts.col.worlds':   'Mundos',
  'page.accounts.col.created':  'Creada',
  'page.accounts.col.actions':  '',
  'page.accounts.action.delete':'Borrar cuenta',
  'page.accounts.loading':      'Cargando cuentas…',
  'page.accounts.error':        'No se pudieron cargar las cuentas.',

  // ── S3 — Wizard de alta ────────────────────────────────
  'wizard.title':                'Nueva cuenta',
  'wizard.step':                 'Paso {current} de {total}',
  'wizard.section.account':      'Datos de la cuenta',
  'wizard.section.world':        'Primer mundo',
  'wizard.field.email':          'Email',
  'wizard.field.email.ph':       'jugador@ejemplo.com',
  'wizard.field.username':       'Usuario',
  'wizard.field.username.ph':    'MiCuenta',
  'wizard.field.password':       'Contraseña',
  'wizard.field.password.ph':    '••••••••',
  'wizard.field.server':         'URL del servidor',
  'wizard.field.server.ph':      'https://ts1.x1.international.travian.com/',
  'wizard.field.tribe':          'Tribu',
  'wizard.field.tribe.ph':       'Selecciona una tribu',
  'wizard.btn.next':             'Siguiente',
  'wizard.btn.back':             'Atrás',
  'wizard.btn.create':           'Crear cuenta',
  'wizard.btn.creating':         'Creando…',
  'wizard.btn.cancel':           'Cancelar',
  'wizard.error.email.invalid':  'Introduce un email válido',
  'wizard.error.email.taken':    'Este email ya está registrado',
  'wizard.error.server.invalid': 'Introduce una URL válida (http:// o https://)',
  'wizard.error.server.taken':   'Este servidor ya existe en esta cuenta',
  'wizard.error.required':       'Este campo es obligatorio',

  // ── S4 — Detalle de cuenta ─────────────────────────────
  'page.account.breadcrumb':         'Cuentas',
  'page.account.createdAt':          'Creada: {date}',
  'page.account.editBtn':            'Editar',
  'page.account.deleteBtn':          'Borrar cuenta',
  'page.account.worlds.title':       'Mundos ({n})',
  'page.account.worlds.add':         'Añadir mundo',
  'page.account.worlds.empty':       'Todavía no hay mundos en esta cuenta.',
  'page.account.col.server':         'Servidor',
  'page.account.col.parsed':         'Servidor (legible)',
  'page.account.col.tribe':          'Tribu',
  'page.account.col.session':        'Sesión',
  'page.account.col.actions':        '',
  'page.account.action.deleteWorld': 'Borrar mundo',
  'page.account.notFound.title':     'Cuenta no encontrada',
  'page.account.notFound.desc':      'La cuenta que buscas no existe o fue eliminada.',
  'page.account.notFound.back':      'Volver a cuentas',

  // ── S5 — Modal editar cuenta ───────────────────────────
  'modal.edit.title':           'Editar cuenta',
  'modal.edit.changePassword':  'Cambiar contraseña',
  'modal.edit.newPassword':     'Contraseña nueva',
  'modal.edit.confirmPassword': 'Confirmar contraseña',
  'modal.edit.passwordMismatch':'Las contraseñas no coinciden',
  'modal.edit.saveBtn':         'Guardar',
  'modal.edit.savingBtn':       'Guardando…',
  'modal.edit.cancelBtn':       'Cancelar',
  'modal.edit.savedToast':      'Cambios guardados',

  // ── S6 — Modal añadir mundo ────────────────────────────
  'modal.addWorld.title':     'Añadir mundo',
  'modal.addWorld.addBtn':    'Añadir',
  'modal.addWorld.addingBtn': 'Añadiendo…',
  'modal.addWorld.cancelBtn': 'Cancelar',
  'modal.addWorld.toast':     'Mundo añadido',

  // ── S7 — Borrar cuenta ─────────────────────────────────
  'modal.deleteAccount.title':   'Borrar cuenta',
  'modal.deleteAccount.body':    '¿Borrar la cuenta "{username}"?',
  'modal.deleteAccount.warning': 'Esta acción no se puede deshacer. Se borrarán también todos sus mundos ({n} mundo/s).',
  'modal.deleteAccount.confirm': 'Borrar',
  'modal.deleteAccount.cancel':  'Cancelar',
  'modal.deleteAccount.toast':   'Cuenta eliminada',
  'modal.deleteAccount.active':  'No es posible borrar esta cuenta mientras el bot tiene una sesión activa. Detén la sesión primero.',
  'modal.deleteAccount.close':   'Cerrar',

  // ── S8 — Borrar mundo ──────────────────────────────────
  'modal.deleteWorld.title':   'Borrar mundo',
  'modal.deleteWorld.body':    '¿Borrar el mundo "{parsed}"?',
  'modal.deleteWorld.warning': 'Esta acción no se puede deshacer. Se borrarán también todas las aldeas asociadas.',
  'modal.deleteWorld.confirm': 'Borrar',
  'modal.deleteWorld.cancel':  'Cancelar',
  'modal.deleteWorld.toast':   'Mundo eliminado',
  'modal.deleteWorld.active':  'Hay una sesión activa para este mundo. Detén la sesión primero.',

  // ── S9 — Espacio del mundo ─────────────────────────────
  'world.status.active':          'Activo',
  'world.status.panelLabel':      'Sesión activa',
  'world.action.stop':            'Parar',
  'world.tab.config':             'Configuración',
  'world.tab.resources':          'Recursos',
  'world.tab.troops':             'Tropas',
  'world.tab.construction':       'Construcción',
  'world.tab.villages':           'Aldeas',
  'world.config.automationTitle': 'Automatización',
  'world.config.tasksTitle':      'Tareas del bot',
  'world.config.tasksDesc':       'Activa o pausa las tareas automáticas que el bot ejecuta en este mundo.',
  'world.config.task.buildQueue': 'Cola de construcción',
  'world.config.task.buildQueueDesc': 'Construye edificios según la cola planificada',
  'world.config.task.farmList':   'Lista de granjas',
  'world.config.task.farmListDesc': 'Envía ataques de granjeo automáticamente',
  'world.config.task.troops':     'Entrenamiento de tropas',
  'world.config.task.troopsDesc': 'Mantiene la cola de entrenamiento activa',
  'world.config.intervalsTitle':  'Intervalos',
  'world.config.intervalsDesc':   'Tiempo entre comprobaciones del bot. Valores más altos reducen el riesgo de detección.',
  'world.config.interval.check':  'Comprobación periódica',
  'world.config.interval.farm':   'Entre granjas',
  'world.config.interval.jitter': 'Variación aleatoria',
  'world.config.interval.min':    'min',
  'world.config.comingSoonTitle': 'Próximamente en este espacio',
  'world.comingSoon.resourcesDesc':   'Monitorización en tiempo real de madera, barro, hierro y cereal.',
  'world.comingSoon.troopsDesc':      'Inventario de unidades, estadísticas de combate y cola de entrenamiento.',
  'world.comingSoon.constructionDesc':'Cola de edificios por aldea, costes y tiempos.',
  'world.comingSoon.villagesDesc':    'Mapa de aldeas, coordenadas, nombre y tipo.',
  'world.stop.toast':             'Bot detenido. Volviendo al detalle de la cuenta…',

  // ── Sesión del mundo (§4b) ─────────────────────────────
  'world.session.start':    'Arrancar',
  'world.session.stop':     'Parar',
  'world.session.retry':    'Reintentar',
  'world.session.cancel':   'Cancelar',
  'world.session.enter':    'Entrar',
  'world.session.idle':     'Inactivo',
  'world.session.connecting': 'Conectando…',
  'world.session.active':   'Activo',
  'world.session.error':    'Error de conexión',
  'world.session.stopping': 'Parando…',
  'world.session.start.aria': 'Arrancar bot en {world}',
  'world.session.stop.aria':  'Parar bot en {world}',
  'world.session.retry.aria': 'Reintentar conexión en {world}',
  'world.session.enter.aria': 'Entrar al espacio de {world}',
  'world.session.disabled.delete':       'Detén la sesión antes de borrar este mundo',
  'world.session.disabled.editMenu':     'No es posible modificar un mundo con sesión activa',
  'world.session.disabled.deleteAccount':'Detén todas las sesiones activas antes de borrar esta cuenta',
  'world.session.started.toast':  'Bot arrancado en {world}',
  'world.session.stopped.toast':  'Bot detenido en {world}',
  'world.session.error.toast':    'No se pudo conectar en {world}',

  // ── Tribus ──────────────────────────────────────────────
  'tribe.romans':    'Romans',
  'tribe.teutons':   'Teutons',
  'tribe.gauls':     'Gauls',
  'tribe.egyptians': 'Egyptians',
  'tribe.huns':      'Huns',
  'tribe.spartans':  'Spartans',
  'tribe.vikings':   'Vikings',

  // ── Errores globales ───────────────────────────────────
  'error.network':    'Error de conexión. Inténtalo de nuevo.',
  'error.retry':      'Reintentar',
  'error.loadFailed': 'No se pudieron cargar los datos.',

  // ── Versión (sidebar footer) ───────────────────────────
  'app.version': 'v0.1.0',

  // ── Placeholders de ruta (etapa 1) ────────────────────
  'placeholder.accounts.list':   'Lista de cuentas — próximamente',
  'placeholder.account.detail':  'Detalle de cuenta — próximamente',
  'placeholder.world.space':     'Espacio del mundo — próximamente',
}

export default es
