import { ArrowRight } from 'lucide-react'
import { verdictMeta } from '../lib/report'
import { Pill, cx } from './ui'

/**
 * The headline number.
 *
 * The score is not a plain average on the backend - the verdict picks a band
 * and the score only positions the photo inside it - so the ring is coloured
 * from the verdict, never from the number. A 74 that is "needs attention" and a
 * 76 that is "acceptable" have to look different, and they do.
 */
export default function ScoreDial({ score, verdict, before, verdictBefore, size = 132 }) {
  const meta = verdictMeta(verdict)
  const stroke = 10
  const radius = (size - stroke) / 2
  const circumference = 2 * Math.PI * radius
  const clamped = Math.max(0, Math.min(100, score ?? 0))
  const improved = typeof before === 'number' && Math.round(before) !== Math.round(clamped)

  return (
    <div className="flex items-center gap-5">
      <div className="relative shrink-0" style={{ width: size, height: size }}>
        <svg width={size} height={size} className="-rotate-90">
          <circle
            cx={size / 2}
            cy={size / 2}
            r={radius}
            fill="none"
            strokeWidth={stroke}
            className="stroke-slate-100"
          />
          <circle
            cx={size / 2}
            cy={size / 2}
            r={radius}
            fill="none"
            strokeWidth={stroke}
            strokeLinecap="round"
            strokeDasharray={circumference}
            strokeDashoffset={circumference * (1 - clamped / 100)}
            className={cx('transition-all duration-700 ease-out', meta.ring)}
            stroke="currentColor"
          />
        </svg>
        <div className="absolute inset-0 flex flex-col items-center justify-center">
          <span className={cx('text-3xl font-bold tabular-nums', meta.ring)}>
            {Math.round(clamped)}
          </span>
          <span className="text-[10px] uppercase tracking-wider text-slate-400">out of 100</span>
        </div>
      </div>

      <div className="min-w-0">
        <Pill className={meta.chip}>{meta.label}</Pill>
        <p className="text-sm text-slate-600 mt-2">{meta.blurb}</p>
        {improved && (
          <p className="mt-2 flex items-center gap-1.5 text-xs text-slate-500">
            <span className="tabular-nums">{Math.round(before)}</span>
            <span className="text-slate-400">{verdictMeta(verdictBefore).label}</span>
            <ArrowRight className="w-3 h-3" />
            <span className="tabular-nums font-medium text-slate-700">{Math.round(clamped)}</span>
            <span className="text-slate-400">after our fixes</span>
          </p>
        )}
      </div>
    </div>
  )
}
