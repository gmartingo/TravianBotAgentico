/**
 * NatureIcon — Icono de animal nature de Travian.
 *
 * Sirve `/api/static/icons/nature_{ordinal}.png` desde los assets del juego.
 * Si la imagen no carga (onerror), muestra el nombre del animal como texto fallback.
 *
 * Análogo a ResIcon (src/components/combat/TravianReport.jsx) pero para animales.
 * ResIcon está especializado para recursos (wood/clay/iron/crop) con rutas stat_*.png.
 * NatureIcon usa el índice numérico ordinal (1–10) de los animales de naturaleza.
 *
 * Props:
 *   ordinal  — number  (1–10, ordinal del animal en Travian)
 *   name     — string  (nombre del animal — alt text y fallback de texto)
 *   size     — number  (px, default 16)
 */
import { useState } from 'react'

export function NatureIcon({ ordinal, name, size = 16 }) {
  const [imgError, setImgError] = useState(false)

  if (imgError || ordinal == null) {
    // Fallback: texto con el primer carácter del nombre en un badge cuadrado
    return (
      <span
        aria-label={name}
        title={name}
        style={{
          display: 'inline-flex',
          alignItems: 'center',
          justifyContent: 'center',
          width: `${size}px`,
          height: `${size}px`,
          borderRadius: '3px',
          background: 'var(--surface-2)',
          border: '1px solid var(--border)',
          fontSize: `${Math.max(size - 5, 8)}px`,
          color: 'var(--text-secondary)',
          fontFamily: 'var(--font-sans)',
          flexShrink: 0,
          lineHeight: 1,
        }}
      >
        {name ? name.charAt(0) : '?'}
      </span>
    )
  }

  return (
    <img
      src={`/api/static/icons/nature_${ordinal}.png`}
      alt={name ?? `nature_${ordinal}`}
      title={name ?? `nature_${ordinal}`}
      onError={() => setImgError(true)}
      style={{
        width: `${size}px`,
        height: `${size}px`,
        objectFit: 'contain',
        imageRendering: 'pixelated',
        display: 'inline-block',
        verticalAlign: 'middle',
        flexShrink: 0,
        borderRadius: '3px',
      }}
    />
  )
}
