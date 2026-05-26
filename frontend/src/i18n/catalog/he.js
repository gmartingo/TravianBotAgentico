/**
 * Catálogo HE — עברית (RTL)
 * [AUTO] Traducción automática — requiere revisión nativa.
 * RTL: el layout se espeja cuando este idioma está activo.
 */
const he = {
  // ── App ────────────────────────────────────────────────
  'app.name': 'TravianBot',

  // ── Navegación (sidebar) ────────────────────────────────
  'nav.accounts':     'חשבונות',
  'nav.resources':    'משאבים',
  'nav.troops':       'חיילים',
  'nav.construction': 'בנייה',
  'nav.comingSoon':   'בקרוב',

  // ── Topbar ─────────────────────────────────────────────
  'topbar.toggleTheme':    'החלף ערכת נושא',
  'topbar.selectLanguage': 'בחר שפה',
  'topbar.backToWorlds':   'עולמות →',
  'topbar.searchLanguage': 'חפש שפה…',

  // ── S2 — Lista de cuentas ───────────────────────────────
  'page.accounts.title':        'חשבונות',
  'page.accounts.caption':      '{n} חשבון',
  'page.accounts.caption.pl':   '{n} חשבונות',
  'page.accounts.newAccount':   'חשבון חדש',
  'page.accounts.empty.title':  'עדיין אין חשבונות',
  'page.accounts.empty.desc':   'הוסף את הראשון כדי להתחיל להשתמש בבוט.',
  'page.accounts.col.email':    'דוא"ל',
  'page.accounts.col.username': 'שם משתמש',
  'page.accounts.col.worlds':   'עולמות',
  'page.accounts.col.created':  'נוצר',
  'page.accounts.col.actions':  '',
  'page.accounts.action.edit':  'ערוך חשבון',
  'page.accounts.action.delete':'מחק חשבון',
  'page.accounts.loading':      'טוען חשבונות…',
  'page.accounts.error':        'לא ניתן לטעון את החשבונות.',

  // ── S3 — Wizard de alta ────────────────────────────────
  'wizard.title':                'חשבון חדש',
  'wizard.step':                 'שלב {current} מתוך {total}',
  'wizard.section.account':      'פרטי החשבון',
  'wizard.section.world':        'עולם ראשון',
  'wizard.field.email':          'דוא"ל',
  'wizard.field.email.ph':       'player@example.com',
  'wizard.field.username':       'שם משתמש',
  'wizard.field.username.ph':    'החשבון שלי',
  'wizard.field.password':       'סיסמה',
  'wizard.field.password.ph':    '••••••••',
  'wizard.field.server':         'כתובת השרת',
  'wizard.field.server.ph':      'https://ts1.x1.international.travian.com/',
  'wizard.field.tribe':          'שבט',
  'wizard.field.tribe.ph':       'בחר שבט',
  'wizard.btn.next':             'הבא',
  'wizard.btn.back':             'הקודם',
  'wizard.btn.create':           'צור חשבון',
  'wizard.btn.creating':         'יוצר…',
  'wizard.btn.cancel':           'ביטול',
  'wizard.error.email.invalid':  'הזן כתובת דוא"ל תקנית',
  'wizard.error.email.taken':    'כתובת דוא"ל זו כבר רשומה',
  'wizard.error.server.invalid': 'הזן כתובת URL תקנית (http:// או https://)',
  'wizard.error.server.taken':   'שרת זה כבר קיים בחשבון זה',
  'wizard.error.required':       'שדה זה הוא חובה',
  'wizard.error.tribe.required': 'בחר שבט',
  'wizard.btn.showPassword':     'הצג סיסמה',
  'wizard.btn.hidePassword':     'הסתר סיסמה',
  'wizard.toast.created':        'החשבון נוצר',

  // ── S4 — Detalle de cuenta ─────────────────────────────
  'page.account.breadcrumb':         'חשבונות',
  'page.account.createdAt':          'נוצר: {date}',
  'page.account.editBtn':            'ערוך',
  'page.account.deleteBtn':          'מחק חשבון',
  'page.account.worlds.title':       'עולמות ({n})',
  'page.account.worlds.add':         'הוסף עולם',
  'page.account.worlds.empty':       'עדיין אין עולמות בחשבון זה.',
  'page.account.col.server':         'שרת',
  'page.account.col.parsed':         'שרת (קריא)',
  'page.account.col.tribe':          'שבט',
  'page.account.col.session':        'סשן',
  'page.account.col.actions':        '',
  'page.account.action.deleteWorld': 'מחק עולם',
  'page.account.notFound.title':     'החשבון לא נמצא',
  'page.account.notFound.desc':      'החשבון שחיפשת אינו קיים או נמחק.',
  'page.account.notFound.back':      'חזור לחשבונות',

  // ── S5 — Modal editar cuenta ───────────────────────────
  'modal.edit.title':           'ערוך חשבון',
  'modal.edit.changePassword':  'שנה סיסמה',
  'modal.edit.newPassword':     'סיסמה חדשה',
  'modal.edit.confirmPassword': 'אשר סיסמה',
  'modal.edit.passwordMismatch':'הסיסמאות אינן תואמות',
  'modal.edit.saveBtn':         'שמור',
  'modal.edit.savingBtn':       'שומר…',
  'modal.edit.cancelBtn':       'ביטול',
  'modal.edit.closeBtn':        'סגור',
  'modal.edit.savedToast':      'השינויים נשמרו',
  'modal.edit.error409':        'כתובת דוא"ל זו רשומה בחשבון אחר.',

  // ── S6 — Modal añadir mundo ────────────────────────────
  'modal.addWorld.title':     'הוסף עולם',
  'modal.addWorld.addBtn':    'הוסף',
  'modal.addWorld.addingBtn': 'מוסיף…',
  'modal.addWorld.cancelBtn': 'ביטול',
  'modal.addWorld.toast':     'העולם נוסף',

  // ── S7 — Borrar cuenta ─────────────────────────────────
  'modal.deleteAccount.title':   'מחק חשבון',
  'modal.deleteAccount.body':    'למחוק את החשבון "{username}"?',
  'modal.deleteAccount.warning': 'לא ניתן לבטל פעולה זו. כל העולמות יימחקו גם הם ({n} עולם/עולמות).',
  'modal.deleteAccount.confirm': 'מחק',
  'modal.deleteAccount.cancel':  'ביטול',
  'modal.deleteAccount.toast':   'החשבון נמחק',
  'modal.deleteAccount.active':  'לא ניתן למחוק חשבון זה כאשר הבוט פעיל. עצור את הסשן תחילה.',
  'modal.deleteAccount.close':   'סגור',

  // ── S8 — Borrar mundo ──────────────────────────────────
  'modal.deleteWorld.title':   'מחק עולם',
  'modal.deleteWorld.body':    'למחוק את העולם "{parsed}"?',
  'modal.deleteWorld.warning': 'לא ניתן לבטל פעולה זו. כל הכפרים המשויכים יימחקו.',
  'modal.deleteWorld.confirm': 'מחק',
  'modal.deleteWorld.cancel':  'ביטול',
  'modal.deleteWorld.toast':   'העולם נמחק',
  'modal.deleteWorld.active':  'קיים סשן פעיל לעולם זה. עצור את הסשן תחילה.',

  // ── S9 — Espacio del mundo ─────────────────────────────
  'world.status.active':          'פעיל',
  'world.status.panelLabel':      'סשן פעיל',
  'world.action.stop':            'עצור',
  'world.tab.config':             'הגדרות',
  'world.tab.resources':          'משאבים',
  'world.tab.troops':             'חיילים',
  'world.tab.construction':       'בנייה',
  'world.tab.villages':           'כפרים',
  'world.config.automationTitle': 'אוטומציה',
  'world.config.tasksTitle':      'משימות הבוט',
  'world.config.tasksDesc':       'הפעל או השהה את המשימות האוטומטיות שהבוט מבצע בעולם זה.',
  'world.config.task.buildQueue': 'תור בנייה',
  'world.config.task.buildQueueDesc': 'בונה מבנים לפי התור המתוכנן',
  'world.config.task.farmList':   'רשימת חוות',
  'world.config.task.farmListDesc': 'שולח התקפות קציר אוטומטית',
  'world.config.task.troops':     'אימון חיילים',
  'world.config.task.troopsDesc': 'שומר על תור האימון פעיל',
  'world.config.intervalsTitle':  'מרווחי זמן',
  'world.config.intervalsDesc':   'זמן בין בדיקות הבוט. ערכים גבוהים יותר מפחיתים סיכון גילוי.',
  'world.config.interval.check':  'בדיקה תקופתית',
  'world.config.interval.farm':   'בין חוות',
  'world.config.interval.jitter': 'שינוי אקראי',
  'world.config.interval.min':    'דקות',
  'world.config.comingSoonTitle': 'בקרוב במרחב זה',
  'world.comingSoon.resourcesDesc':   'ניטור בזמן אמת של עץ, חימר, ברזל ותבואה.',
  'world.comingSoon.troopsDesc':      'מלאי יחידות, סטטיסטיקות קרב ותור אימון.',
  'world.comingSoon.constructionDesc':'תור מבנים לכל כפר, עלויות וזמנים.',
  'world.comingSoon.villagesDesc':    'מפת כפרים, קואורדינטות, שם וסוג.',
  'world.stop.toast':             'הבוט הופסק. חוזר לפרטי החשבון…',

  // ── Sesión del mundo (§4b) ─────────────────────────────
  'world.session.start':    'הפעל',
  'world.session.stop':     'עצור',
  'world.session.retry':    'נסה שוב',
  'world.session.cancel':   'ביטול',
  'world.session.enter':    'כניסה',
  'world.session.idle':     'לא פעיל',
  'world.session.connecting': 'מתחבר…',
  'world.session.active':   'פעיל',
  'world.session.error':    'שגיאת חיבור',
  'world.session.stopping': 'עוצר…',
  'world.session.start.aria': 'הפעל בוט ב-{world}',
  'world.session.stop.aria':  'עצור בוט ב-{world}',
  'world.session.retry.aria': 'נסה חיבור מחדש ב-{world}',
  'world.session.enter.aria': 'כנס למרחב של {world}',
  'world.session.disabled.delete':       'עצור את הסשן לפני מחיקת עולם זה',
  'world.session.disabled.editMenu':     'לא ניתן לערוך עולם עם סשן פעיל',
  'world.session.disabled.deleteAccount':'עצור את כל הסשנים הפעילים לפני מחיקת חשבון זה',
  'world.session.started.toast':  'הבוט הופעל ב-{world}',
  'world.session.stopped.toast':  'הבוט הופסק ב-{world}',
  'world.session.error.toast':    'לא ניתן להתחבר ב-{world}',

  // ── Tribus ──────────────────────────────────────────────
  'tribe.romans':    'Romans',
  'tribe.teutons':   'Teutons',
  'tribe.gauls':     'Gauls',
  'tribe.egyptians': 'Egyptians',
  'tribe.huns':      'Huns',
  'tribe.spartans':  'Spartans',
  'tribe.vikings':   'Vikings',

  // ── Errores globales ───────────────────────────────────
  'error.network':    'שגיאת חיבור. נסה שוב.',
  'error.retry':      'נסה שוב',
  'error.loadFailed': 'לא ניתן היה לטעון את הנתונים.',

  // ── Versión (sidebar footer) ───────────────────────────
  'app.version': 'v0.1.0',

  // ── Placeholders de ruta (etapa 1) ────────────────────
  'placeholder.accounts.list':   'רשימת חשבונות — בקרוב',
  'placeholder.account.detail':  'פרטי חשבון — בקרוב',
  'placeholder.world.space':     'מרחב עולם — בקרוב',
}

export default he
