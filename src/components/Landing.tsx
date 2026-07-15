import { useRef } from 'react'
import { motion } from 'motion/react'
import gsap from 'gsap'
import { ScrollTrigger } from 'gsap/ScrollTrigger'
import { useGSAP } from '@gsap/react'
import Logo from './Logo'
import Cursor from './Cursor'
import VideoCanvas from './VideoCanvas'
import { CIRCLE_SYMBOLS, GALLERY_IMAGES } from '../data/assets'

gsap.registerPlugin(ScrollTrigger, useGSAP)

const EASE = [0.25, 0.1, 0.25, 1] as const

// Scattered gallery layout. `top` is in vh (grid-local), `left` a % of grid
// width, `w` the image box width in vw. The grid is 3x viewport tall.
const GALLERY_LAYOUT = [
  { left: '5%', top: 12, w: 30 },
  { left: '60%', top: 6, w: 34 },
  { left: '33%', top: 44, w: 30 },
  { left: '3%', top: 78, w: 27 },
  { left: '66%', top: 82, w: 29 },
  { left: '28%', top: 112, w: 40 },
  { left: '70%', top: 146, w: 26 },
  { left: '6%', top: 156, w: 31 },
  { left: '42%', top: 190, w: 34 },
  { left: '10%', top: 220, w: 42 },
]

const clamp = (v: number, min: number, max: number) => Math.min(Math.max(v, min), max)

export default function Landing() {
  const spacerRef = useRef<HTMLDivElement>(null)
  const panelRef = useRef<HTMLDivElement>(null)
  const gridRef = useRef<HTMLDivElement>(null)
  const overlayRef = useRef<HTMLDivElement>(null)
  const buyRef = useRef<HTMLDivElement>(null)
  const infoRef = useRef<HTMLDivElement>(null)
  const symbolRef = useRef<HTMLSpanElement>(null)
  const imgRefs = useRef<(HTMLDivElement | null)[]>([])

  useGSAP(
    () => {
      const spacer = spacerRef.current
      const panel = panelRef.current
      const grid = gridRef.current
      if (!spacer || !panel || !grid) return

      const setSpacerHeight = () => {
        // Height = vh (hero) + maxScroll (gallery = 2vh) + 2vh (outro) = 5vh.
        spacer.style.height = `${window.innerHeight * 5}px`
      }
      setSpacerHeight()
      ScrollTrigger.addEventListener('refreshInit', setSpacerHeight)

      const setPanelY = gsap.quickSetter(panel, 'y', 'px')
      const setGridY = gsap.quickSetter(grid, 'y', 'px')

      const outroOffset = () => (window.innerWidth >= 1024 ? 166 : 132)

      let lastSymbol = 0

      const render = (p: number) => {
        const vh = window.innerHeight
        const vw = window.innerWidth
        const maxScroll = vh * 2

        // Phase progress: A = panel rise [0,.25], B = gallery [.25,.75],
        // C = outro [.75,1].
        const pa = clamp(p / 0.25, 0, 1)
        const pb = clamp((p - 0.25) / 0.5, 0, 1)
        const pc = clamp((p - 0.75) / 0.25, 0, 1)

        // Black panel slides up from below the fold to cover the video.
        setPanelY((1 - pa) * vh)

        // Gallery content scrolls within the pinned panel.
        const gridY = -pb * maxScroll
        setGridY(gridY)

        // Per-image scale/opacity based on distance from the viewport centre.
        for (let i = 0; i < GALLERY_LAYOUT.length; i++) {
          const el = imgRefs.current[i]
          if (!el) continue
          const item = GALLERY_LAYOUT[i]
          const boxW = (item.w / 100) * vw
          const boxH = boxW * (4 / 3) // portrait product crop
          const boxTop = (item.top / 100) * vh
          const centerY = boxTop + boxH / 2 + gridY
          const dist = Math.abs(centerY - vh / 2)
          const norm = dist / (vh * 0.68)
          const scale = clamp(1 - norm * 0.55, 0.42, 1)
          const opacity = clamp(1 - norm * 0.7, 0.12, 1)
          el.style.transform = `scale(${scale})`
          el.style.opacity = `${opacity}`
        }

        // Outro: white overlay fades in, view button scales in, info shifts up.
        if (overlayRef.current) overlayRef.current.style.opacity = `${pc}`
        if (buyRef.current) buyRef.current.style.transform = `scale(${pc})`
        if (infoRef.current)
          infoRef.current.style.transform = `translateY(${-outroOffset() * pc}px)`

        // Circle glyph flickers through symbols while scrolling (throttled).
        const now = p * 100000
        if (symbolRef.current && now - lastSymbol > 8) {
          lastSymbol = now
          const idx = Math.floor(clamp(pb + pa, 0, 1.999) * 991) % CIRCLE_SYMBOLS.length
          symbolRef.current.textContent = CIRCLE_SYMBOLS[idx]
        }
      }

      const st = ScrollTrigger.create({
        trigger: spacer,
        start: 'top top',
        end: 'bottom bottom',
        scrub: true,
        onUpdate: (self) => render(self.progress),
      })

      render(0)

      return () => {
        ScrollTrigger.removeEventListener('refreshInit', setSpacerHeight)
        st.kill()
      }
    },
    { scope: spacerRef },
  )

  return (
    <div
      ref={spacerRef}
      id="scroll-spacer"
      className="relative bg-white"
      style={{ userSelect: 'none', height: '500vh' }}
    >
      {/* 1G. Video background */}
      <VideoCanvas />

      {/* SECTION 2. Black gallery panel — slides up over the video, holds the
          scattered image grid. */}
      <div
        ref={panelRef}
        id="gallery-panel"
        className="fixed inset-0 z-10 h-screen w-screen overflow-hidden bg-black"
        style={{ transform: 'translateY(100%)', pointerEvents: 'none', willChange: 'transform' }}
      >
        <div ref={gridRef} className="absolute inset-x-0 top-0" style={{ height: '300vh' }}>
          {GALLERY_LAYOUT.map((item, i) => (
            <div
              key={i}
              ref={(el) => {
                imgRefs.current[i] = el
              }}
              className="absolute overflow-hidden"
              style={{
                left: item.left,
                top: `${item.top}vh`,
                width: `${item.w}vw`,
                aspectRatio: '3 / 4',
                transformOrigin: 'center center',
                willChange: 'transform, opacity',
              }}
            >
              <img
                src={GALLERY_IMAGES[i]}
                alt={`prmpt archive ${i + 1}`}
                loading="lazy"
                draggable={false}
                className="h-full w-full object-cover"
              />
              <span
                className="absolute bottom-2 left-2 font-medium uppercase text-white/70"
                style={{ fontSize: 11, letterSpacing: '-0.04em' }}
              >
                {String(i + 1).padStart(2, '0')} / archive
              </span>
            </div>
          ))}
        </div>
      </div>

      {/* 1I. White outro overlay */}
      <div
        ref={overlayRef}
        id="outro-overlay"
        className="fixed inset-0 z-[12] bg-white"
        style={{ opacity: 0, pointerEvents: 'none' }}
      />

      {/* 1B. Logo */}
      <motion.div
        className="fixed left-4 top-4 z-20 w-[124px] sm:w-[266px] lg:left-8 lg:top-8 lg:w-[355px]"
        style={{ pointerEvents: 'none', mixBlendMode: 'exclusion' }}
        initial={{ opacity: 0, y: 12 }}
        animate={{ opacity: 1, y: 0 }}
        transition={{ duration: 0.6, ease: EASE, delay: 0 }}
      >
        <Logo className="w-full" />
      </motion.div>

      {/* 1C. Caption */}
      <motion.p
        className="fixed left-4 top-[118px] z-20 w-[calc(100vw-32px)] font-medium text-white sm:top-[180px] sm:w-[calc(50vw-48px)] lg:left-8 lg:top-[244px] lg:w-[692px]"
        style={{
          pointerEvents: 'none',
          mixBlendMode: 'exclusion',
          fontSize: 12,
          lineHeight: '140%',
          letterSpacing: '-0.04em',
        }}
        initial={{ opacity: 0, y: 12 }}
        animate={{ opacity: 1, y: 0 }}
        transition={{ duration: 0.6, ease: EASE, delay: 0.3 }}
      >
        When switching between videos near the center, do not reset currentTime to 0 abruptly. Add a
        small dead zone: if cursor is within +/-50px of center, keep both videos at currentTime = 0
        and show whichever was last active.
      </motion.p>

      {/* 1D. Header navigation */}
      <motion.nav
        className="fixed right-4 top-4 z-20 flex h-[30px] items-center justify-between lg:right-8 lg:top-8 lg:w-[330px]"
        style={{ pointerEvents: 'none', mixBlendMode: 'exclusion' }}
        initial={{ opacity: 0, y: 12 }}
        animate={{ opacity: 1, y: 0 }}
        transition={{ duration: 0.6, ease: EASE, delay: 0.15 }}
      >
        <span
          className="hidden font-medium uppercase text-white sm:block"
          style={{ fontSize: 15, letterSpacing: '-0.02em' }}
        >
          About
        </span>
        <div className="flex items-center gap-5 lg:gap-[50px]">
          <svg
            className="h-6 w-6 lg:h-[30px] lg:w-[30px]"
            viewBox="0 0 40 40"
            fill="none"
            xmlns="http://www.w3.org/2000/svg"
          >
            <path d="M0 14H40" stroke="#FFFFFF" strokeWidth="2.5" />
            <path d="M0 26H40" stroke="#FFFFFF" strokeWidth="2.5" />
          </svg>
          <span
            className="font-medium text-white"
            style={{ fontSize: 13, letterSpacing: '-0.02em' }}
          >
            [ CART ]
          </span>
        </div>
      </motion.nav>

      {/* 1E. Product info (bottom right) */}
      <motion.div
        ref={infoRef}
        id="outro-info"
        data-outro-offset={166}
        className="fixed bottom-12 left-0 right-0 z-20 flex flex-col items-center lg:bottom-20 lg:left-auto lg:right-8 lg:w-[330px]"
        style={{ pointerEvents: 'none', mixBlendMode: 'exclusion', willChange: 'transform' }}
        initial={{ opacity: 0 }}
        animate={{ opacity: 1 }}
        transition={{ duration: 0.6, ease: EASE, delay: 0.45 }}
      >
        <div className="mb-3 flex w-[252px] flex-col items-start lg:mb-8 lg:w-full">
          <div className="relative mb-3 h-5 w-5 lg:h-[30px] lg:w-[30px]">
            <svg viewBox="0 0 40 40" fill="none" className="h-full w-full">
              <circle
                cx="20"
                cy="20"
                r="18.75"
                stroke="#FFFFFF"
                className="[stroke-width:2] lg:[stroke-width:2.5]"
              />
            </svg>
            <span
              ref={symbolRef}
              id="circle-symbol"
              className="absolute inset-0 flex items-center justify-center font-medium uppercase text-white"
              style={{ fontSize: 10, letterSpacing: '-0.04em' }}
            >
              8
            </span>
          </div>
          <div
            className="text-center font-medium uppercase text-white"
            style={{ fontSize: 20, lineHeight: '100%', letterSpacing: '-0.04em' }}
          >
            <span className="lg:text-[30px]">
              Archive Collection
              <br />
              "PROMPT"
            </span>
          </div>
        </div>
        <div
          className="text-center font-medium text-white"
          style={{ fontSize: 60, lineHeight: '100%', letterSpacing: '-0.04em' }}
        >
          <span className="lg:text-[80px]">$97,33</span>
        </div>
      </motion.div>

      {/* 1F. View button (bottom right, scales in on scroll) */}
      <div
        ref={buyRef}
        id="outro-buy"
        className="fixed bottom-[60px] left-4 right-4 z-20 flex h-[100px] items-center justify-center lg:bottom-8 lg:left-auto lg:right-8 lg:h-[174px] lg:w-[330px]"
        style={{
          pointerEvents: 'none',
          mixBlendMode: 'exclusion',
          background: '#fff',
          borderRadius: 1335,
          transformOrigin: 'right bottom',
          transform: 'scale(0)',
          willChange: 'transform',
        }}
      >
        <span
          className="font-medium lowercase"
          style={{
            fontSize: 72,
            letterSpacing: '-0.04em',
            color: '#fff',
            mixBlendMode: 'exclusion',
          }}
        >
          <span className="lg:text-[110px]">view</span>
        </span>
      </div>

      {/* 1J. Footer (bottom left) */}
      <div
        id="outro-footer"
        className="fixed bottom-4 left-4 z-20 font-medium uppercase text-white"
        style={{ pointerEvents: 'none', mixBlendMode: 'exclusion', fontSize: 12, letterSpacing: '-0.04em' }}
      >
        © prmpt 2026 — index
      </div>

      {/* 1A. Custom cursor */}
      <Cursor />
    </div>
  )
}
