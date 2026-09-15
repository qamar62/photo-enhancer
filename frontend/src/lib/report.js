/**
 * Presentation helpers for the compliance report.
 *
 * The backend decides pass/warn/fail and the verdict; nothing here re-judges a
 * photo, it only chooses words and colours for a decision already made.
 */

export const VERDICTS = {
  compliant: {
    label: 'Compliant',
    blurb: 'This photo meets every rule we check.',
    ring: 'text-emerald-600',
    chip: 'bg-emerald-50 text-emerald-700 border-emerald-200',
    bar: 'bg-emerald-500',
  },
  acceptable: {
    label: 'Likely accepted',
    blurb: 'Nothing here should get it rejected, but a few things are close to the limit.',
    ring: 'text-lime-600',
    chip: 'bg-lime-50 text-lime-700 border-lime-200',
    bar: 'bg-lime-500',
  },
  needs_attention: {
    label: 'Needs attention',
    blurb: 'Some rules are outside the allowed range. Check the list below.',
    ring: 'text-amber-600',
    chip: 'bg-amber-50 text-amber-700 border-amber-200',
    bar: 'bg-amber-500',
  },
  rejected: {
    label: 'Would be rejected',
    blurb: 'At least one rule fails in a way that cannot be fixed automatically.',
    ring: 'text-red-600',
    chip: 'bg-red-50 text-red-700 border-red-200',
    bar: 'bg-red-500',
  },
  error: {
    label: 'Failed',
    blurb: 'This photo could not be processed.',
    ring: 'text-red-600',
    chip: 'bg-red-50 text-red-700 border-red-200',
    bar: 'bg-red-500',
  },
}

export const STATUSES = {
  pass: {
    label: 'Pass',
    dot: 'bg-emerald-500',
    text: 'text-emerald-700',
    chip: 'bg-emerald-50 text-emerald-700 border-emerald-200',
  },
  warn: {
    label: 'Borderline',
    dot: 'bg-amber-500',
    text: 'text-amber-700',
    chip: 'bg-amber-50 text-amber-700 border-amber-200',
  },
  fail: {
    label: 'Fail',
    dot: 'bg-red-500',
    text: 'text-red-700',
    chip: 'bg-red-50 text-red-700 border-red-200',
  },
}

export const SEVERITIES = {
  critical: { label: 'Critical', chip: 'bg-red-100 text-red-700' },
  major: { label: 'Major', chip: 'bg-amber-100 text-amber-700' },
  minor: { label: 'Minor', chip: 'bg-slate-100 text-slate-600' },
}

export function verdictMeta(verdict) {
  return VERDICTS[verdict] || VERDICTS.needs_attention
}

export function statusMeta(status) {
  return STATUSES[status] || STATUSES.warn
}

/** Category order, worst-first inside the panel but stable between photos. */
export const CATEGORY_ORDER = [
  'subject',
  'framing',
  'pose',
  'expression',
  'lighting',
  'background',
  'quality',
]

/**
 * Group checks for the report panel, keeping CATEGORY_ORDER but pushing any
 * category the backend adds later to the end rather than dropping it.
 */
export function groupChecks(checks = []) {
  const groups = new Map()
  for (const check of checks) {
    if (!groups.has(check.category)) {
      groups.set(check.category, { id: check.category, label: check.category_label, checks: [] })
    }
    groups.get(check.category).checks.push(check)
  }
  const rank = (id) => {
    const i = CATEGORY_ORDER.indexOf(id)
    return i === -1 ? CATEGORY_ORDER.length : i
  }
  return [...groups.values()].sort((a, b) => rank(a.id) - rank(b.id))
}

/** fail first, then warn, then pass - the things needing action float up. */
const STATUS_RANK = { fail: 0, warn: 1, pass: 2 }
export function byUrgency(a, b) {
  const d = (STATUS_RANK[a.status] ?? 3) - (STATUS_RANK[b.status] ?? 3)
  if (d !== 0) return d
  const s = { critical: 0, major: 1, minor: 2 }
  return (s[a.severity] ?? 3) - (s[b.severity] ?? 3)
}

/** "827 × 1063 px" / "35×45 mm @ 600 dpi" - spec.size_label already has this. */
export function describeSpec(spec) {
  if (!spec) return ''
  return spec.size_label || `${spec.width_px}×${spec.height_px} px`
}

export function hexToRgbString(hex) {
  const m = /^#?([a-f\d]{2})([a-f\d]{2})([a-f\d]{2})$/i.exec(hex || '')
  if (!m) return null
  return [parseInt(m[1], 16), parseInt(m[2], 16), parseInt(m[3], 16)].join(',')
}

export function rgbToHex(rgb) {
  if (!Array.isArray(rgb) || rgb.length < 3) return '#ffffff'
  return `#${rgb.map((v) => Math.max(0, Math.min(255, v)).toString(16).padStart(2, '0')).join('')}`
}

/** A data URL is what /process returns; the sheet and print flows need a Blob. */
export function dataUrlToBlob(dataUrl) {
  const [head, body] = dataUrl.split(',')
  const mime = /:(.*?);/.exec(head)?.[1] || 'image/jpeg'
  const binary = atob(body)
  const bytes = new Uint8Array(binary.length)
  for (let i = 0; i < binary.length; i += 1) bytes[i] = binary.charCodeAt(i)
  return new Blob([bytes], { type: mime })
}

export function downloadBlob(blob, filename) {
  const url = URL.createObjectURL(blob)
  const link = document.createElement('a')
  link.href = url
  link.download = filename
  document.body.appendChild(link)
  link.click()
  link.remove()
  // Revoking immediately can cancel the download in Safari, so give it a tick.
  setTimeout(() => URL.revokeObjectURL(url), 10_000)
}

export function formatBytes(bytes) {
  if (!bytes) return ''
  if (bytes < 1024) return `${bytes} B`
  if (bytes < 1024 * 1024) return `${Math.round(bytes / 1024)} KB`
  return `${(bytes / 1024 / 1024).toFixed(1)} MB`
}
