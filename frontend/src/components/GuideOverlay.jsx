import { cx } from './ui'

/**
 * The ICAO guide drawn over the finished photo.
 *
 * Coordinates arrive from the backend already normalised to the output image,
 * so the SVG uses a 0-100 viewBox with preserveAspectRatio="none" and every
 * stroke is non-scaling - that way the lines land on the right pixels at any
 * display size without the geometry being recomputed in the browser, where it
 * could drift from what the report actually measured.
 *
 * Bands are what the standard allows; solid lines are what this photo does.
 */
export default function GuideOverlay({ src, guide, landmarks, aspect = 35 / 45, showLabels = true }) {
  if (!guide || !landmarks) {
    return <img src={src} alt="Result" className="w-full rounded-xl" />
  }

  const pct = (v) => v * 100
  const eyeBand = { top: pct(guide.eye_min), height: pct(guide.eye_max - guide.eye_min) }
  const centre = { left: 50 - pct(guide.centre_tolerance), width: pct(guide.centre_tolerance) * 2 }

  const headTop = pct(landmarks.head_top_y)
  const chin = pct(landmarks.chin_y)
  const eyeLine = pct(landmarks.eye_line_y)
  const midline = pct(landmarks.midline_x)
  const headPct = Math.round(chin - headTop)

  return (
    <div className="space-y-3">
      <div
        className="relative mx-auto overflow-hidden rounded-xl bg-white"
        style={{ aspectRatio: aspect, maxHeight: '60vh' }}
      >
        <img src={src} alt="Result with guide lines" className="absolute inset-0 w-full h-full object-contain" />

        <svg
          viewBox="0 0 100 100"
          preserveAspectRatio="none"
          className="absolute inset-0 w-full h-full"
          aria-hidden="true"
        >
          {/* allowed eye-line band */}
          <rect x="0" y={eyeBand.top} width="100" height={eyeBand.height} fill="rgb(16 185 129 / 0.16)" />
          <line
            x1="0"
            x2="100"
            y1={pct(guide.eye_target)}
            y2={pct(guide.eye_target)}
            stroke="rgb(5 150 105)"
            strokeDasharray="4 3"
            strokeWidth="1"
            vectorEffect="non-scaling-stroke"
          />

          {/* allowed horizontal centring */}
          <rect x={centre.left} y="0" width={centre.width} height="100" fill="rgb(59 130 246 / 0.10)" />

          {/* measured: eye line, head extents, midline */}
          <line
            x1="0"
            x2="100"
            y1={eyeLine}
            y2={eyeLine}
            stroke="rgb(220 38 38)"
            strokeWidth="1.5"
            vectorEffect="non-scaling-stroke"
          />
          <line
            x1="0"
            x2="100"
            y1={headTop}
            y2={headTop}
            stroke="rgb(37 99 235)"
            strokeWidth="1.5"
            vectorEffect="non-scaling-stroke"
          />
          <line
            x1="0"
            x2="100"
            y1={chin}
            y2={chin}
            stroke="rgb(37 99 235)"
            strokeWidth="1.5"
            vectorEffect="non-scaling-stroke"
          />
          <line
            x1={midline}
            x2={midline}
            y1="0"
            y2="100"
            stroke="rgb(37 99 235)"
            strokeWidth="1"
            strokeDasharray="3 3"
            vectorEffect="non-scaling-stroke"
          />
        </svg>

        {/* Labels are HTML so the stretched viewBox cannot squash the type. */}
        {showLabels && (
          <>
            <Label style={{ top: `${headTop}%`, left: 6 }}>Top of head</Label>
            <Label style={{ top: `${eyeLine}%`, left: 6 }} tone="red">
              Eye line {Math.round(eyeLine)}%
            </Label>
            <Label style={{ top: `${chin}%`, left: 6 }}>Chin</Label>
            <Label style={{ top: `${(headTop + chin) / 2}%`, right: 6 }}>
              Head {headPct}% of height
            </Label>
          </>
        )}
      </div>

      <dl className="grid sm:grid-cols-3 gap-2 text-xs">
        <Legend swatch="bg-emerald-500/30" label="Eye line must sit here">
          {Math.round(pct(guide.eye_min))}–{Math.round(pct(guide.eye_max))}% from the top
        </Legend>
        <Legend swatch="bg-blue-500/20" label="Head must be centred">
          within ±{Math.round(pct(guide.centre_tolerance))}% of the middle
        </Legend>
        <Legend swatch="bg-blue-600" label="Head height">
          {Math.round(pct(guide.head_min))}–{Math.round(pct(guide.head_max))}% of the photo
        </Legend>
      </dl>
    </div>
  )
}

function Label({ style, tone, children }) {
  return (
    <span
      className={cx(
        'absolute -translate-y-1/2 px-1.5 py-0.5 rounded text-[10px] font-medium text-white whitespace-nowrap',
        tone === 'red' ? 'bg-red-600/90' : 'bg-blue-600/90',
      )}
      style={style}
    >
      {children}
    </span>
  )
}

function Legend({ swatch, label, children }) {
  return (
    <div className="flex items-start gap-2">
      <span className={cx('mt-0.5 w-3 h-3 rounded-sm shrink-0', swatch)} />
      <div className="min-w-0">
        <dt className="font-medium text-slate-700">{label}</dt>
        <dd className="text-slate-500">{children}</dd>
      </div>
    </div>
  )
}
