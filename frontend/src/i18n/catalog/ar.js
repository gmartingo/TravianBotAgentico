/**
 * Catálogo AR — العربية (RTL)
 * [AUTO] Traducción automática — requiere revisión nativa.
 * RTL: el layout se espeja cuando este idioma está activo.
 */
const ar = {
  // ── App ────────────────────────────────────────────────
  'app.name': 'TravianBot',

  // ── Navegación (sidebar) ────────────────────────────────
  'nav.accounts':     'الحسابات',
  'nav.resources':    'الموارد',
  'nav.troops':       'الجيوش',
  'nav.construction': 'البناء',
  'nav.comingSoon':   'قريباً',

  // ── Topbar ─────────────────────────────────────────────
  'topbar.toggleTheme':    'تبديل المظهر',
  'topbar.selectLanguage': 'اختر اللغة',
  'topbar.backToWorlds':   'العوالم →',
  'topbar.searchLanguage': 'ابحث عن لغة…',

  // ── S2 — Lista de cuentas ───────────────────────────────
  'page.accounts.title':        'الحسابات',
  'page.accounts.caption':      '{n} حساب',
  'page.accounts.caption.pl':   '{n} حسابات',
  'page.accounts.newAccount':   'حساب جديد',
  'page.accounts.empty.title':  'لا توجد حسابات بعد',
  'page.accounts.empty.desc':   'أضف الأول لبدء استخدام البوت.',
  'page.accounts.col.email':    'البريد الإلكتروني',
  'page.accounts.col.username': 'اسم المستخدم',
  'page.accounts.col.worlds':   'العوالم',
  'page.accounts.col.created':  'أُنشئ',
  'page.accounts.col.actions':  '',
  'page.accounts.action.edit':  'تعديل الحساب',
  'page.accounts.action.delete':'حذف الحساب',
  'page.accounts.loading':      'جارٍ تحميل الحسابات…',
  'page.accounts.error':        'تعذّر تحميل الحسابات.',

  // ── S3 — Wizard de alta ────────────────────────────────
  'wizard.title':                'حساب جديد',
  'wizard.step':                 'الخطوة {current} من {total}',
  'wizard.section.account':      'بيانات الحساب',
  'wizard.section.world':        'العالم الأول',
  'wizard.field.email':          'البريد الإلكتروني',
  'wizard.field.email.ph':       'player@example.com',
  'wizard.field.username':       'اسم المستخدم',
  'wizard.field.username.ph':    'حسابي',
  'wizard.field.password':       'كلمة المرور',
  'wizard.field.password.ph':    '••••••••',
  'wizard.field.server':         'رابط الخادم',
  'wizard.field.server.ph':      'https://ts1.x1.international.travian.com/',
  'wizard.field.tribe':          'القبيلة',
  'wizard.field.tribe.ph':       'اختر قبيلة',
  'wizard.btn.next':             'التالي',
  'wizard.btn.back':             'السابق',
  'wizard.btn.create':           'إنشاء الحساب',
  'wizard.btn.creating':         'جاري الإنشاء…',
  'wizard.btn.cancel':           'إلغاء',
  'wizard.error.email.invalid':  'أدخل بريداً إلكترونياً صحيحاً',
  'wizard.error.email.taken':    'هذا البريد مسجّل مسبقاً',
  'wizard.error.server.invalid': 'أدخل رابطاً صحيحاً (http:// أو https://)',
  'wizard.error.server.taken':   'هذا الخادم موجود بالفعل في هذا الحساب',
  'wizard.error.required':       'هذا الحقل مطلوب',
  'wizard.error.tribe.required': 'اختر قبيلة',
  'wizard.btn.showPassword':     'إظهار كلمة المرور',
  'wizard.btn.hidePassword':     'إخفاء كلمة المرور',
  'wizard.toast.created':        'تم إنشاء الحساب',

  // ── S4 — Detalle de cuenta ─────────────────────────────
  'page.account.breadcrumb':         'الحسابات',
  'page.account.createdAt':          'أُنشئ: {date}',
  'page.account.editBtn':            'تعديل',
  'page.account.deleteBtn':          'حذف الحساب',
  'page.account.worlds.title':       'العوالم ({n})',
  'page.account.worlds.add':         'إضافة عالم',
  'page.account.worlds.empty':       'لا توجد عوالم في هذا الحساب بعد.',
  'page.account.col.server':         'الخادم',
  'page.account.col.parsed':         'الخادم (مقروء)',
  'page.account.col.tribe':          'القبيلة',
  'page.account.col.session':        'الجلسة',
  'page.account.col.actions':        '',
  'page.account.action.deleteWorld': 'حذف العالم',
  'page.account.notFound.title':     'الحساب غير موجود',
  'page.account.notFound.desc':      'الحساب الذي تبحث عنه غير موجود أو تم حذفه.',
  'page.account.notFound.back':      'العودة إلى الحسابات',

  // ── S5 — Modal editar cuenta ───────────────────────────
  'modal.edit.title':           'تعديل الحساب',
  'modal.edit.changePassword':  'تغيير كلمة المرور',
  'modal.edit.newPassword':     'كلمة المرور الجديدة',
  'modal.edit.confirmPassword': 'تأكيد كلمة المرور',
  'modal.edit.passwordMismatch':'كلمتا المرور غير متطابقتين',
  'modal.edit.saveBtn':         'حفظ',
  'modal.edit.savingBtn':       'جارٍ الحفظ…',
  'modal.edit.cancelBtn':       'إلغاء',
  'modal.edit.closeBtn':        'إغلاق',
  'modal.edit.savedToast':      'تم حفظ التغييرات',
  'modal.edit.error409':        'هذا البريد الإلكتروني مسجّل في حساب آخر.',

  // ── S6 — Modal añadir mundo ────────────────────────────
  'modal.addWorld.title':     'إضافة عالم',
  'modal.addWorld.addBtn':    'إضافة',
  'modal.addWorld.addingBtn': 'جارٍ الإضافة…',
  'modal.addWorld.cancelBtn': 'إلغاء',
  'modal.addWorld.toast':     'تمت إضافة العالم',

  // ── S7 — Borrar cuenta ─────────────────────────────────
  'modal.deleteAccount.title':   'حذف الحساب',
  'modal.deleteAccount.body':    'هل تريد حذف الحساب "{username}"؟',
  'modal.deleteAccount.warning': 'لا يمكن التراجع عن هذا الإجراء. سيتم حذف جميع العوالم أيضاً ({n} عالم/عوالم).',
  'modal.deleteAccount.confirm': 'حذف',
  'modal.deleteAccount.cancel':  'إلغاء',
  'modal.deleteAccount.toast':   'تم حذف الحساب',
  'modal.deleteAccount.active':  'لا يمكن حذف هذا الحساب أثناء وجود جلسة نشطة للبوت. أوقف الجلسة أولاً.',
  'modal.deleteAccount.close':   'إغلاق',

  // ── S8 — Borrar mundo ──────────────────────────────────
  'modal.deleteWorld.title':   'حذف العالم',
  'modal.deleteWorld.body':    'هل تريد حذف العالم "{parsed}"؟',
  'modal.deleteWorld.warning': 'لا يمكن التراجع عن هذا الإجراء. سيتم حذف جميع القرى المرتبطة.',
  'modal.deleteWorld.confirm': 'حذف',
  'modal.deleteWorld.cancel':  'إلغاء',
  'modal.deleteWorld.toast':   'تم حذف العالم',
  'modal.deleteWorld.active':  'توجد جلسة نشطة لهذا العالم. أوقف الجلسة أولاً.',

  // ── S9 — Espacio del mundo ─────────────────────────────
  'world.status.active':          'نشط',
  'world.status.panelLabel':      'جلسة نشطة',
  'world.action.stop':            'إيقاف',
  'world.tab.config':             'الإعدادات',
  'world.tab.resources':          'الموارد',
  'world.tab.troops':             'الجيوش',
  'world.tab.construction':       'البناء',
  'world.tab.villages':           'القرى',
  'world.config.automationTitle': 'الأتمتة',
  'world.config.tasksTitle':      'مهام البوت',
  'world.config.tasksDesc':       'فعّل أو أوقف المهام التلقائية التي يُنفّذها البوت في هذا العالم.',
  'world.config.task.buildQueue': 'قائمة البناء',
  'world.config.task.buildQueueDesc': 'يبني المباني وفق القائمة المجدولة',
  'world.config.task.farmList':   'قائمة المزارع',
  'world.config.task.farmListDesc': 'يرسل هجمات الحصاد تلقائياً',
  'world.config.task.troops':     'تدريب الجيوش',
  'world.config.task.troopsDesc': 'يحافظ على قائمة التدريب نشطة',
  'world.config.intervalsTitle':  'الفترات الزمنية',
  'world.config.intervalsDesc':   'الوقت بين فحوصات البوت. القيم الأعلى تقلل خطر الاكتشاف.',
  'world.config.interval.check':  'الفحص الدوري',
  'world.config.interval.farm':   'بين المزارع',
  'world.config.interval.jitter': 'تباين عشوائي',
  'world.config.interval.min':    'دقيقة',
  'world.config.comingSoonTitle': 'قريباً في هذه المساحة',
  'world.comingSoon.resourcesDesc':   'مراقبة فورية للخشب والطين والحديد والحبوب.',
  'world.comingSoon.troopsDesc':      'جرد الوحدات وإحصاءات القتال وقائمة التدريب.',
  'world.comingSoon.constructionDesc':'قائمة المباني لكل قرية، والتكاليف والأوقات.',
  'world.comingSoon.villagesDesc':    'خريطة القرى والإحداثيات والاسم والنوع.',
  'world.stop.toast':             'تم إيقاف البوت. العودة إلى تفاصيل الحساب…',

  // ── Sesión del mundo (§4b) ─────────────────────────────
  'world.session.start':    'تشغيل',
  'world.session.stop':     'إيقاف',
  'world.session.retry':    'إعادة المحاولة',
  'world.session.cancel':   'إلغاء',
  'world.session.enter':    'دخول',
  'world.session.idle':     'غير نشط',
  'world.session.connecting': 'جارٍ الاتصال…',
  'world.session.active':   'نشط',
  'world.session.error':    'خطأ في الاتصال',
  'world.session.stopping': 'جارٍ الإيقاف…',
  'world.session.start.aria': 'تشغيل البوت في {world}',
  'world.session.stop.aria':  'إيقاف البوت في {world}',
  'world.session.retry.aria': 'إعادة الاتصال في {world}',
  'world.session.enter.aria': 'الدخول إلى مساحة {world}',
  'world.session.disabled.delete':       'أوقف الجلسة قبل حذف هذا العالم',
  'world.session.disabled.editMenu':     'لا يمكن تعديل عالم بجلسة نشطة',
  'world.session.disabled.deleteAccount':'أوقف جميع الجلسات النشطة قبل حذف هذا الحساب',
  'world.session.started.toast':  'تم تشغيل البوت في {world}',
  'world.session.stopped.toast':  'تم إيقاف البوت في {world}',
  'world.session.error.toast':    'تعذّر الاتصال في {world}',

  // ── Tribus ──────────────────────────────────────────────
  'tribe.romans':    'Romans',
  'tribe.teutons':   'Teutons',
  'tribe.gauls':     'Gauls',
  'tribe.egyptians': 'Egyptians',
  'tribe.huns':      'Huns',
  'tribe.spartans':  'Spartans',
  'tribe.vikings':   'Vikings',

  // ── Errores globales ───────────────────────────────────
  'error.network':    'خطأ في الاتصال. حاول مرة أخرى.',
  'error.retry':      'إعادة المحاولة',
  'error.loadFailed': 'تعذّر تحميل البيانات.',

  // ── Versión (sidebar footer) ───────────────────────────
  'app.version': 'v0.1.0',

  // ── Placeholders de ruta (etapa 1) ────────────────────
  'placeholder.accounts.list':   'قائمة الحسابات — قريباً',
  'placeholder.account.detail':  'تفاصيل الحساب — قريباً',
  'placeholder.world.space':     'مساحة العالم — قريباً',
}

export default ar
