/**
 * Catálogo NL — Nederlands
 * [AUTO] Traducción automática — requiere revisión nativa.
 * Claves no presentes aquí hacen fallback al catálogo 'es'.
 */
const nl = {
  // ── App ────────────────────────────────────────────────
  'app.name': 'TravianBot',

  // ── Navegación (sidebar) ────────────────────────────────
  'nav.accounts':     'Accounts',
  'nav.resources':    'Grondstoffen',
  'nav.troops':       'Troepen',
  'nav.construction': 'Bouw',
  'nav.comingSoon':   'Binnenkort',

  // ── Topbar ─────────────────────────────────────────────
  'topbar.toggleTheme':    'Thema wisselen',
  'topbar.selectLanguage': 'Taal kiezen',
  'topbar.backToWorlds':   '← Werelden',
  'topbar.searchLanguage': 'Taal zoeken…',

  // ── S2 — Lista de cuentas ───────────────────────────────
  'page.accounts.title':        'Accounts',
  'page.accounts.caption':      '{n} account',
  'page.accounts.caption.pl':   '{n} accounts',
  'page.accounts.newAccount':   'Nieuw account',
  'page.accounts.empty.title':  'Nog geen accounts',
  'page.accounts.empty.desc':   'Voeg de eerste toe om de bot te gebruiken.',
  'page.accounts.col.email':    'E-mail',
  'page.accounts.col.username': 'Gebruikersnaam',
  'page.accounts.col.worlds':   'Werelden',
  'page.accounts.col.created':  'Aangemaakt',
  'page.accounts.col.actions':  '',
  'page.accounts.action.edit':  'Account bewerken',
  'page.accounts.action.delete':'Account verwijderen',
  'page.accounts.loading':      'Accounts laden…',
  'page.accounts.error':        'Accounts konden niet worden geladen.',

  // ── S3 — Wizard de alta ────────────────────────────────
  'wizard.title':                'Nieuw account',
  'wizard.step':                 'Stap {current} van {total}',
  'wizard.section.account':      'Accountgegevens',
  'wizard.section.world':        'Eerste wereld',
  'wizard.field.email':          'E-mail',
  'wizard.field.email.ph':       'speler@voorbeeld.nl',
  'wizard.field.username':       'Gebruikersnaam',
  'wizard.field.username.ph':    'MijnAccount',
  'wizard.field.password':       'Wachtwoord',
  'wizard.field.password.ph':    '••••••••',
  'wizard.field.server':         'Server-URL',
  'wizard.field.server.ph':      'https://ts1.x1.international.travian.com/',
  'wizard.field.tribe':          'Stam',
  'wizard.field.tribe.ph':       'Selecteer een stam',
  'wizard.btn.next':             'Volgende',
  'wizard.btn.back':             'Terug',
  'wizard.btn.create':           'Account aanmaken',
  'wizard.btn.creating':         'Aanmaken…',
  'wizard.btn.cancel':           'Annuleren',
  'wizard.error.email.invalid':  'Voer een geldig e-mailadres in',
  'wizard.error.email.taken':    'Dit e-mailadres is al geregistreerd',
  'wizard.error.server.invalid': 'Voer een geldige URL in (http:// of https://)',
  'wizard.error.server.taken':   'Deze server bestaat al in dit account',
  'wizard.error.required':       'Dit veld is verplicht',
  'wizard.error.tribe.required': 'Selecteer een stam',
  'wizard.btn.showPassword':     'Wachtwoord tonen',
  'wizard.btn.hidePassword':     'Wachtwoord verbergen',
  'wizard.toast.created':        'Account aangemaakt',

  // ── S4 — Detalle de cuenta ─────────────────────────────
  'page.account.breadcrumb':         'Accounts',
  'page.account.createdAt':          'Aangemaakt: {date}',
  'page.account.editBtn':            'Bewerken',
  'page.account.deleteBtn':          'Account verwijderen',
  'page.account.worlds.title':       'Werelden ({n})',
  'page.account.worlds.add':         'Wereld toevoegen',
  'page.account.worlds.empty':       'Nog geen werelden in dit account.',
  'page.account.col.server':         'Server',
  'page.account.col.parsed':         'Server (leesbaar)',
  'page.account.col.tribe':          'Stam',
  'page.account.col.session':        'Sessie',
  'page.account.col.actions':        '',
  'page.account.action.deleteWorld': 'Wereld verwijderen',
  'page.account.notFound.title':     'Account niet gevonden',
  'page.account.notFound.desc':      'Het gezochte account bestaat niet of is verwijderd.',
  'page.account.notFound.back':      'Terug naar accounts',

  // ── S5 — Modal editar cuenta ───────────────────────────
  'modal.edit.title':           'Account bewerken',
  'modal.edit.changePassword':  'Wachtwoord wijzigen',
  'modal.edit.newPassword':     'Nieuw wachtwoord',
  'modal.edit.confirmPassword': 'Wachtwoord bevestigen',
  'modal.edit.passwordMismatch':'Wachtwoorden komen niet overeen',
  'modal.edit.saveBtn':         'Opslaan',
  'modal.edit.savingBtn':       'Opslaan…',
  'modal.edit.cancelBtn':       'Annuleren',
  'modal.edit.closeBtn':        'Sluiten',
  'modal.edit.savedToast':      'Wijzigingen opgeslagen',
  'modal.edit.error409':        'Dit e-mailadres is al in gebruik door een ander account.',

  // ── S6 — Modal añadir mundo ────────────────────────────
  'modal.addWorld.title':     'Wereld toevoegen',
  'modal.addWorld.addBtn':    'Toevoegen',
  'modal.addWorld.addingBtn': 'Toevoegen…',
  'modal.addWorld.cancelBtn': 'Annuleren',
  'modal.addWorld.toast':     'Wereld toegevoegd',

  // ── S7 — Borrar cuenta ─────────────────────────────────
  'modal.deleteAccount.title':   'Account verwijderen',
  'modal.deleteAccount.body':    'Account "{username}" verwijderen?',
  'modal.deleteAccount.warning': 'Deze actie kan niet ongedaan worden gemaakt. Alle bijbehorende werelden ({n} wereld(en)) worden ook verwijderd.',
  'modal.deleteAccount.confirm': 'Verwijderen',
  'modal.deleteAccount.cancel':  'Annuleren',
  'modal.deleteAccount.toast':   'Account verwijderd',
  'modal.deleteAccount.active':  'Dit account kan niet worden verwijderd zolang de bot een actieve sessie heeft. Stop de sessie eerst.',
  'modal.deleteAccount.close':   'Sluiten',

  // ── S8 — Borrar mundo ──────────────────────────────────
  'modal.deleteWorld.title':   'Wereld verwijderen',
  'modal.deleteWorld.body':    'Wereld "{parsed}" verwijderen?',
  'modal.deleteWorld.warning': 'Deze actie kan niet ongedaan worden gemaakt. Alle bijbehorende dorpen worden ook verwijderd.',
  'modal.deleteWorld.confirm': 'Verwijderen',
  'modal.deleteWorld.cancel':  'Annuleren',
  'modal.deleteWorld.toast':   'Wereld verwijderd',
  'modal.deleteWorld.active':  'Er is een actieve sessie voor deze wereld. Stop de sessie eerst.',

  // ── S9 — Espacio del mundo ─────────────────────────────
  'world.status.active':          'Actief',
  'world.status.panelLabel':      'Actieve sessie',
  'world.action.stop':            'Stoppen',
  'world.tab.config':             'Configuratie',
  'world.tab.resources':          'Grondstoffen',
  'world.tab.troops':             'Troepen',
  'world.tab.construction':       'Bouw',
  'world.tab.villages':           'Dorpen',
  'world.config.automationTitle': 'Automatisering',
  'world.config.tasksTitle':      'Bot-taken',
  'world.config.tasksDesc':       'Activeer of pauzeer de automatische taken die de bot in deze wereld uitvoert.',
  'world.config.task.buildQueue': 'Bouwwachtrij',
  'world.config.task.buildQueueDesc': 'Bouwt gebouwen volgens de geplande wachtrij',
  'world.config.task.farmList':   'Farmlijst',
  'world.config.task.farmListDesc': 'Stuurt automatisch farmaanvallen',
  'world.config.task.troops':     'Troepen trainen',
  'world.config.task.troopsDesc': 'Houdt de trainingswachtrij actief',
  'world.config.intervalsTitle':  'Intervallen',
  'world.config.intervalsDesc':   'Tijd tussen bot-controles. Hogere waarden verminderen het detectierisico.',
  'world.config.interval.check':  'Periodieke controle',
  'world.config.interval.farm':   'Tussen farms',
  'world.config.interval.jitter': 'Willekeurige variatie',
  'world.config.interval.min':    'min',
  'world.config.comingSoonTitle': 'Binnenkort in deze ruimte',
  'world.comingSoon.resourcesDesc':   'Realtime monitoring van hout, klei, ijzer en graan.',
  'world.comingSoon.troopsDesc':      'Eenhedeninventaris, gevechtsstatistieken en trainingswachtrij.',
  'world.comingSoon.constructionDesc':'Bouwwachtrij per dorp, kosten en tijden.',
  'world.comingSoon.villagesDesc':    'Dorpenkaart, coördinaten, naam en type.',
  'world.stop.toast':             'Bot gestopt. Terug naar accountdetails…',

  // ── Sesión del mundo ───────────────────────────────────
  'world.session.start':    'Starten',
  'world.session.stop':     'Stoppen',
  'world.session.retry':    'Opnieuw proberen',
  'world.session.cancel':   'Annuleren',
  'world.session.enter':    'Binnengaan',
  'world.session.idle':     'Inactief',
  'world.session.connecting': 'Verbinden…',
  'world.session.active':   'Actief',
  'world.session.error':    'Verbindingsfout',
  'world.session.stopping': 'Stoppen…',
  'world.session.start.aria': 'Bot starten op {world}',
  'world.session.stop.aria':  'Bot stoppen op {world}',
  'world.session.retry.aria': 'Verbinding opnieuw proberen op {world}',
  'world.session.enter.aria': 'De ruimte van {world} betreden',
  'world.session.disabled.delete':       'Stop de sessie voordat je deze wereld verwijdert',
  'world.session.disabled.editMenu':     'Een wereld met actieve sessie kan niet worden bewerkt',
  'world.session.disabled.deleteAccount':'Stop alle actieve sessies voordat je dit account verwijdert',
  'world.session.started.toast':  'Bot gestart op {world}',
  'world.session.stopped.toast':  'Bot gestopt op {world}',
  'world.session.error.toast':    'Kon geen verbinding maken met {world}',

  // ── Tribus ──────────────────────────────────────────────
  'tribe.romans':    'Romans',
  'tribe.teutons':   'Teutons',
  'tribe.gauls':     'Gauls',
  'tribe.egyptians': 'Egyptians',
  'tribe.huns':      'Huns',
  'tribe.spartans':  'Spartans',
  'tribe.vikings':   'Vikings',

  // ── Errores globales ───────────────────────────────────
  'error.network':    'Verbindingsfout. Probeer het opnieuw.',
  'error.retry':      'Opnieuw proberen',
  'error.loadFailed': 'Gegevens konden niet worden geladen.',

  // ── Versión ────────────────────────────────────────────
  'app.version': 'v0.1.0',

  // ── Placeholders de ruta ──────────────────────────────
  'placeholder.accounts.list':   'Accountlijst — binnenkort',
  'placeholder.account.detail':  'Accountdetails — binnenkort',
  'placeholder.world.space':     'Wereldruimte — binnenkort',
}

export default nl
