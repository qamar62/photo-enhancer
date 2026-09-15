import { useState } from 'react'
import { Printer, Download, AlertCircle } from 'lucide-react'
import { Button, Field, inputClass } from './ui'
import { printSheet } from '../lib/api'
import { downloadBlob } from '../lib/report'

/**
 * Tile the finished photo onto a sheet of paper.
 *
 * The sheet is built server-side at a real DPI, which is the only way the cut
 * marks land 35 mm apart on paper. The one thing the user must not do is scale
 * it at print time, so that warning is surfaced here and not buried.
 */
export default function PrintSheet({ papers, specId, photoBlob, disabled }) {
  const [paper, setPaper] = useState(papers[0]?.id || '4x6')
  const [dpi, setDpi] = useState(300)
  const [cutGuides, setCutGuides] = useState(true)
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState(null)
  const [sheet, setSheet] = useState(null)

  const build = async () => {
    setBusy(true)
    setError(null)
    setSheet(null)
    try {
      const file = new File([photoBlob], 'photo.jpg', { type: photoBlob.type || 'image/jpeg' })
      const { blob, info } = await printSheet(file, {
        specId,
        paper,
        dpi,
        cutGuides,
        alreadyProcessed: true,
      })
      setSheet({ url: URL.createObjectURL(blob), blob, info })
    } catch (err) {
      setError(err.message)
    } finally {
      setBusy(false)
    }
  }

  return (
    <div className="space-y-4">
      <div className="grid sm:grid-cols-3 gap-3">
        <Field label="Paper" className="sm:col-span-1">
          <select
            value={paper}
            onChange={(e) => setPaper(e.target.value)}
            disabled={disabled || busy}
            className={inputClass}
          >
            {papers.map((p) => (
              <option key={p.id} value={p.id}>
                {p.name} ({p.width_mm}×{p.height_mm} mm)
              </option>
            ))}
          </select>
        </Field>
        <Field label="Print resolution" hint="300 dpi suits any photo lab.">
          <select
            value={dpi}
            onChange={(e) => setDpi(Number(e.target.value))}
            disabled={disabled || busy}
            className={inputClass}
          >
            <option value={300}>300 dpi</option>
            <option value={600}>600 dpi</option>
          </select>
        </Field>
        <Field label="Cut guides">
          <label className="flex items-center gap-2 h-[38px] px-3 rounded-lg border border-slate-300 bg-white">
            <input
              type="checkbox"
              checked={cutGuides}
              disabled={disabled || busy}
              onChange={(e) => setCutGuides(e.target.checked)}
              className="w-4 h-4 rounded border-slate-300 text-primary focus:ring-ring"
            />
            <span className="text-sm text-slate-700">Show cut marks</span>
          </label>
        </Field>
      </div>

      <Button onClick={build} busy={busy} disabled={disabled} icon={Printer}>
        {busy ? 'Building sheet…' : 'Build print sheet'}
      </Button>

      {error && (
        <p className="flex items-start gap-2 text-sm text-red-700">
          <AlertCircle className="w-4 h-4 mt-0.5 shrink-0" />
          {error}
        </p>
      )}

      {sheet && (
        <div className="space-y-3">
          <img
            src={sheet.url}
            alt="Print sheet preview"
            className="w-full rounded-xl border border-slate-200 bg-white"
          />
          <div className="rounded-lg bg-amber-50 border border-amber-200 px-3 py-2 text-xs text-amber-900">
            {sheet.info?.copies
              ? `${sheet.info.copies} copies (${sheet.info.columns}×${sheet.info.rows}) on ${sheet.info.paper_name} at ${sheet.info.dpi} dpi. `
              : ''}
            Print at 100% or “actual size” — a “fit to page” setting rescales the sheet, and the
            photos come out the wrong physical size
            {sheet.info?.cell_mm ? ` instead of ${sheet.info.cell_mm.join('×')} mm` : ''}.
          </div>
          <Button
            variant="success"
            icon={Download}
            onClick={() => downloadBlob(sheet.blob, `print_sheet_${paper}.jpg`)}
          >
            Download sheet
          </Button>
        </div>
      )}
    </div>
  )
}
