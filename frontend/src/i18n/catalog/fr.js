/**
 * Catálogo FR — Français
 * [AUTO] Traducción automática — requiere revisión nativa.
 * Claves no presentes aquí hacen fallback al catálogo 'es'.
 */
const fr = {
  // ── App ────────────────────────────────────────────────
  'app.name': 'TravianBot',

  // ── Navegación (sidebar) ────────────────────────────────
  'nav.accounts':     'Comptes',
  'nav.resources':    'Ressources',
  'nav.troops':       'Troupes',
  'nav.construction': 'Construction',
  'nav.comingSoon':   'Bientôt',

  // ── Topbar ─────────────────────────────────────────────
  'topbar.toggleTheme':    'Changer le thème',
  'topbar.selectLanguage': 'Sélectionner la langue',
  'topbar.backToWorlds':   '← Mondes',
  'topbar.searchLanguage': 'Rechercher une langue…',

  // ── S2 — Lista de cuentas ───────────────────────────────
  'page.accounts.title':        'Comptes',
  'page.accounts.caption':      '{n} compte',
  'page.accounts.caption.pl':   '{n} comptes',
  'page.accounts.newAccount':   'Nouveau compte',
  'page.accounts.empty.title':  "Aucun compte pour l'instant",
  'page.accounts.empty.desc':   'Ajoutez le premier pour commencer à utiliser le bot.',
  'page.accounts.col.email':    'Email',
  'page.accounts.col.username': "Nom d'utilisateur",
  'page.accounts.col.worlds':   'Mondes',
  'page.accounts.col.created':  'Créé',
  'page.accounts.col.actions':  '',
  'page.accounts.action.edit':  'Modifier le compte',
  'page.accounts.action.delete':'Supprimer le compte',
  'page.accounts.loading':      'Chargement des comptes…',
  'page.accounts.error':        'Impossible de charger les comptes.',

  // ── S3 — Wizard de alta ────────────────────────────────
  'wizard.title':                'Nouveau compte',
  'wizard.step':                 'Étape {current} sur {total}',
  'wizard.section.account':      'Données du compte',
  'wizard.section.world':        'Premier monde',
  'wizard.field.email':          'Email',
  'wizard.field.email.ph':       'joueur@exemple.fr',
  'wizard.field.username':       'Nom d\'utilisateur',
  'wizard.field.username.ph':    'MonCompte',
  'wizard.field.password':       'Mot de passe',
  'wizard.field.password.ph':    '••••••••',
  'wizard.field.server':         'URL du serveur',
  'wizard.field.server.ph':      'https://ts1.x1.international.travian.com/',
  'wizard.field.tribe':          'Tribu',
  'wizard.field.tribe.ph':       'Sélectionner une tribu',
  'wizard.btn.next':             'Suivant',
  'wizard.btn.back':             'Retour',
  'wizard.btn.create':           'Créer le compte',
  'wizard.btn.creating':         'Création…',
  'wizard.btn.cancel':           'Annuler',
  'wizard.error.email.invalid':  'Saisir un email valide',
  'wizard.error.email.taken':    'Cet email est déjà enregistré',
  'wizard.error.server.invalid': 'Saisir une URL valide (http:// ou https://)',
  'wizard.error.server.taken':   'Ce serveur existe déjà dans ce compte',
  'wizard.error.required':       'Ce champ est obligatoire',
  'wizard.error.tribe.required': 'Sélectionner une tribu',
  'wizard.btn.showPassword':     'Afficher le mot de passe',
  'wizard.btn.hidePassword':     'Masquer le mot de passe',
  'wizard.toast.created':        'Compte créé',

  // ── S4 — Detalle de cuenta ─────────────────────────────
  'page.account.breadcrumb':         'Comptes',
  'page.account.createdAt':          'Créé le : {date}',
  'page.account.editBtn':            'Modifier',
  'page.account.deleteBtn':          'Supprimer le compte',
  'page.account.worlds.title':       'Mondes ({n})',
  'page.account.worlds.add':         'Ajouter un monde',
  'page.account.worlds.empty':       "Pas encore de mondes dans ce compte.",
  'page.account.col.server':         'Serveur',
  'page.account.col.parsed':         'Serveur (lisible)',
  'page.account.col.tribe':          'Tribu',
  'page.account.col.session':        'Session',
  'page.account.col.actions':        '',
  'page.account.action.deleteWorld': 'Supprimer le monde',
  'page.account.notFound.title':     'Compte introuvable',
  'page.account.notFound.desc':      "Le compte recherché n'existe pas ou a été supprimé.",
  'page.account.notFound.back':      'Retour aux comptes',

  // ── S5 — Modal editar cuenta ───────────────────────────
  'modal.edit.title':           'Modifier le compte',
  'modal.edit.changePassword':  'Changer le mot de passe',
  'modal.edit.newPassword':     'Nouveau mot de passe',
  'modal.edit.confirmPassword': 'Confirmer le mot de passe',
  'modal.edit.passwordMismatch':'Les mots de passe ne correspondent pas',
  'modal.edit.saveBtn':         'Enregistrer',
  'modal.edit.savingBtn':       'Enregistrement…',
  'modal.edit.cancelBtn':       'Annuler',
  'modal.edit.closeBtn':        'Fermer',
  'modal.edit.savedToast':      'Modifications enregistrées',
  'modal.edit.error409':        'Cet email est déjà utilisé par un autre compte.',

  // ── S6 — Modal añadir mundo ────────────────────────────
  'modal.addWorld.title':     'Ajouter un monde',
  'modal.addWorld.addBtn':    'Ajouter',
  'modal.addWorld.addingBtn': 'Ajout en cours…',
  'modal.addWorld.cancelBtn': 'Annuler',
  'modal.addWorld.toast':     'Monde ajouté',

  // ── S7 — Borrar cuenta ─────────────────────────────────
  'modal.deleteAccount.title':   'Supprimer le compte',
  'modal.deleteAccount.body':    'Supprimer le compte "{username}" ?',
  'modal.deleteAccount.warning': 'Cette action est irréversible. Tous ses mondes ({n} monde(s)) seront également supprimés.',
  'modal.deleteAccount.confirm': 'Supprimer',
  'modal.deleteAccount.cancel':  'Annuler',
  'modal.deleteAccount.toast':   'Compte supprimé',
  'modal.deleteAccount.active':  "Impossible de supprimer ce compte tant que le bot a une session active. Arrêtez la session d'abord.",
  'modal.deleteAccount.close':   'Fermer',

  // ── S8 — Borrar mundo ──────────────────────────────────
  'modal.deleteWorld.title':   'Supprimer le monde',
  'modal.deleteWorld.body':    'Supprimer le monde "{parsed}" ?',
  'modal.deleteWorld.warning': 'Cette action est irréversible. Tous les villages associés seront également supprimés.',
  'modal.deleteWorld.confirm': 'Supprimer',
  'modal.deleteWorld.cancel':  'Annuler',
  'modal.deleteWorld.toast':   'Monde supprimé',
  'modal.deleteWorld.active':  'Il y a une session active pour ce monde. Arrêtez la session en premier.',

  // ── S9 — Espacio del mundo ─────────────────────────────
  'world.status.active':          'Actif',
  'world.status.panelLabel':      'Session active',
  'world.action.stop':            'Arrêter',
  'world.tab.config':             'Configuration',
  'world.tab.resources':          'Ressources',
  'world.tab.troops':             'Troupes',
  'world.tab.construction':       'Construction',
  'world.tab.villages':           'Villages',
  'world.config.automationTitle': 'Automatisation',
  'world.config.tasksTitle':      'Tâches du bot',
  'world.config.tasksDesc':       'Activez ou mettez en pause les tâches automatiques que le bot exécute dans ce monde.',
  'world.config.task.buildQueue': 'File de construction',
  'world.config.task.buildQueueDesc': 'Construit des bâtiments selon la file planifiée',
  'world.config.task.farmList':   'Liste de fermes',
  'world.config.task.farmListDesc': 'Envoie des attaques de farming automatiquement',
  'world.config.task.troops':     "Entraînement de troupes",
  'world.config.task.troopsDesc': "Maintient la file d'entraînement active",
  'world.config.intervalsTitle':  'Intervalles',
  'world.config.intervalsDesc':   'Temps entre les vérifications du bot. Des valeurs plus élevées réduisent le risque de détection.',
  'world.config.interval.check':  'Vérification périodique',
  'world.config.interval.farm':   'Entre les fermes',
  'world.config.interval.jitter': 'Variation aléatoire',
  'world.config.interval.min':    'min',
  'world.config.comingSoonTitle': 'Bientôt dans cet espace',
  'world.comingSoon.resourcesDesc':   'Surveillance en temps réel du bois, de l\'argile, du fer et des céréales.',
  'world.comingSoon.troopsDesc':      "Inventaire des unités, statistiques de combat et file d'entraînement.",
  'world.comingSoon.constructionDesc':'File de construction par village, coûts et délais.',
  'world.comingSoon.villagesDesc':    'Carte des villages, coordonnées, nom et type.',
  'world.stop.toast':             'Bot arrêté. Retour aux détails du compte…',

  // ── Sesión del mundo ───────────────────────────────────
  'world.session.start':    'Démarrer',
  'world.session.stop':     'Arrêter',
  'world.session.retry':    'Réessayer',
  'world.session.cancel':   'Annuler',
  'world.session.enter':    'Entrer',
  'world.session.idle':     'Inactif',
  'world.session.connecting': 'Connexion…',
  'world.session.active':   'Actif',
  'world.session.error':    'Erreur de connexion',
  'world.session.stopping': 'Arrêt…',
  'world.session.start.aria': 'Démarrer le bot sur {world}',
  'world.session.stop.aria':  'Arrêter le bot sur {world}',
  'world.session.retry.aria': 'Réessayer la connexion sur {world}',
  'world.session.enter.aria': "Entrer dans l'espace de {world}",
  'world.session.disabled.delete':       'Arrêter la session avant de supprimer ce monde',
  'world.session.disabled.editMenu':     'Impossible de modifier un monde avec une session active',
  'world.session.disabled.deleteAccount':'Arrêter toutes les sessions actives avant de supprimer ce compte',
  'world.session.started.toast':  'Bot démarré sur {world}',
  'world.session.stopped.toast':  'Bot arrêté sur {world}',
  'world.session.error.toast':    'Impossible de se connecter à {world}',

  // ── Tribus ──────────────────────────────────────────────
  'tribe.romans':    'Romans',
  'tribe.teutons':   'Teutons',
  'tribe.gauls':     'Gauls',
  'tribe.egyptians': 'Egyptians',
  'tribe.huns':      'Huns',
  'tribe.spartans':  'Spartans',
  'tribe.vikings':   'Vikings',

  // ── Errores globales ───────────────────────────────────
  'error.network':    'Erreur de connexion. Veuillez réessayer.',
  'error.retry':      'Réessayer',
  'error.loadFailed': "Les données n'ont pas pu être chargées.",

  // ── Versión ────────────────────────────────────────────
  'app.version': 'v0.1.0',

  // ── Placeholders de ruta ──────────────────────────────
  'placeholder.accounts.list':   'Liste des comptes — bientôt',
  'placeholder.account.detail':  'Détails du compte — bientôt',
  'placeholder.world.space':     'Espace monde — bientôt',
}

export default fr
