/**
 * Catálogo DE — Deutsch
 * [AUTO] Traducción automática — requiere revisión nativa.
 * Claves no presentes aquí hacen fallback al catálogo 'es'.
 */
const de = {
  // ── App ────────────────────────────────────────────────
  'app.name': 'TravianBot',

  // ── Navegación (sidebar) ────────────────────────────────
  'nav.accounts':     'Konten',
  'nav.resources':    'Ressourcen',
  'nav.troops':       'Truppen',
  'nav.construction': 'Bauwesen',
  'nav.comingSoon':   'Demnächst',

  // ── Topbar ─────────────────────────────────────────────
  'topbar.toggleTheme':    'Thema wechseln',
  'topbar.selectLanguage': 'Sprache wählen',
  'topbar.backToWorlds':   '← Welten',
  'topbar.searchLanguage': 'Sprache suchen…',

  // ── S2 — Lista de cuentas ───────────────────────────────
  'page.accounts.title':        'Konten',
  'page.accounts.caption':      '{n} Konto',
  'page.accounts.caption.pl':   '{n} Konten',
  'page.accounts.newAccount':   'Neues Konto',
  'page.accounts.empty.title':  'Noch keine Konten',
  'page.accounts.empty.desc':   'Füge das erste hinzu, um den Bot zu verwenden.',
  'page.accounts.col.email':    'E-Mail',
  'page.accounts.col.username': 'Benutzername',
  'page.accounts.col.worlds':   'Welten',
  'page.accounts.col.created':  'Erstellt',
  'page.accounts.col.actions':  '',
  'page.accounts.action.edit':  'Konto bearbeiten',
  'page.accounts.action.delete':'Konto löschen',
  'page.accounts.loading':      'Konten werden geladen…',
  'page.accounts.error':        'Konten konnten nicht geladen werden.',

  // ── S3 — Wizard de alta ────────────────────────────────
  'wizard.title':                'Neues Konto',
  'wizard.step':                 'Schritt {current} von {total}',
  'wizard.section.account':      'Kontodaten',
  'wizard.section.world':        'Erste Welt',
  'wizard.field.email':          'E-Mail',
  'wizard.field.email.ph':       'spieler@beispiel.de',
  'wizard.field.username':       'Benutzername',
  'wizard.field.username.ph':    'MeinKonto',
  'wizard.field.password':       'Passwort',
  'wizard.field.password.ph':    '••••••••',
  'wizard.field.server':         'Server-URL',
  'wizard.field.server.ph':      'https://ts1.x1.international.travian.com/',
  'wizard.field.tribe':          'Stamm',
  'wizard.field.tribe.ph':       'Stamm auswählen',
  'wizard.btn.next':             'Weiter',
  'wizard.btn.back':             'Zurück',
  'wizard.btn.create':           'Konto erstellen',
  'wizard.btn.creating':         'Erstelle…',
  'wizard.btn.cancel':           'Abbrechen',
  'wizard.error.email.invalid':  'Gültige E-Mail-Adresse eingeben',
  'wizard.error.email.taken':    'Diese E-Mail ist bereits registriert',
  'wizard.error.server.invalid': 'Gültige URL eingeben (http:// oder https://)',
  'wizard.error.server.taken':   'Dieser Server existiert bereits in diesem Konto',
  'wizard.error.required':       'Dieses Feld ist erforderlich',
  'wizard.error.tribe.required': 'Stamm auswählen',
  'wizard.btn.showPassword':     'Passwort anzeigen',
  'wizard.btn.hidePassword':     'Passwort verbergen',
  'wizard.toast.created':        'Konto erstellt',

  // ── S4 — Detalle de cuenta ─────────────────────────────
  'page.account.breadcrumb':         'Konten',
  'page.account.createdAt':          'Erstellt: {date}',
  'page.account.editBtn':            'Bearbeiten',
  'page.account.deleteBtn':          'Konto löschen',
  'page.account.worlds.title':       'Welten ({n})',
  'page.account.worlds.add':         'Welt hinzufügen',
  'page.account.worlds.empty':       'Noch keine Welten in diesem Konto.',
  'page.account.col.server':         'Server',
  'page.account.col.parsed':         'Server (lesbar)',
  'page.account.col.tribe':          'Stamm',
  'page.account.col.session':        'Sitzung',
  'page.account.col.actions':        '',
  'page.account.action.deleteWorld': 'Welt löschen',
  'page.account.notFound.title':     'Konto nicht gefunden',
  'page.account.notFound.desc':      'Das gesuchte Konto existiert nicht oder wurde gelöscht.',
  'page.account.notFound.back':      'Zurück zu Konten',

  // ── S5 — Modal editar cuenta ───────────────────────────
  'modal.edit.title':           'Konto bearbeiten',
  'modal.edit.changePassword':  'Passwort ändern',
  'modal.edit.newPassword':     'Neues Passwort',
  'modal.edit.confirmPassword': 'Passwort bestätigen',
  'modal.edit.passwordMismatch':'Passwörter stimmen nicht überein',
  'modal.edit.saveBtn':         'Speichern',
  'modal.edit.savingBtn':       'Speichere…',
  'modal.edit.cancelBtn':       'Abbrechen',
  'modal.edit.closeBtn':        'Schließen',
  'modal.edit.savedToast':      'Änderungen gespeichert',
  'modal.edit.error409':        'Diese E-Mail ist bereits in einem anderen Konto registriert.',

  // ── S6 — Modal añadir mundo ────────────────────────────
  'modal.addWorld.title':     'Welt hinzufügen',
  'modal.addWorld.addBtn':    'Hinzufügen',
  'modal.addWorld.addingBtn': 'Wird hinzugefügt…',
  'modal.addWorld.cancelBtn': 'Abbrechen',
  'modal.addWorld.toast':     'Welt hinzugefügt',

  // ── S7 — Borrar cuenta ─────────────────────────────────
  'modal.deleteAccount.title':   'Konto löschen',
  'modal.deleteAccount.body':    'Konto "{username}" löschen?',
  'modal.deleteAccount.warning': 'Diese Aktion kann nicht rückgängig gemacht werden. Alle zugehörigen Welten ({n} Welt/en) werden ebenfalls gelöscht.',
  'modal.deleteAccount.confirm': 'Löschen',
  'modal.deleteAccount.cancel':  'Abbrechen',
  'modal.deleteAccount.toast':   'Konto gelöscht',
  'modal.deleteAccount.active':  'Dieses Konto kann nicht gelöscht werden, solange der Bot eine aktive Sitzung hat. Sitzung zuerst beenden.',
  'modal.deleteAccount.close':   'Schließen',

  // ── S8 — Borrar mundo ──────────────────────────────────
  'modal.deleteWorld.title':   'Welt löschen',
  'modal.deleteWorld.body':    'Welt "{parsed}" löschen?',
  'modal.deleteWorld.warning': 'Diese Aktion kann nicht rückgängig gemacht werden. Alle zugehörigen Dörfer werden ebenfalls gelöscht.',
  'modal.deleteWorld.confirm': 'Löschen',
  'modal.deleteWorld.cancel':  'Abbrechen',
  'modal.deleteWorld.toast':   'Welt gelöscht',
  'modal.deleteWorld.active':  'Es gibt eine aktive Sitzung für diese Welt. Sitzung zuerst beenden.',

  // ── S9 — Espacio del mundo ─────────────────────────────
  'world.status.active':          'Aktiv',
  'world.status.panelLabel':      'Aktive Sitzung',
  'world.action.stop':            'Stoppen',
  'world.tab.config':             'Konfiguration',
  'world.tab.resources':          'Ressourcen',
  'world.tab.troops':             'Truppen',
  'world.tab.construction':       'Bauwesen',
  'world.tab.villages':           'Dörfer',
  'world.config.automationTitle': 'Automatisierung',
  'world.config.tasksTitle':      'Bot-Aufgaben',
  'world.config.tasksDesc':       'Aktiviere oder pausiere die automatischen Aufgaben, die der Bot in dieser Welt ausführt.',
  'world.config.task.buildQueue': 'Bau-Warteschlange',
  'world.config.task.buildQueueDesc': 'Baut Gebäude gemäß der geplanten Warteschlange',
  'world.config.task.farmList':   'Farmliste',
  'world.config.task.farmListDesc': 'Sendet Farmangriffe automatisch',
  'world.config.task.troops':     'Truppenausbildung',
  'world.config.task.troopsDesc': 'Hält die Ausbildungswarteschlange aktiv',
  'world.config.intervalsTitle':  'Intervalle',
  'world.config.intervalsDesc':   'Zeit zwischen Bot-Prüfungen. Höhere Werte reduzieren das Erkennungsrisiko.',
  'world.config.interval.check':  'Regelmäßige Prüfung',
  'world.config.interval.farm':   'Zwischen Farms',
  'world.config.interval.jitter': 'Zufällige Variation',
  'world.config.interval.min':    'min',
  'world.config.comingSoonTitle': 'Demnächst in diesem Bereich',
  'world.comingSoon.resourcesDesc':   'Echtzeit-Überwachung von Holz, Lehm, Eisen und Getreide.',
  'world.comingSoon.troopsDesc':      'Einheitenbestand, Kampfstatistiken und Ausbildungswarteschlange.',
  'world.comingSoon.constructionDesc':'Gebäudewarteschlange pro Dorf, Kosten und Zeiten.',
  'world.comingSoon.villagesDesc':    'Dorfkarte, Koordinaten, Name und Typ.',
  'world.stop.toast':             'Bot gestoppt. Rückkehr zur Kontoansicht…',

  // ── Sesión del mundo ───────────────────────────────────
  'world.session.start':    'Starten',
  'world.session.stop':     'Stoppen',
  'world.session.retry':    'Wiederholen',
  'world.session.cancel':   'Abbrechen',
  'world.session.enter':    'Eintreten',
  'world.session.idle':     'Inaktiv',
  'world.session.connecting': 'Verbinde…',
  'world.session.active':   'Aktiv',
  'world.session.error':    'Verbindungsfehler',
  'world.session.stopping': 'Stoppt…',
  'world.session.start.aria': 'Bot in {world} starten',
  'world.session.stop.aria':  'Bot in {world} stoppen',
  'world.session.retry.aria': 'Verbindung in {world} wiederholen',
  'world.session.enter.aria': 'Bereich von {world} betreten',
  'world.session.disabled.delete':       'Sitzung beenden, bevor diese Welt gelöscht wird',
  'world.session.disabled.editMenu':     'Eine Welt mit aktiver Sitzung kann nicht bearbeitet werden',
  'world.session.disabled.deleteAccount':'Alle aktiven Sitzungen beenden, bevor dieses Konto gelöscht wird',
  'world.session.started.toast':  'Bot in {world} gestartet',
  'world.session.stopped.toast':  'Bot in {world} gestoppt',
  'world.session.error.toast':    'Verbindung zu {world} fehlgeschlagen',

  // ── Tribus ──────────────────────────────────────────────
  'tribe.romans':    'Romans',
  'tribe.teutons':   'Teutons',
  'tribe.gauls':     'Gauls',
  'tribe.egyptians': 'Egyptians',
  'tribe.huns':      'Huns',
  'tribe.spartans':  'Spartans',
  'tribe.vikings':   'Vikings',

  // ── Errores globales ───────────────────────────────────
  'error.network':    'Verbindungsfehler. Bitte erneut versuchen.',
  'error.retry':      'Erneut versuchen',
  'error.loadFailed': 'Daten konnten nicht geladen werden.',

  // ── Versión ────────────────────────────────────────────
  'app.version': 'v0.1.0',

  // ── Placeholders de ruta ──────────────────────────────
  'placeholder.accounts.list':   'Kontenliste — demnächst',
  'placeholder.account.detail':  'Kontodetails — demnächst',
  'placeholder.world.space':     'Weltbereich — demnächst',
}

export default de
