/**
 * WizardModal — S3 Wizard de alta de cuenta (2 pasos).
 *
 * Fiel al mockup aprobado: frontend/mockups/wizard.playground.html
 * Spec de diseño: docs/design/gestion-cuentas-mundos.md §5, §6 S3, §7 S3, §9 S3
 *
 * Paso 1: email + username + password (con toggle de visibilidad).
 *         Al pulsar "Siguiente": valida + llama POST /accounts → 201.
 *         Error 409 email → error inline en el campo email (permanece en paso 1).
 *         Error 422 → error genérico de validación.
 *
 * Paso 2: URL del servidor + tribu (select).
 *         Vista previa parseada ("ts1 · x1 · international") en tiempo real.
 *         Al pulsar "Crear cuenta": llama POST /accounts/:id/worlds → 201.
 *         Error 409 server duplicado → error inline URL.
 *         Error 422 URL inválida → error inline URL.
 *
 * Al terminar con éxito → navega a /cuentas/:id (detalle de la cuenta nueva).
 * Cancelar / ESC / click fuera → navega a /cuentas.
 *
 * Accesibilidad (§10):
 *   - role="dialog" + aria-modal + aria-labelledby
 *   - Focus trap dentro del modal
 *   - Al abrir: foco al primer campo
 *   - Al cerrar: foco devuelto al trigger (vía onClose)
 *   - ESC cierra (si no hay operación en curso)
 *   - role="alert" en errores dinámicos
 *   - aria-current="step" en paso activo del stepper
 *   - aria-live="polite" en la vista previa del servidor
 *
 * Responsive (§11):
 *   - En móvil (< md): modal = bottom sheet (ancho 100vw, radius-bottom: 0)
 *   - Botones del footer se apilan en < md
 *   - Input font-size ≥ 16px en móvil (evita zoom iOS)
 */
import { useState, useEffect, useRef, useCallback, useMemo } from 'react'
import { useNavigate } from 'react-router-dom'
import { useI18n } from '../../i18n/index.jsx'
import { api, ApiError } from '../../api/client.js'

// ─── Icono: ojo (mostrar contraseña) ────────────────────────────────────────

function IconEye({ size = 16 }) {
  return (
    <svg width={size} height={size} viewBox="0 0 24 24"
      fill="none" stroke="currentColor" strokeWidth="2"
      strokeLinecap="round" strokeLinejoin="round" aria-hidden="true">
      <path d="M1 12s4-8 11-8 11 8 11 8-4 8-11 8-11-8-11-8z" />
      <circle cx="12" cy="12" r="3" />
    </svg>
  )
}

function IconEyeOff({ size = 16 }) {
  return (
    <svg width={size} height={size} viewBox="0 0 24 24"
      fill="none" stroke="currentColor" strokeWidth="2"
      strokeLinecap="round" strokeLinejoin="round" aria-hidden="true">
      <path d="M17.94 17.94A10.07 10.07 0 0 1 12 20c-7 0-11-8-11-8a18.45 18.45 0 0 1 5.06-5.94M9.9 4.24A9.12 9.12 0 0 1 12 4c7 0 11 8 11 8a18.5 18.5 0 0 1-2.16 3.19m-6.72-1.07a3 3 0 1 1-4.24-4.24" />
      <line x1="1" y1="1" x2="23" y2="23" />
    </svg>
  )
}

// ─── Icono: spinner inline ───────────────────────────────────────────────────

function Spinner({ size = 14 }) {
  return (
    <svg
      width={size} height={size}
      viewBox="0 0 24 24"
      fill="none" stroke="currentColor" strokeWidth="2.5"
      strokeLinecap="round" aria-hidden="true"
      className="animate-spin"
      style={{ animation: 'wizard-spin 0.6s linear infinite', flexShrink: 0 }}
    >
      <path d="M12 2a10 10 0 0 1 10 10" />
    </svg>
  )
}

// ─── Utilidad: parsear URL de servidor Travian ───────────────────────────────
//
// https://ts1.x1.international.travian.com/
//          ↓
// server = "ts1"  speed = "x1"  region = "international"
// Formato: "ts1 · x1 · international"
// Si no parseable: null (la UI muestra "—" en --text-tertiary)

function parseServerUrl(raw) {
  if (!raw || typeof raw !== 'string') return null
  let hostname
  try {
    // Añadir protocolo si falta para que URL() lo acepte
    const normalised = raw.match(/^https?:\/\//) ? raw : `https://${raw}`
    hostname = new URL(normalised).hostname
  } catch {
    return null
  }
  // hostname: ts1.x1.international.travian.com
  const parts = hostname.split('.')
  if (parts.length < 3) return null
  const server = parts[0]                                    // "ts1"
  const speed  = parts.find(p => /^x\d+$/i.test(p)) ?? null // "x1"
  // La región es el segmento entre speed y "travian"
  // Para "ts1.x1.international.travian.com" → partes[2] = "international"
  const travianIdx = parts.findIndex(p => p.toLowerCase() === 'travian')
  // Cualquier segmento entre el primero y "travian" que no sea el server ni el speed
  const region = parts
    .slice(1, travianIdx < 0 ? parts.length - 1 : travianIdx)
    .find(p => !/^x\d+$/i.test(p) && p !== server) ?? null

  if (!server) return null
  const chunks = [server, speed, region].filter(Boolean)
  return chunks.join(' · ')
}

// ─── Función de validación de URL ────────────────────────────────────────────

function isValidServerUrl(raw) {
  if (!raw) return false
  try {
    const normalised = raw.match(/^https?:\/\//) ? raw : null
    if (!normalised) return false
    new URL(normalised)
    return true
  } catch {
    return false
  }
}

// ─── Focus trap ──────────────────────────────────────────────────────────────

const FOCUSABLE = [
  'a[href]',
  'button:not([disabled])',
  'input:not([disabled]):not([readonly])',
  'select:not([disabled])',
  'textarea:not([disabled])',
  '[tabindex]:not([tabindex="-1"])',
].join(', ')

function useFocusTrap(ref, active) {
  useEffect(() => {
    if (!active || !ref.current) return
    const el = ref.current
    const focusable = () => Array.from(el.querySelectorAll(FOCUSABLE))

    function handler(e) {
      if (e.key !== 'Tab') return
      const nodes = focusable()
      if (!nodes.length) return
      const first = nodes[0]
      const last  = nodes[nodes.length - 1]
      if (e.shiftKey) {
        if (document.activeElement === first) { e.preventDefault(); last.focus() }
      } else {
        if (document.activeElement === last) { e.preventDefault(); first.focus() }
      }
    }
    document.addEventListener('keydown', handler)
    return () => document.removeEventListener('keydown', handler)
  }, [ref, active])
}

// ─── Componente Campo de formulario ─────────────────────────────────────────

function FormField({ label, required, error, children }) {
  return (
    <div className="flex flex-col gap-[5px] mb-4 last:mb-0">
      <label className="text-[12px] font-medium text-[var(--text-secondary)]">
        {label}
        {required && (
          <span className="text-[var(--danger)] ms-[2px]" aria-hidden="true">*</span>
        )}
      </label>
      {children}
      {error && (
        <span
          role="alert"
          className="text-[12px] text-[var(--danger)]"
        >
          {error}
        </span>
      )}
    </div>
  )
}

// ─── Input estilado ──────────────────────────────────────────────────────────

const inputBase = [
  'w-full h-9 border border-[var(--border-strong)] bg-[var(--surface)]',
  'text-[var(--text)] rounded-[var(--radius-sm)] px-[10px]',
  'font-[inherit] text-[16px] md:text-[14px]',   // 16px en móvil evita el auto-zoom de iOS; 14px en escritorio
  'outline-none transition-[border-color] duration-[var(--dur-fast)]',
  'focus:border-[var(--accent)] focus:outline-[2px] focus:outline-[var(--accent)] focus:outline-offset-[1px]',
  'disabled:opacity-65 disabled:cursor-not-allowed read-only:opacity-65 read-only:bg-[var(--surface-2)]',
  'placeholder:text-[var(--text-tertiary)]',
].join(' ')

const inputError = 'border-[var(--danger)] focus:outline-[var(--danger)]'

// ─── WizardModal ─────────────────────────────────────────────────────────────

export function WizardModal({ triggerRef }) {
  const { t } = useI18n()
  const navigate = useNavigate()
  const modalRef = useRef(null)

  // Estado del wizard
  const [step, setStep]       = useState(1)       // 1 | 2
  const [sending, setSending] = useState(false)   // true durante la llamada a la API
  const [createdId, setCreatedId] = useState(null) // id de la cuenta recién creada (tras paso 1 OK)

  // Campos paso 1
  const [email,    setEmail]    = useState('')
  const [username, setUsername] = useState('')
  const [password, setPassword] = useState('')
  const [showPw,   setShowPw]   = useState(false)

  // Errores inline paso 1
  const [emailErr,    setEmailErr]    = useState('')
  const [usernameErr, setUsernameErr] = useState('')
  const [passwordErr, setPasswordErr] = useState('')

  // Campos paso 2
  const [serverUrl, setServerUrl] = useState('')
  const [tribe,     setTribe]     = useState('')

  // Errores inline paso 2
  const [serverErr, setServerErr] = useState('')
  const [tribeErr,  setTribeErr]  = useState('')

  // refs para devolver foco al trigger al cerrar
  const firstFieldRef = useRef(null)

  // Focus trap
  useFocusTrap(modalRef, true)

  // Foco al primer campo al montar / cambiar de paso
  useEffect(() => {
    const timer = setTimeout(() => {
      firstFieldRef.current?.focus()
    }, 50)
    return () => clearTimeout(timer)
  }, [step])

  // ESC cierra (solo si no está enviando)
  useEffect(() => {
    function handler(e) {
      if (e.key === 'Escape' && !sending) handleClose()
    }
    document.addEventListener('keydown', handler)
    return () => document.removeEventListener('keydown', handler)
  }, [sending]) // eslint-disable-line react-hooks/exhaustive-deps

  function handleClose() {
    navigate('/cuentas')
    triggerRef?.current?.focus()
  }

  function handleBackdropClick(e) {
    if (!sending && e.target === e.currentTarget) handleClose()
  }

  // ── Validaciones ──────────────────────────────────────────────────────────

  function validateEmail(val) {
    if (!val.trim()) return t('wizard.error.required')
    if (!/^[^\s@]+@[^\s@]+\.[^\s@]+$/.test(val.trim())) return t('wizard.error.email.invalid')
    return ''
  }

  function validateUsername(val) {
    if (!val.trim()) return t('wizard.error.required')
    return ''
  }

  function validatePassword(val) {
    if (!val) return t('wizard.error.required')
    return ''
  }

  function validateServerUrl(val) {
    if (!val.trim()) return t('wizard.error.required')
    if (!isValidServerUrl(val.trim())) return t('wizard.error.server.invalid')
    return ''
  }

  function validateTribe(val) {
    if (!val) return t('wizard.error.tribe.required')
    return ''
  }

  // ── Habilitación de botones ───────────────────────────────────────────────

  const step1Valid = useMemo(() => {
    return (
      !validateEmail(email) &&
      !validateUsername(username) &&
      !validatePassword(password)
    )
  }, [email, username, password]) // eslint-disable-line react-hooks/exhaustive-deps

  const step2Valid = useMemo(() => {
    return !validateServerUrl(serverUrl) && !validateTribe(tribe)
  }, [serverUrl, tribe]) // eslint-disable-line react-hooks/exhaustive-deps

  // ── Handlers blur ────────────────────────────────────────────────────────

  function onEmailBlur()    { setEmailErr(validateEmail(email)) }
  function onUsernameBlur() { setUsernameErr(validateUsername(username)) }
  function onPasswordBlur() { setPasswordErr(validatePassword(password)) }
  function onServerBlur()   { setServerErr(validateServerUrl(serverUrl)) }
  function onTribeBlur()    { setTribeErr(validateTribe(tribe)) }

  // ── Avanzar al paso 2: crear cuenta ─────────────────────────────────────

  async function handleNext() {
    // Validar todos los campos del paso 1 antes de enviar
    const eErr = validateEmail(email)
    const uErr = validateUsername(username)
    const pErr = validatePassword(password)
    setEmailErr(eErr)
    setUsernameErr(uErr)
    setPasswordErr(pErr)
    if (eErr || uErr || pErr) return

    setSending(true)
    try {
      const account = await api.createAccount({
        email:    email.trim(),
        username: username.trim(),
        password,
      })
      setCreatedId(account.id)
      setStep(2)
    } catch (err) {
      if (err instanceof ApiError && err.status === 409) {
        setEmailErr(t('wizard.error.email.taken'))
      } else if (err instanceof ApiError && err.status === 422) {
        setEmailErr(t('wizard.error.email.invalid'))
      } else {
        // Error de red u otros — mostramos en email como campo más visible
        setEmailErr(err.message === 'error.network' ? t('error.network') : (err.message || t('error.network')))
      }
    } finally {
      setSending(false)
    }
  }

  // ── Volver al paso 1 ─────────────────────────────────────────────────────

  function handleBack() {
    setStep(1)
    setServerErr('')
    setTribeErr('')
  }

  // ── Crear mundo (paso 2) ─────────────────────────────────────────────────

  async function handleCreate() {
    // Validar campos del paso 2 antes de enviar
    const sErr = validateServerUrl(serverUrl)
    const trErr = validateTribe(tribe)
    setServerErr(sErr)
    setTribeErr(trErr)
    if (sErr || trErr) return

    setSending(true)
    try {
      await api.createWorld(createdId, {
        server: serverUrl.trim(),
        tribe,
      })
      // Éxito: navegar al detalle de la cuenta nueva
      navigate(`/cuentas/${createdId}`)
    } catch (err) {
      if (err instanceof ApiError && err.status === 409) {
        setServerErr(t('wizard.error.server.taken'))
      } else if (err instanceof ApiError && err.status === 422) {
        setServerErr(t('wizard.error.server.invalid'))
      } else {
        setServerErr(err.message === 'error.network' ? t('error.network') : (err.message || t('error.network')))
      }
    } finally {
      setSending(false)
    }
  }

  // ── Vista previa del servidor ────────────────────────────────────────────

  const serverPreview = useMemo(() => parseServerUrl(serverUrl), [serverUrl])

  // ── Tribus ───────────────────────────────────────────────────────────────

  const TRIBES = [
    { value: 'romans',    key: 'tribe.romans' },
    { value: 'teutons',   key: 'tribe.teutons' },
    { value: 'gauls',     key: 'tribe.gauls' },
    { value: 'egyptians', key: 'tribe.egyptians' },
    { value: 'huns',      key: 'tribe.huns' },
    { value: 'spartans',  key: 'tribe.spartans' },
    { value: 'vikings',   key: 'tribe.vikings' },
  ]

  // ─────────────────────────────────────────────────────────────────────────
  // RENDER
  // ─────────────────────────────────────────────────────────────────────────

  return (
    <>
      {/* Keyframe del spinner inline — solo en este componente */}
      <style>{`
        @keyframes wizard-spin { to { transform: rotate(360deg); } }
      `}</style>

      {/* Backdrop -------------------------------------------------------- */}
      <div
        className="fixed inset-0 z-[400] flex items-center justify-center
                   bg-black/40 backdrop-blur-[2px]
                   md:items-center items-end
                   transition-opacity duration-[var(--dur-slow)]"
        onClick={handleBackdropClick}
        aria-hidden="false"
      >
        {/* Modal panel -------------------------------------------------- */}
        <div
          ref={modalRef}
          role="dialog"
          aria-modal="true"
          aria-labelledby="wizard-title"
          className="relative bg-[var(--surface)] flex flex-col
                     w-full max-w-[480px] max-h-[90vh]
                     rounded-[var(--radius-lg)]
                     md:rounded-[var(--radius-lg)]
                     rounded-b-none
                     shadow-[var(--shadow-lg)]
                     transition-transform duration-[var(--dur-slow)]"
          onClick={e => e.stopPropagation()}
        >

          {/* Header ------------------------------------------------------ */}
          <div className="flex items-center justify-between gap-3
                          px-5 pt-[18px] pb-[14px]
                          border-b border-[var(--border)] flex-shrink-0">
            <span
              id="wizard-title"
              className="text-[17px] font-semibold tracking-[-0.01em] text-[var(--text)]"
            >
              {t('wizard.title')}
            </span>
            <button
              type="button"
              onClick={handleClose}
              disabled={sending}
              aria-label={t('modal.deleteAccount.cancel')}
              className="w-7 h-7 rounded-[var(--radius-sm)] grid place-items-center
                         text-[var(--text-secondary)] text-[18px] leading-none
                         bg-transparent border-none cursor-pointer
                         hover:bg-[var(--surface-2)] hover:text-[var(--text)]
                         disabled:opacity-40 disabled:cursor-not-allowed
                         transition-colors duration-[var(--dur-fast)]"
            >
              ×
            </button>
          </div>

          {/* Body -------------------------------------------------------- */}
          <div className="px-5 py-5 overflow-y-auto flex-1">

            {/* Stepper -------------------------------------------------- */}
            <div
              className="flex items-center mb-[6px]"
              aria-label={t('wizard.step', { current: step, total: 2 })}
            >
              {/* Paso 1 */}
              <div
                className={[
                  'w-6 h-6 rounded-full border-2 grid place-items-center',
                  'text-[12px] font-semibold flex-shrink-0',
                  'transition-colors duration-[var(--dur-base)]',
                  step === 1
                    ? 'bg-[var(--accent)] border-[var(--accent)] text-[var(--surface)]'
                    : 'bg-[var(--accent-subtle)] border-[var(--accent)] text-[var(--accent-text)]',
                ].join(' ')}
                aria-current={step === 1 ? 'step' : undefined}
                role="listitem"
              >
                1
              </div>
              {/* Línea */}
              <div
                className={[
                  'flex-1 h-[2px] mx-[6px] transition-colors duration-[var(--dur-base)]',
                  step === 2 ? 'bg-[var(--accent)]' : 'bg-[var(--border)]',
                ].join(' ')}
              />
              {/* Paso 2 */}
              <div
                className={[
                  'w-6 h-6 rounded-full border-2 grid place-items-center',
                  'text-[12px] font-semibold flex-shrink-0',
                  'transition-colors duration-[var(--dur-base)]',
                  step === 2
                    ? 'bg-[var(--accent)] border-[var(--accent)] text-[var(--surface)]'
                    : 'border-[var(--border-strong)] text-[var(--text-secondary)]',
                ].join(' ')}
                aria-current={step === 2 ? 'step' : undefined}
                role="listitem"
              >
                2
              </div>
            </div>

            {/* Label del paso */}
            <p className="text-[12px] text-[var(--text-secondary)] mb-4">
              {t('wizard.step', { current: step, total: 2 })}
            </p>

            {/* ── PASO 1: Datos de la cuenta ──────────────────────────── */}
            {step === 1 && (
              <div>
                <p className="text-[17px] font-semibold tracking-[-0.01em] text-[var(--text)] mb-4">
                  {t('wizard.section.account')}
                </p>

                {/* Email */}
                <FormField
                  label={t('wizard.field.email')}
                  required
                  error={emailErr}
                >
                  <input
                    ref={firstFieldRef}
                    type="email"
                    id="w-email"
                    autoComplete="username"
                    value={email}
                    onChange={e => { setEmail(e.target.value); if (emailErr) setEmailErr('') }}
                    onBlur={onEmailBlur}
                    placeholder={t('wizard.field.email.ph')}
                    readOnly={sending}
                    aria-invalid={!!emailErr}
                    aria-describedby={emailErr ? 'w-email-err' : undefined}
                    className={[inputBase, emailErr ? inputError : ''].join(' ')}
                    style={{ fontSize: undefined }} // se gestiona por Tailwind + media query abajo
                  />
                </FormField>

                {/* Username */}
                <FormField
                  label={t('wizard.field.username')}
                  required
                  error={usernameErr}
                >
                  <input
                    type="text"
                    id="w-username"
                    autoComplete="off"
                    value={username}
                    onChange={e => { setUsername(e.target.value); if (usernameErr) setUsernameErr('') }}
                    onBlur={onUsernameBlur}
                    placeholder={t('wizard.field.username.ph')}
                    readOnly={sending}
                    aria-invalid={!!usernameErr}
                    className={[inputBase, usernameErr ? inputError : ''].join(' ')}
                  />
                </FormField>

                {/* Password con toggle */}
                <FormField
                  label={t('wizard.field.password')}
                  required
                  error={passwordErr}
                >
                  <div className="relative flex items-center">
                    <input
                      type={showPw ? 'text' : 'password'}
                      id="w-password"
                      autoComplete="new-password"
                      value={password}
                      onChange={e => { setPassword(e.target.value); if (passwordErr) setPasswordErr('') }}
                      onBlur={onPasswordBlur}
                      placeholder={t('wizard.field.password.ph')}
                      readOnly={sending}
                      aria-invalid={!!passwordErr}
                      className={[inputBase, 'pe-[38px]', passwordErr ? inputError : ''].join(' ')}
                    />
                    <button
                      type="button"
                      tabIndex={0}
                      onClick={() => setShowPw(v => !v)}
                      aria-label={showPw ? t('wizard.btn.hidePassword') : t('wizard.btn.showPassword')}
                      className="absolute end-[8px] top-1/2 -translate-y-1/2
                                 w-6 h-6 grid place-items-center rounded
                                 bg-transparent border-none cursor-pointer
                                 text-[var(--text-secondary)]
                                 hover:text-[var(--text)]"
                    >
                      {showPw ? <IconEyeOff /> : <IconEye />}
                    </button>
                  </div>
                </FormField>
              </div>
            )}

            {/* ── PASO 2: Primer mundo ────────────────────────────────── */}
            {step === 2 && (
              <div>
                <p className="text-[17px] font-semibold tracking-[-0.01em] text-[var(--text)] mb-4">
                  {t('wizard.section.world')}
                </p>

                {/* URL del servidor */}
                <FormField
                  label={t('wizard.field.server')}
                  required
                  error={serverErr}
                >
                  <input
                    ref={firstFieldRef}
                    type="url"
                    id="w-server"
                    autoComplete="off"
                    value={serverUrl}
                    onChange={e => { setServerUrl(e.target.value); if (serverErr) setServerErr('') }}
                    onBlur={onServerBlur}
                    placeholder={t('wizard.field.server.ph')}
                    readOnly={sending}
                    aria-invalid={!!serverErr}
                    className={[inputBase, serverErr ? inputError : ''].join(' ')}
                  />
                  {/* Vista previa parseada en tiempo real */}
                  <p
                    aria-live="polite"
                    className={[
                      'text-[12px] font-mono -mt-[10px]',
                      serverPreview
                        ? 'text-[var(--accent-text)]'
                        : 'text-[var(--text-tertiary)]',
                    ].join(' ')}
                    style={{ minHeight: '16px' }}
                  >
                    {serverPreview ?? '—'}
                  </p>
                </FormField>

                {/* Tribu */}
                <FormField
                  label={t('wizard.field.tribe')}
                  required
                  error={tribeErr}
                >
                  <select
                    id="w-tribe"
                    value={tribe}
                    onChange={e => { setTribe(e.target.value); if (tribeErr) setTribeErr('') }}
                    onBlur={onTribeBlur}
                    disabled={sending}
                    aria-invalid={!!tribeErr}
                    className={[
                      'w-full h-9 border border-[var(--border-strong)] bg-[var(--surface)]',
                      'text-[var(--text)] rounded-[var(--radius-sm)] px-[10px]',
                      'font-[inherit] text-[14px] outline-none cursor-pointer',
                      'transition-[border-color] duration-[var(--dur-fast)]',
                      'focus:border-[var(--accent)] focus:outline-[2px] focus:outline-[var(--accent)] focus:outline-offset-[1px]',
                      'disabled:opacity-65 disabled:cursor-not-allowed',
                      tribeErr ? inputError : '',
                    ].join(' ')}
                  >
                    <option value="">{t('wizard.field.tribe.ph')}</option>
                    {TRIBES.map(({ value, key }) => (
                      <option key={value} value={value}>{t(key)}</option>
                    ))}
                  </select>
                </FormField>
              </div>
            )}
          </div>{/* /body */}

          {/* Footer paso 1 ----------------------------------------------- */}
          {step === 1 && (
            <div className="flex items-center justify-end gap-2
                            px-5 py-[14px] border-t border-[var(--border)] flex-shrink-0
                            md:flex-row flex-col-reverse md:items-center items-stretch">
              <button
                type="button"
                onClick={handleClose}
                disabled={sending}
                className="h-8 px-[14px] rounded-[var(--radius-sm)]
                           bg-[var(--surface)] border border-[var(--border-strong)]
                           text-[var(--text)] text-[13px] font-medium cursor-pointer
                           hover:bg-[var(--surface-2)]
                           disabled:opacity-50 disabled:cursor-not-allowed
                           transition-colors duration-[var(--dur-fast)]
                           md:w-auto w-full md:justify-start justify-center flex items-center"
              >
                {t('wizard.btn.cancel')}
              </button>
              <button
                type="button"
                onClick={handleNext}
                disabled={!step1Valid || sending}
                className="h-8 px-[14px] rounded-[var(--radius-sm)]
                           bg-[var(--btn-primary-bg)] text-[var(--btn-primary-text)]
                           text-[13px] font-medium border-none cursor-pointer
                           hover:bg-[var(--btn-primary-hover)]
                           disabled:opacity-50 disabled:cursor-not-allowed
                           transition-colors duration-[var(--dur-fast)]
                           md:w-auto w-full flex items-center justify-center gap-[6px]"
              >
                {sending && <Spinner />}
                {sending ? t('wizard.btn.creating') : t('wizard.btn.next')}
              </button>
            </div>
          )}

          {/* Footer paso 2 ----------------------------------------------- */}
          {step === 2 && (
            <div className="flex items-center justify-between gap-2
                            px-5 py-[14px] border-t border-[var(--border)] flex-shrink-0
                            md:flex-row flex-row">
              {/* Atrás (ghost) */}
              <button
                type="button"
                onClick={handleBack}
                disabled={sending}
                className="h-8 px-[10px] rounded-[var(--radius-sm)]
                           bg-transparent border-none
                           text-[var(--accent-text)] text-[13px] cursor-pointer
                           hover:text-[var(--accent-hover)]
                           disabled:opacity-50 disabled:cursor-not-allowed
                           transition-colors duration-[var(--dur-fast)]
                           flex items-center gap-[6px]"
              >
                {t('wizard.btn.back')}
              </button>

              {/* Cancelar + Crear cuenta */}
              <div className="flex items-center gap-2">
                <button
                  type="button"
                  onClick={handleClose}
                  disabled={sending}
                  className="h-8 px-[14px] rounded-[var(--radius-sm)]
                             bg-[var(--surface)] border border-[var(--border-strong)]
                             text-[var(--text)] text-[13px] font-medium cursor-pointer
                             hover:bg-[var(--surface-2)]
                             disabled:opacity-50 disabled:cursor-not-allowed
                             transition-colors duration-[var(--dur-fast)]
                             flex items-center"
                >
                  {t('wizard.btn.cancel')}
                </button>
                <button
                  type="button"
                  onClick={handleCreate}
                  disabled={!step2Valid || sending}
                  className="h-8 px-[14px] rounded-[var(--radius-sm)]
                             bg-[var(--btn-primary-bg)] text-[var(--btn-primary-text)]
                             text-[13px] font-medium border-none cursor-pointer
                             hover:bg-[var(--btn-primary-hover)]
                             disabled:opacity-50 disabled:cursor-not-allowed
                             transition-colors duration-[var(--dur-fast)]
                             flex items-center gap-[6px]"
                >
                  {sending && <Spinner />}
                  {sending ? t('wizard.btn.creating') : t('wizard.btn.create')}
                </button>
              </div>
            </div>
          )}

        </div>{/* /modal panel */}
      </div>{/* /backdrop */}
    </>
  )
}
