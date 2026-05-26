/**
 * Catálogo FA — فارسی (RTL)
 * [AUTO] Traducción automática — requiere revisión nativa.
 * RTL: el layout se espeja cuando este idioma está activo.
 */
const fa = {
  // ── App ────────────────────────────────────────────────
  'app.name': 'TravianBot',

  // ── Navegación (sidebar) ────────────────────────────────
  'nav.accounts':     'حساب‌ها',
  'nav.resources':    'منابع',
  'nav.troops':       'سربازان',
  'nav.construction': 'ساخت و ساز',
  'nav.comingSoon':   'به زودی',

  // ── Topbar ─────────────────────────────────────────────
  'topbar.toggleTheme':    'تغییر تم',
  'topbar.selectLanguage': 'انتخاب زبان',
  'topbar.backToWorlds':   'دنیاها →',
  'topbar.searchLanguage': 'جستجوی زبان…',

  // ── S2 — Lista de cuentas ───────────────────────────────
  'page.accounts.title':        'حساب‌ها',
  'page.accounts.caption':      '{n} حساب',
  'page.accounts.caption.pl':   '{n} حساب',
  'page.accounts.newAccount':   'حساب جدید',
  'page.accounts.empty.title':  'هنوز حسابی وجود ندارد',
  'page.accounts.empty.desc':   'اولین را اضافه کنید تا از ربات استفاده کنید.',
  'page.accounts.col.email':    'ایمیل',
  'page.accounts.col.username': 'نام کاربری',
  'page.accounts.col.worlds':   'دنیاها',
  'page.accounts.col.created':  'ایجاد شد',
  'page.accounts.col.actions':  '',
  'page.accounts.action.edit':  'ویرایش حساب',
  'page.accounts.action.delete':'حذف حساب',
  'page.accounts.loading':      'در حال بارگذاری حساب‌ها…',
  'page.accounts.error':        'بارگذاری حساب‌ها ممکن نشد.',

  // ── S3 — Wizard de alta ────────────────────────────────
  'wizard.title':                'حساب جدید',
  'wizard.step':                 'مرحله {current} از {total}',
  'wizard.section.account':      'اطلاعات حساب',
  'wizard.section.world':        'اولین دنیا',
  'wizard.field.email':          'ایمیل',
  'wizard.field.email.ph':       'player@example.com',
  'wizard.field.username':       'نام کاربری',
  'wizard.field.username.ph':    'حساب من',
  'wizard.field.password':       'رمز عبور',
  'wizard.field.password.ph':    '••••••••',
  'wizard.field.server':         'آدرس سرور',
  'wizard.field.server.ph':      'https://ts1.x1.international.travian.com/',
  'wizard.field.tribe':          'قبیله',
  'wizard.field.tribe.ph':       'یک قبیله انتخاب کنید',
  'wizard.btn.next':             'بعدی',
  'wizard.btn.back':             'قبلی',
  'wizard.btn.create':           'ایجاد حساب',
  'wizard.btn.creating':         'در حال ایجاد…',
  'wizard.btn.cancel':           'لغو',
  'wizard.error.email.invalid':  'یک ایمیل معتبر وارد کنید',
  'wizard.error.email.taken':    'این ایمیل قبلاً ثبت شده است',
  'wizard.error.server.invalid': 'یک آدرس معتبر وارد کنید (http:// یا https://)',
  'wizard.error.server.taken':   'این سرور از قبل در این حساب وجود دارد',
  'wizard.error.required':       'این فیلد الزامی است',
  'wizard.error.tribe.required': 'یک قبیله انتخاب کنید',
  'wizard.btn.showPassword':     'نمایش رمز عبور',
  'wizard.btn.hidePassword':     'پنهان کردن رمز عبور',
  'wizard.toast.created':        'حساب ایجاد شد',

  // ── S4 — Detalle de cuenta ─────────────────────────────
  'page.account.breadcrumb':         'حساب‌ها',
  'page.account.createdAt':          'ایجاد شد: {date}',
  'page.account.editBtn':            'ویرایش',
  'page.account.deleteBtn':          'حذف حساب',
  'page.account.worlds.title':       'دنیاها ({n})',
  'page.account.worlds.add':         'افزودن دنیا',
  'page.account.worlds.empty':       'هنوز هیچ دنیایی در این حساب وجود ندارد.',
  'page.account.col.server':         'سرور',
  'page.account.col.parsed':         'سرور (خوانا)',
  'page.account.col.tribe':          'قبیله',
  'page.account.col.session':        'جلسه',
  'page.account.col.actions':        '',
  'page.account.action.deleteWorld': 'حذف دنیا',
  'page.account.notFound.title':     'حساب یافت نشد',
  'page.account.notFound.desc':      'حسابی که دنبال آن هستید وجود ندارد یا حذف شده است.',
  'page.account.notFound.back':      'بازگشت به حساب‌ها',

  // ── S5 — Modal editar cuenta ───────────────────────────
  'modal.edit.title':           'ویرایش حساب',
  'modal.edit.changePassword':  'تغییر رمز عبور',
  'modal.edit.newPassword':     'رمز عبور جدید',
  'modal.edit.confirmPassword': 'تأیید رمز عبور',
  'modal.edit.passwordMismatch':'رمزهای عبور مطابقت ندارند',
  'modal.edit.saveBtn':         'ذخیره',
  'modal.edit.savingBtn':       'در حال ذخیره…',
  'modal.edit.cancelBtn':       'لغو',
  'modal.edit.closeBtn':        'بستن',
  'modal.edit.savedToast':      'تغییرات ذخیره شد',
  'modal.edit.error409':        'این ایمیل در حساب دیگری ثبت شده است.',

  // ── S6 — Modal añadir mundo ────────────────────────────
  'modal.addWorld.title':     'افزودن دنیا',
  'modal.addWorld.addBtn':    'افزودن',
  'modal.addWorld.addingBtn': 'در حال افزودن…',
  'modal.addWorld.cancelBtn': 'لغو',
  'modal.addWorld.toast':     'دنیا اضافه شد',

  // ── S7 — Borrar cuenta ─────────────────────────────────
  'modal.deleteAccount.title':   'حذف حساب',
  'modal.deleteAccount.body':    'آیا می‌خواهید حساب "{username}" را حذف کنید؟',
  'modal.deleteAccount.warning': 'این عمل قابل بازگشت نیست. همه دنیاها نیز حذف خواهند شد ({n} دنیا).',
  'modal.deleteAccount.confirm': 'حذف',
  'modal.deleteAccount.cancel':  'لغو',
  'modal.deleteAccount.toast':   'حساب حذف شد',
  'modal.deleteAccount.active':  'در حالی که ربات یک جلسه فعال دارد نمی‌توان این حساب را حذف کرد. ابتدا جلسه را متوقف کنید.',
  'modal.deleteAccount.close':   'بستن',

  // ── S8 — Borrar mundo ──────────────────────────────────
  'modal.deleteWorld.title':   'حذف دنیا',
  'modal.deleteWorld.body':    'آیا می‌خواهید دنیای "{parsed}" را حذف کنید؟',
  'modal.deleteWorld.warning': 'این عمل قابل بازگشت نیست. همه دهکده‌های مرتبط نیز حذف خواهند شد.',
  'modal.deleteWorld.confirm': 'حذف',
  'modal.deleteWorld.cancel':  'لغو',
  'modal.deleteWorld.toast':   'دنیا حذف شد',
  'modal.deleteWorld.active':  'یک جلسه فعال برای این دنیا وجود دارد. ابتدا جلسه را متوقف کنید.',

  // ── S9 — Espacio del mundo ─────────────────────────────
  'world.status.active':          'فعال',
  'world.status.panelLabel':      'جلسه فعال',
  'world.action.stop':            'توقف',
  'world.tab.config':             'تنظیمات',
  'world.tab.resources':          'منابع',
  'world.tab.troops':             'سربازان',
  'world.tab.construction':       'ساخت و ساز',
  'world.tab.villages':           'دهکده‌ها',
  'world.config.automationTitle': 'اتوماسیون',
  'world.config.tasksTitle':      'وظایف ربات',
  'world.config.tasksDesc':       'وظایف خودکاری که ربات در این دنیا اجرا می‌کند را فعال یا متوقف کنید.',
  'world.config.task.buildQueue': 'صف ساخت',
  'world.config.task.buildQueueDesc': 'ساختمان‌ها را بر اساس صف برنامه‌ریزی شده می‌سازد',
  'world.config.task.farmList':   'لیست مزارع',
  'world.config.task.farmListDesc': 'حملات برداشت را به صورت خودکار ارسال می‌کند',
  'world.config.task.troops':     'آموزش سربازان',
  'world.config.task.troopsDesc': 'صف آموزش را فعال نگه می‌دارد',
  'world.config.intervalsTitle':  'فواصل زمانی',
  'world.config.intervalsDesc':   'زمان بین بررسی‌های ربات. مقادیر بیشتر خطر شناسایی را کاهش می‌دهند.',
  'world.config.interval.check':  'بررسی دوره‌ای',
  'world.config.interval.farm':   'بین مزارع',
  'world.config.interval.jitter': 'تغییر تصادفی',
  'world.config.interval.min':    'دقیقه',
  'world.config.comingSoonTitle': 'به زودی در این فضا',
  'world.comingSoon.resourcesDesc':   'پایش لحظه‌ای چوب، گل، آهن و غله.',
  'world.comingSoon.troopsDesc':      'موجودی واحدها، آمار نبرد و صف آموزش.',
  'world.comingSoon.constructionDesc':'صف ساختمان‌ها برای هر دهکده، هزینه‌ها و زمان‌ها.',
  'world.comingSoon.villagesDesc':    'نقشه دهکده‌ها، مختصات، نام و نوع.',
  'world.stop.toast':             'ربات متوقف شد. بازگشت به جزئیات حساب…',

  // ── Sesión del mundo (§4b) ─────────────────────────────
  'world.session.start':    'راه‌اندازی',
  'world.session.stop':     'توقف',
  'world.session.retry':    'تلاش مجدد',
  'world.session.cancel':   'لغو',
  'world.session.enter':    'ورود',
  'world.session.idle':     'غیرفعال',
  'world.session.connecting': 'در حال اتصال…',
  'world.session.active':   'فعال',
  'world.session.error':    'خطای اتصال',
  'world.session.stopping': 'در حال توقف…',
  'world.session.start.aria': 'راه‌اندازی ربات در {world}',
  'world.session.stop.aria':  'توقف ربات در {world}',
  'world.session.retry.aria': 'تلاش مجدد اتصال در {world}',
  'world.session.enter.aria': 'ورود به فضای {world}',
  'world.session.disabled.delete':       'قبل از حذف این دنیا جلسه را متوقف کنید',
  'world.session.disabled.editMenu':     'امکان ویرایش دنیای دارای جلسه فعال وجود ندارد',
  'world.session.disabled.deleteAccount':'قبل از حذف این حساب همه جلسات فعال را متوقف کنید',
  'world.session.started.toast':  'ربات در {world} راه‌اندازی شد',
  'world.session.stopped.toast':  'ربات در {world} متوقف شد',
  'world.session.error.toast':    'اتصال در {world} ممکن نشد',

  // ── Tribus ──────────────────────────────────────────────
  'tribe.romans':    'Romans',
  'tribe.teutons':   'Teutons',
  'tribe.gauls':     'Gauls',
  'tribe.egyptians': 'Egyptians',
  'tribe.huns':      'Huns',
  'tribe.spartans':  'Spartans',
  'tribe.vikings':   'Vikings',

  // ── Errores globales ───────────────────────────────────
  'error.network':    'خطای اتصال. دوباره امتحان کنید.',
  'error.retry':      'تلاش مجدد',
  'error.loadFailed': 'بارگذاری داده‌ها ممکن نشد.',

  // ── Versión (sidebar footer) ───────────────────────────
  'app.version': 'v0.1.0',

  // ── Placeholders de ruta (etapa 1) ────────────────────
  'placeholder.accounts.list':   'لیست حساب‌ها — به زودی',
  'placeholder.account.detail':  'جزئیات حساب — به زودی',
  'placeholder.world.space':     'فضای دنیا — به زودی',
}

export default fa
