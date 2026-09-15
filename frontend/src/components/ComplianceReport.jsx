import { useState } from 'react'
import { AlertTriangle, Check, ChevronRight, Sparkles, X, Minus } from 'lucide-react'
import { groupChecks, byUrgency, statusMeta, SEVERITIES } from '../lib/report'
import { Pill, cx } from './ui'
import ScoreDial from './ScoreDial'
import RetakeTips from './RetakeTips'

const ICONS = { pass: Check, warn: AlertTriangle, fail: X }

function CheckRow({ check }) {
  const [open, setOpen] = useState(false)
  const meta = statusMeta(check.status)
  const Icon = ICONS[check.status] || Minus
  const hasDetail = Boolean(check.requirement || check.measured || check.tip)

  return (
    <li className="border-b border-slate-100 last:border-0">
      <button
        type="button"
        onClick={() => hasDetail && setOpen((v) => !v)}
        aria-expanded={open}
        className={cx(
          'w-full flex items-center gap-3 px-3 py-2.5 text-left rounded-lg',
          hasDetail && 'hover:bg-slate-50',
        )}
      >
        <span
          className={cx(
            'shrink-0 w-5 h-5 rounded-full flex items-center justify-center text-white',
            meta.dot,
          )}
        >
          <Icon className="w-3 h-3" strokeWidth={3} />
        </span>

        <span className="min-w-0 flex-1">
          <span className="block text-sm text-slate-800">{check.label}</span>
          {!open && check.measured && (
            <span className="block text-xs text-slate-500 truncate">{check.measured}</span>
          )}
        </span>

        {check.fixed && (
          <Pill className="bg-blue-50 text-blue-700 border-blue-200 shrink-0">
            <Sparkles className="w-3 h-3" />
            Fixed
          </Pill>
        )}
        {check.status !== 'pass' && (
          <Pill className={cx('shrink-0 border-transparent', SEVERITIES[check.severity]?.chip)}>
            {SEVERITIES[check.severity]?.label}
          </Pill>
        )}
        {hasDetail && (
          <ChevronRight
            className={cx('w-4 h-4 text-slate-300 shrink-0 transition-transform', open && 'rotate-90')}
          />
        )}
      </button>

      {open && (
        <div className="px-3 pb-3 pl-11 space-y-1.5 text-xs">
          <p className="text-slate-600">
            <span className="text-slate-400">Required: </span>
            {check.requirement}
          </p>
          <p className={meta.text}>
            <span className="text-slate-400">Measured: </span>
            {check.measured}
          </p>
          {check.tip && <p className="text-slate-500 pt-1">{check.tip}</p>}
        </div>
      )}
    </li>
  )
}

function CategoryBlock({ group }) {
  const fails = group.checks.filter((c) => c.status === 'fail').length
  const warns = group.checks.filter((c) => c.status === 'warn').length
  const [open, setOpen] = useState(fails > 0 || warns > 0)
  const sorted = [...group.checks].sort(byUrgency)

  return (
    <div className="rounded-xl border border-slate-200 overflow-hidden">
      <button
        type="button"
        onClick={() => setOpen((v) => !v)}
        aria-expanded={open}
        className="w-full flex items-center gap-3 px-3 py-2.5 bg-slate-50 hover:bg-slate-100 transition-colors"
      >
        <ChevronRight
          className={cx('w-4 h-4 text-slate-400 transition-transform', open && 'rotate-90')}
        />
        <span className="text-sm font-medium text-slate-800">{group.label}</span>
        <span className="ml-auto flex items-center gap-1.5">
          {fails > 0 && <Pill className={statusMeta('fail').chip}>{fails} failing</Pill>}
          {warns > 0 && <Pill className={statusMeta('warn').chip}>{warns} borderline</Pill>}
          {fails === 0 && warns === 0 && (
            <Pill className={statusMeta('pass').chip}>
              <Check className="w-3 h-3" />
              All clear
            </Pill>
          )}
        </span>
      </button>
      {open && (
        <ul className="divide-y divide-slate-100">
          {sorted.map((check) => (
            <CheckRow key={check.id} check={check} />
          ))}
        </ul>
      )}
    </div>
  )
}

/**
 * The full pass / borderline / fail breakdown.
 *
 * Everything shown here is measured server-side and arrives in the report; the
 * panel only decides what order to reveal it in - retake reasons first, because
 * no amount of scrolling through passing rules helps someone whose eyes were
 * closed.
 */
export default function ComplianceReport({ report, fixes = [] }) {
  if (!report) return null
  const { summary } = report
  const groups = groupChecks(report.checks)

  return (
    <div className="space-y-5">
      <ScoreDial
        score={summary.score}
        verdict={summary.verdict}
        before={report.score_before}
        verdictBefore={report.verdict_before}
      />

      <div className="grid grid-cols-3 gap-2 text-center">
        {[
          ['Passed', summary.passed, 'text-emerald-600'],
          ['Borderline', summary.warnings, 'text-amber-600'],
          ['Failing', summary.failures, 'text-red-600'],
        ].map(([label, value, tone]) => (
          <div key={label} className="rounded-lg bg-slate-50 py-2.5">
            <div className={cx('text-xl font-semibold tabular-nums', tone)}>{value}</div>
            <div className="text-[11px] uppercase tracking-wide text-slate-500">{label}</div>
          </div>
        ))}
      </div>

      <RetakeTips reasons={summary.retake_reasons} blocking={summary.blocking} />

      {fixes.length > 0 && (
        <div className="rounded-xl border border-blue-200 bg-blue-50/60 p-3">
          <p className="flex items-center gap-2 text-sm font-medium text-blue-900">
            <Sparkles className="w-4 h-4" />
            {fixes.length} {fixes.length === 1 ? 'correction' : 'corrections'} applied
          </p>
          <ul className="mt-2 flex flex-wrap gap-1.5">
            {fixes.map((fix) => (
              <li key={fix.id}>
                <Pill className="bg-white text-blue-700 border-blue-200">{fix.label}</Pill>
              </li>
            ))}
          </ul>
        </div>
      )}

      <div className="space-y-2">
        {groups.map((group) => (
          <CategoryBlock key={group.id} group={group} />
        ))}
      </div>

      <p className="text-xs text-slate-400">
        Checked against {report.spec?.name} · {report.checks.length} rules ·{' '}
        {report.processing_ms} ms
      </p>
    </div>
  )
}
