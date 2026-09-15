import { useState } from 'react'
import { Download, Grid2x2, Image as ImageIcon, Printer, SlidersHorizontal } from 'lucide-react'
import { Button, cx } from './ui'
import ComparisonSlider from './ComparisonSlider'
import GuideOverlay from './GuideOverlay'
import PrintSheet from './PrintSheet'
import { downloadBlob, formatBytes } from '../lib/report'

const TABS = [
  { id: 'photo', label: 'Photo', icon: ImageIcon },
  { id: 'compare', label: 'Compare', icon: SlidersHorizontal },
  { id: 'guides', label: 'Guides', icon: Grid2x2 },
  { id: 'print', label: 'Print sheet', icon: Printer },
]

/**
 * The finished photo, four ways to look at it, and the download.
 *
 * The print tab is hidden for pixel-only specs: a sheet is laid out in
 * millimetres, and a photo with no physical size has nothing to lay out.
 */
export default function ResultView({ result, originalUrl, papers, spec }) {
  const [tab, setTab] = useState('photo')
  const { image, report, filename, bytes, blob } = result
  const aspect = report.spec?.aspect || 35 / 45
  const printable = Boolean(report.spec?.physical)
  const tabs = TABS.filter((t) => t.id !== 'print' || printable)

  return (
    <div className="space-y-4">
      <div className="flex flex-wrap gap-1 p-1 rounded-xl bg-slate-100">
        {tabs.map((t) => (
          <button
            key={t.id}
            type="button"
            onClick={() => setTab(t.id)}
            className={cx(
              'flex-1 min-w-[6rem] inline-flex items-center justify-center gap-1.5 rounded-lg px-3 py-2 text-sm font-medium transition-colors',
              tab === t.id
                ? 'bg-white text-slate-900 shadow-sm'
                : 'text-slate-500 hover:text-slate-800',
            )}
          >
            <t.icon className="w-4 h-4" />
            {t.label}
          </button>
        ))}
      </div>

      {tab === 'photo' && (
        <div
          className="mx-auto overflow-hidden rounded-xl border border-slate-200 bg-white"
          style={{ aspectRatio: aspect, maxHeight: '60vh' }}
        >
          <img src={image} alt="Enhanced passport photo" className="w-full h-full object-contain" />
        </div>
      )}

      {tab === 'compare' && (
        <ComparisonSlider before={originalUrl} after={image} aspect={aspect} />
      )}

      {tab === 'guides' && (
        <GuideOverlay
          src={image}
          guide={report.guide}
          landmarks={report.landmarks}
          aspect={aspect}
        />
      )}

      {tab === 'print' && (
        <PrintSheet papers={papers} specId={spec?.id} photoBlob={blob} />
      )}

      {tab !== 'print' && (
        <div className="flex flex-wrap items-center gap-3">
          <Button variant="success" icon={Download} onClick={() => downloadBlob(blob, filename)}>
            Download photo
          </Button>
          <span className="text-xs text-slate-500">
            {report.image_size?.width}×{report.image_size?.height} px
            {report.spec?.physical ? ` · ${report.spec.size_label}` : ''}
            {bytes ? ` · ${formatBytes(bytes)}` : ''}
          </span>
        </div>
      )}
    </div>
  )
}
