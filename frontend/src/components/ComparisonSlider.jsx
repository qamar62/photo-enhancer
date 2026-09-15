import { useCallback, useRef, useState } from 'react'
import { MoveHorizontal } from 'lucide-react'

/**
 * Before / after wipe.
 *
 * Both images are `object-contain` inside one box shaped by the *output*
 * aspect ratio, so the original sits letterboxed behind the result. That is
 * deliberate: re-framing is most of what the pipeline does, and a slider that
 * stretched the original to match would hide exactly the change it is meant to
 * show.
 */
export default function ComparisonSlider({ before, after, aspect = 35 / 45 }) {
  const frameRef = useRef(null)
  const [position, setPosition] = useState(50)
  const [dragging, setDragging] = useState(false)

  const moveTo = useCallback((clientX) => {
    const rect = frameRef.current?.getBoundingClientRect()
    if (!rect || !rect.width) return
    const pct = ((clientX - rect.left) / rect.width) * 100
    setPosition(Math.max(0, Math.min(100, pct)))
  }, [])

  return (
    <div className="space-y-2">
      <div
        ref={frameRef}
        className="relative w-full mx-auto overflow-hidden rounded-xl bg-slate-100 select-none touch-none"
        style={{ aspectRatio: aspect, maxHeight: '60vh' }}
        onPointerDown={(e) => {
          e.currentTarget.setPointerCapture(e.pointerId)
          setDragging(true)
          moveTo(e.clientX)
        }}
        onPointerMove={(e) => dragging && moveTo(e.clientX)}
        onPointerUp={() => setDragging(false)}
        onPointerCancel={() => setDragging(false)}
      >
        <img
          src={before}
          alt="Original"
          draggable={false}
          className="absolute inset-0 w-full h-full object-contain"
        />
        <div
          className="absolute inset-0"
          style={{ clipPath: `inset(0 0 0 ${position}%)` }}
        >
          <img
            src={after}
            alt="Enhanced"
            draggable={false}
            className="absolute inset-0 w-full h-full object-contain bg-white"
          />
        </div>

        <div
          className="absolute inset-y-0 w-0.5 bg-white shadow-[0_0_0_1px_rgba(0,0,0,0.15)] pointer-events-none"
          style={{ left: `${position}%` }}
        />
        <button
          type="button"
          aria-label="Compare before and after"
          aria-valuenow={Math.round(position)}
          aria-valuemin={0}
          aria-valuemax={100}
          role="slider"
          onKeyDown={(e) => {
            if (e.key === 'ArrowLeft') setPosition((p) => Math.max(0, p - 4))
            if (e.key === 'ArrowRight') setPosition((p) => Math.min(100, p + 4))
          }}
          className="absolute top-1/2 -translate-y-1/2 -translate-x-1/2 w-9 h-9 rounded-full bg-white shadow-lg
                     flex items-center justify-center text-slate-600 cursor-ew-resize
                     focus:outline-none focus-visible:ring-2 focus-visible:ring-ring"
          style={{ left: `${position}%` }}
        >
          <MoveHorizontal className="w-4 h-4" />
        </button>

        <span className="absolute left-2 bottom-2 px-2 py-0.5 rounded bg-black/55 text-white text-[11px]">
          Original
        </span>
        <span className="absolute right-2 bottom-2 px-2 py-0.5 rounded bg-black/55 text-white text-[11px]">
          Enhanced
        </span>
      </div>
      <p className="text-xs text-center text-slate-400">Drag the handle, or use the arrow keys.</p>
    </div>
  )
}
