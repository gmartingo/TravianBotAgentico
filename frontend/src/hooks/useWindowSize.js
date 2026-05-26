/**
 * useWindowSize — devuelve { width, height } del viewport.
 * Se actualiza en cada resize con debounce implícito (requestAnimationFrame).
 */
import { useState, useEffect } from 'react'

export function useWindowSize() {
  const [size, setSize] = useState({
    width:  window.innerWidth,
    height: window.innerHeight,
  })

  useEffect(() => {
    let raf
    function handleResize() {
      cancelAnimationFrame(raf)
      raf = requestAnimationFrame(() => {
        setSize({ width: window.innerWidth, height: window.innerHeight })
      })
    }
    window.addEventListener('resize', handleResize)
    return () => {
      window.removeEventListener('resize', handleResize)
      cancelAnimationFrame(raf)
    }
  }, [])

  return size
}
