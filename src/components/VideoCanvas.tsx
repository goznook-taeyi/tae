import { useEffect, useRef, useState } from 'react'
import { VIDEOS } from '../data/assets'

// #main-canvas — full-viewport video background living behind everything (z-0).
//
// Desktop (fine pointer, >=1024): the two clips are NOT autoplayed. They are
// scrubbed by cursor X with a central dead zone. Mobile / touch: the clips
// autoplay alternately (left, then right, then left...).
export default function VideoCanvas() {
  const containerRef = useRef<HTMLDivElement>(null)
  const leftRef = useRef<HTMLVideoElement>(null)
  const rightRef = useRef<HTMLVideoElement>(null)
  const [ready, setReady] = useState(false)

  // Reveal the canvas once both clips have enough data to render.
  useEffect(() => {
    const left = leftRef.current
    const right = rightRef.current
    if (!left || !right) return

    let loaded = 0
    const onLoad = () => {
      loaded += 1
      if (loaded >= 2) setReady(true)
    }
    // If a clip is already buffered (cache), count it immediately.
    for (const v of [left, right]) {
      if (v.readyState >= 2) onLoad()
      else v.addEventListener('loadeddata', onLoad, { once: true })
    }
    return () => {
      left.removeEventListener('loadeddata', onLoad)
      right.removeEventListener('loadeddata', onLoad)
    }
  }, [])

  // Interaction: desktop scrub vs. mobile autoplay.
  useEffect(() => {
    const container = containerRef.current
    const left = leftRef.current
    const right = rightRef.current
    if (!container || !left || !right) return

    const isDesktop =
      window.matchMedia('(pointer: fine)').matches && window.innerWidth >= 1024
    const reduceMotion = window.matchMedia('(prefers-reduced-motion: reduce)').matches

    // ---- Mobile / touch: alternate autoplay -------------------------------
    if (!isDesktop) {
      left.style.display = 'block'
      right.style.display = 'none'
      if (reduceMotion) return

      let current: HTMLVideoElement = left
      let other: HTMLVideoElement = right

      const swap = () => {
        const prev = current
        current = other
        other = prev
        other.style.display = 'none'
        other.pause()
        current.currentTime = 0
        current.style.display = 'block'
        current.play().catch(() => {})
      }
      left.addEventListener('ended', swap)
      right.addEventListener('ended', swap)
      left.play().catch(() => {})

      return () => {
        left.removeEventListener('ended', swap)
        right.removeEventListener('ended', swap)
      }
    }

    // ---- Desktop: cursor-driven scrub -------------------------------------
    // Left video starts hidden, right visible.
    left.style.display = 'none'
    right.style.display = 'block'

    let pointerX = window.innerWidth / 2
    // Which side was last "active" (drives which clip is shown). Only flips
    // when the cursor leaves the dead zone.
    let activeSide: 'left' | 'right' = 'right'

    const onMove = (e: MouseEvent) => {
      pointerX = e.clientX
    }
    window.addEventListener('mousemove', onMove, { passive: true })

    let raf = 0
    const tick = () => {
      raf = requestAnimationFrame(tick)

      const width = container.clientWidth
      const center = width / 2
      const dead = Math.max(30, width * 0.05)
      const dx = pointerX - center

      // Inside the dead zone: hold both clips at the very start, keep showing
      // whichever side was last active. No reset jitter near centre.
      if (Math.abs(dx) <= dead) {
        const shown = activeSide === 'right' ? right : left
        const hidden = activeSide === 'right' ? left : right
        shown.style.display = 'block'
        hidden.style.display = 'none'
        if (!shown.seeking && shown.currentTime > 0.001) shown.currentTime = 0
        return
      }

      if (dx < 0) {
        // Cursor left of the dead zone → show RIGHT clip, scrub toward edge.
        activeSide = 'right'
        right.style.display = 'block'
        left.style.display = 'none'
        const range = center - dead // px available from dead-zone edge to edge
        const progress = range > 0 ? Math.min(Math.max((-dx - dead) / range, 0), 1) : 0
        const dur = right.duration || 0
        if (dur && !right.seeking) right.currentTime = progress * dur
      } else {
        // Cursor right of the dead zone → show LEFT clip, scrub toward edge.
        activeSide = 'left'
        left.style.display = 'block'
        right.style.display = 'none'
        const range = center - dead
        const progress = range > 0 ? Math.min(Math.max((dx - dead) / range, 0), 1) : 0
        const dur = left.duration || 0
        if (dur && !left.seeking) left.currentTime = progress * dur
      }
    }
    raf = requestAnimationFrame(tick)

    return () => {
      window.removeEventListener('mousemove', onMove)
      cancelAnimationFrame(raf)
    }
  }, [])

  const videoStyle: React.CSSProperties = {
    position: 'absolute',
    inset: 0,
    width: '100%',
    height: '100%',
    objectFit: 'cover',
  }

  return (
    <div
      ref={containerRef}
      id="main-canvas"
      className="fixed left-0 top-[220px] z-0 h-[calc(100vh-220px)] w-screen overflow-hidden lg:inset-0 lg:top-0 lg:h-full lg:w-full"
      style={{
        pointerEvents: 'none',
        opacity: ready ? 1 : 0,
        transition: 'opacity 0.3s ease',
      }}
    >
      <video
        ref={leftRef}
        style={{ ...videoStyle, display: 'none' }}
        src={VIDEOS.left}
        muted
        playsInline
        preload="auto"
      />
      <video
        ref={rightRef}
        style={{ ...videoStyle, display: 'block' }}
        src={VIDEOS.right}
        muted
        playsInline
        preload="auto"
      />
    </div>
  )
}
