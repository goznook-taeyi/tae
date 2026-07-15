import { useEffect, useRef } from 'react'

// Desktop-only custom cursor. A fixed, pointer-events-none node positioned by
// direct DOM writes on mousemove (translate(-50%,-50%) to centre on the
// pointer) with mix-blend-mode: exclusion. Hidden below 1024px / on touch.
export default function Cursor() {
  const ref = useRef<HTMLDivElement>(null)

  useEffect(() => {
    const el = ref.current
    if (!el) return

    // Only engage on fine pointers wide enough to be a desktop.
    const fine = window.matchMedia('(pointer: fine)').matches
    const wide = window.matchMedia('(min-width: 1024px)').matches
    if (!fine || !wide) return

    document.documentElement.classList.add('has-custom-cursor')
    el.style.display = 'block'

    const onMove = (e: MouseEvent) => {
      el.style.left = `${e.clientX}px`
      el.style.top = `${e.clientY}px`
    }
    window.addEventListener('mousemove', onMove, { passive: true })

    return () => {
      window.removeEventListener('mousemove', onMove)
      document.documentElement.classList.remove('has-custom-cursor')
    }
  }, [])

  return (
    <div
      ref={ref}
      style={{
        position: 'fixed',
        left: -100,
        top: -100,
        display: 'none',
        pointerEvents: 'none',
        zIndex: 50,
        transform: 'translate(-50%, -50%)',
        mixBlendMode: 'exclusion',
        willChange: 'left, top',
      }}
    >
      <svg width="48" height="48" viewBox="0 0 48 48" fill="none" xmlns="http://www.w3.org/2000/svg">
        <circle cx="24" cy="24" r="22.75" stroke="#FFFFFF" strokeWidth="2.5" />
        {/* decorative glyph, filled white */}
        <path
          d="M18 16h12v2.4h-4.6v3h4v2.4h-4v6.2c0 1.1-.5 1.6-1.7 1.6-.7 0-1.6-.03-2.4-.1l-.4-2.5c.7.1 1.4.15 1.9.15.4 0 .5-.15.5-.5v-4.85h-4.4v-2.4h4.4v-3H18V16Z"
          fill="#FFFFFF"
        />
      </svg>
    </div>
  )
}
