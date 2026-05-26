/**
 * Catálogo IT — Italiano
 * [AUTO] Traducción automática — requiere revisión nativa.
 * Claves no presentes aquí hacen fallback al catálogo 'es'.
 */
const it = {
  // ── App ────────────────────────────────────────────────
  'app.name': 'TravianBot',

  // ── Navegación (sidebar) ────────────────────────────────
  'nav.accounts':     'Account',
  'nav.resources':    'Risorse',
  'nav.troops':       'Truppe',
  'nav.construction': 'Costruzione',
  'nav.comingSoon':   'Prossimamente',

  // ── Topbar ─────────────────────────────────────────────
  'topbar.toggleTheme':    'Cambia tema',
  'topbar.selectLanguage': 'Seleziona lingua',
  'topbar.backToWorlds':   '← Mondi',
  'topbar.searchLanguage': 'Cerca lingua…',

  // ── S2 — Lista de cuentas ───────────────────────────────
  'page.accounts.title':        'Account',
  'page.accounts.caption':      '{n} account',
  'page.accounts.caption.pl':   '{n} account',
  'page.accounts.newAccount':   'Nuovo account',
  'page.accounts.empty.title':  'Ancora nessun account',
  'page.accounts.empty.desc':   'Aggiungi il primo per iniziare a usare il bot.',
  'page.accounts.col.email':    'Email',
  'page.accounts.col.username': 'Nome utente',
  'page.accounts.col.worlds':   'Mondi',
  'page.accounts.col.created':  'Creato',
  'page.accounts.col.actions':  '',
  'page.accounts.action.edit':  'Modifica account',
  'page.accounts.action.delete':'Elimina account',
  'page.accounts.loading':      'Caricamento account…',
  'page.accounts.error':        'Impossibile caricare gli account.',

  // ── S3 — Wizard de alta ────────────────────────────────
  'wizard.title':                'Nuovo account',
  'wizard.step':                 'Passo {current} di {total}',
  'wizard.section.account':      'Dati account',
  'wizard.section.world':        'Primo mondo',
  'wizard.field.email':          'Email',
  'wizard.field.email.ph':       'giocatore@esempio.it',
  'wizard.field.username':       'Nome utente',
  'wizard.field.username.ph':    'MioAccount',
  'wizard.field.password':       'Password',
  'wizard.field.password.ph':    '••••••••',
  'wizard.field.server':         'URL del server',
  'wizard.field.server.ph':      'https://ts1.x1.international.travian.com/',
  'wizard.field.tribe':          'Tribù',
  'wizard.field.tribe.ph':       'Seleziona una tribù',
  'wizard.btn.next':             'Avanti',
  'wizard.btn.back':             'Indietro',
  'wizard.btn.create':           'Crea account',
  'wizard.btn.creating':         'Creazione…',
  'wizard.btn.cancel':           'Annulla',
  'wizard.error.email.invalid':  'Inserire un email valido',
  'wizard.error.email.taken':    'Questa email è già registrata',
  'wizard.error.server.invalid': 'Inserire un URL valido (http:// o https://)',
  'wizard.error.server.taken':   'Questo server esiste già in questo account',
  'wizard.error.required':       'Questo campo è obbligatorio',
  'wizard.error.tribe.required': 'Seleziona una tribù',
  'wizard.btn.showPassword':     'Mostra password',
  'wizard.btn.hidePassword':     'Nascondi password',
  'wizard.toast.created':        'Account creato',

  // ── S4 — Detalle de cuenta ─────────────────────────────
  'page.account.breadcrumb':         'Account',
  'page.account.createdAt':          'Creato: {date}',
  'page.account.editBtn':            'Modifica',
  'page.account.deleteBtn':          'Elimina account',
  'page.account.worlds.title':       'Mondi ({n})',
  'page.account.worlds.add':         'Aggiungi mondo',
  'page.account.worlds.empty':       'Ancora nessun mondo in questo account.',
  'page.account.col.server':         'Server',
  'page.account.col.parsed':         'Server (leggibile)',
  'page.account.col.tribe':          'Tribù',
  'page.account.col.session':        'Sessione',
  'page.account.col.actions':        '',
  'page.account.action.deleteWorld': 'Elimina mondo',
  'page.account.notFound.title':     'Account non trovato',
  'page.account.notFound.desc':      "L'account cercato non esiste o è stato eliminato.",
  'page.account.notFound.back':      'Torna agli account',

  // ── S5 — Modal editar cuenta ───────────────────────────
  'modal.edit.title':           'Modifica account',
  'modal.edit.changePassword':  'Cambia password',
  'modal.edit.newPassword':     'Nuova password',
  'modal.edit.confirmPassword': 'Conferma password',
  'modal.edit.passwordMismatch':'Le password non corrispondono',
  'modal.edit.saveBtn':         'Salva',
  'modal.edit.savingBtn':       'Salvataggio…',
  'modal.edit.cancelBtn':       'Annulla',
  'modal.edit.closeBtn':        'Chiudi',
  'modal.edit.savedToast':      'Modifiche salvate',
  'modal.edit.error409':        'Questa email è già utilizzata da un altro account.',

  // ── S6 — Modal añadir mundo ────────────────────────────
  'modal.addWorld.title':     'Aggiungi mondo',
  'modal.addWorld.addBtn':    'Aggiungi',
  'modal.addWorld.addingBtn': 'Aggiunta…',
  'modal.addWorld.cancelBtn': 'Annulla',
  'modal.addWorld.toast':     'Mondo aggiunto',

  // ── S7 — Borrar cuenta ─────────────────────────────────
  'modal.deleteAccount.title':   'Elimina account',
  'modal.deleteAccount.body':    'Eliminare l\'account "{username}"?',
  'modal.deleteAccount.warning': 'Questa azione non può essere annullata. Verranno eliminati anche tutti i suoi mondi ({n} mondo/i).',
  'modal.deleteAccount.confirm': 'Elimina',
  'modal.deleteAccount.cancel':  'Annulla',
  'modal.deleteAccount.toast':   'Account eliminato',
  'modal.deleteAccount.active':  'Impossibile eliminare questo account mentre il bot ha una sessione attiva. Fermare prima la sessione.',
  'modal.deleteAccount.close':   'Chiudi',

  // ── S8 — Borrar mundo ──────────────────────────────────
  'modal.deleteWorld.title':   'Elimina mondo',
  'modal.deleteWorld.body':    'Eliminare il mondo "{parsed}"?',
  'modal.deleteWorld.warning': 'Questa azione non può essere annullata. Verranno eliminate anche tutte le città associate.',
  'modal.deleteWorld.confirm': 'Elimina',
  'modal.deleteWorld.cancel':  'Annulla',
  'modal.deleteWorld.toast':   'Mondo eliminato',
  'modal.deleteWorld.active':  "C'è una sessione attiva per questo mondo. Fermare prima la sessione.",

  // ── S9 — Espacio del mundo ─────────────────────────────
  'world.status.active':          'Attivo',
  'world.status.panelLabel':      'Sessione attiva',
  'world.action.stop':            'Ferma',
  'world.tab.config':             'Configurazione',
  'world.tab.resources':          'Risorse',
  'world.tab.troops':             'Truppe',
  'world.tab.construction':       'Costruzione',
  'world.tab.villages':           'Villaggi',
  'world.config.automationTitle': 'Automazione',
  'world.config.tasksTitle':      'Compiti del bot',
  'world.config.tasksDesc':       'Attiva o sospendi i compiti automatici che il bot esegue in questo mondo.',
  'world.config.task.buildQueue': 'Coda di costruzione',
  'world.config.task.buildQueueDesc': 'Costruisce edifici secondo la coda pianificata',
  'world.config.task.farmList':   'Lista fattorie',
  'world.config.task.farmListDesc': 'Invia attacchi di farming automaticamente',
  'world.config.task.troops':     'Addestramento truppe',
  'world.config.task.troopsDesc': "Mantiene attiva la coda di addestramento",
  'world.config.intervalsTitle':  'Intervalli',
  'world.config.intervalsDesc':   'Tempo tra i controlli del bot. Valori più alti riducono il rischio di rilevamento.',
  'world.config.interval.check':  'Controllo periodico',
  'world.config.interval.farm':   'Tra le fattorie',
  'world.config.interval.jitter': 'Variazione casuale',
  'world.config.interval.min':    'min',
  'world.config.comingSoonTitle': 'Prossimamente in questo spazio',
  'world.comingSoon.resourcesDesc':   'Monitoraggio in tempo reale di legno, argilla, ferro e grano.',
  'world.comingSoon.troopsDesc':      'Inventario unità, statistiche di combattimento e coda di addestramento.',
  'world.comingSoon.constructionDesc':'Coda di costruzione per villaggio, costi e tempi.',
  'world.comingSoon.villagesDesc':    'Mappa dei villaggi, coordinate, nome e tipo.',
  'world.stop.toast':             'Bot fermato. Ritorno ai dettagli account…',

  // ── Sesión del mundo ───────────────────────────────────
  'world.session.start':    'Avvia',
  'world.session.stop':     'Ferma',
  'world.session.retry':    'Riprova',
  'world.session.cancel':   'Annulla',
  'world.session.enter':    'Entra',
  'world.session.idle':     'Inattivo',
  'world.session.connecting': 'Connessione…',
  'world.session.active':   'Attivo',
  'world.session.error':    'Errore di connessione',
  'world.session.stopping': 'Arresto…',
  'world.session.start.aria': 'Avvia bot su {world}',
  'world.session.stop.aria':  'Ferma bot su {world}',
  'world.session.retry.aria': 'Riprova connessione su {world}',
  'world.session.enter.aria': "Entra nello spazio di {world}",
  'world.session.disabled.delete':       'Fermare la sessione prima di eliminare questo mondo',
  'world.session.disabled.editMenu':     'Impossibile modificare un mondo con sessione attiva',
  'world.session.disabled.deleteAccount':'Fermare tutte le sessioni attive prima di eliminare questo account',
  'world.session.started.toast':  'Bot avviato su {world}',
  'world.session.stopped.toast':  'Bot fermato su {world}',
  'world.session.error.toast':    'Impossibile connettersi a {world}',

  // ── Tribus ──────────────────────────────────────────────
  'tribe.romans':    'Romans',
  'tribe.teutons':   'Teutons',
  'tribe.gauls':     'Gauls',
  'tribe.egyptians': 'Egyptians',
  'tribe.huns':      'Huns',
  'tribe.spartans':  'Spartans',
  'tribe.vikings':   'Vikings',

  // ── Errores globales ───────────────────────────────────
  'error.network':    'Errore di connessione. Riprova.',
  'error.retry':      'Riprova',
  'error.loadFailed': 'Impossibile caricare i dati.',

  // ── Versión ────────────────────────────────────────────
  'app.version': 'v0.1.0',

  // ── Placeholders de ruta ──────────────────────────────
  'placeholder.accounts.list':   'Lista account — prossimamente',
  'placeholder.account.detail':  'Dettagli account — prossimamente',
  'placeholder.world.space':     'Spazio mondo — prossimamente',
}

export default it
