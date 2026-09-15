import { useState } from 'react'
import { Download, FileArchive, Play, Trash2, X } from 'lucide-react'
import { Button, Empty, Pill, cx } from './ui'
import UploadZone from './UploadZone'
import { batch as runBatch } from '../lib/api'
import { downloadBlob, formatBytes } from '../lib/report'

/**
 * Many photos, one ZIP.
 *
 * The archive is assembled server-side and streamed back, so nothing here has
 * to hold a dozen decoded images in memory; the tally the UI shows comes from
 * response headers rather than from unzipping the result in the browser.
 */
export default function BatchPanel({ options, specId, size, maxBatch = 20, onError }) {
  const [files, setFiles] = useState([])
  const [busy, setBusy] = useState(false)
  const [progress, setProgress] = useState(0)
  const [done, setDone] = useState(null)

  const add = (incoming) => {
    setDone(null)
    setFiles((current) => {
      const seen = new Set(current.map((f) => `${f.name}:${f.size}`))
      const fresh = incoming.filter((f) => !seen.has(`${f.name}:${f.size}`))
      return [...current, ...fresh].slice(0, maxBatch)
    })
  }

  const start = async () => {
    setBusy(true)
    setProgress(0)
    setDone(null)
    onError(null)
    try {
      const result = await runBatch(files, { ...options, specId, ...size }, {
        onProgress: setProgress,
      })
      setDone(result)
    } catch (err) {
      onError(err.message)
    } finally {
      setBusy(false)
    }
  }

  return (
    <div className="space-y-4">
      <UploadZone multiple maxFiles={maxBatch} onFiles={add} disabled={busy} />

      {files.length === 0 ? (
        <Empty icon={FileArchive} title="No photos queued">
          Add up to {maxBatch} photos. You get back a ZIP with every processed image, a
          reports.json and a summary.csv.
        </Empty>
      ) : (
        <>
          <div className="flex items-center gap-2">
            <p className="text-sm text-slate-600">
              {files.length} of {maxBatch} photos queued
            </p>
            <button
              type="button"
              disabled={busy}
              onClick={() => {
                setFiles([])
                setDone(null)
              }}
              className="ml-auto inline-flex items-center gap-1 text-xs text-slate-500 hover:text-red-600 disabled:opacity-50"
            >
              <Trash2 className="w-3.5 h-3.5" />
              Clear all
            </button>
          </div>

          <ul className="divide-y divide-slate-100 rounded-xl border border-slate-200 max-h-64 overflow-y-auto">
            {files.map((file) => (
              <li key={`${file.name}:${file.size}`} className="flex items-center gap-3 px-3 py-2">
                <span className="truncate text-sm text-slate-700">{file.name}</span>
                <span className="ml-auto text-xs text-slate-400 shrink-0">
                  {formatBytes(file.size)}
                </span>
                <button
                  type="button"
                  disabled={busy}
                  aria-label={`Remove ${file.name}`}
                  onClick={() => setFiles((c) => c.filter((f) => f !== file))}
                  className="text-slate-300 hover:text-red-500 disabled:opacity-50"
                >
                  <X className="w-4 h-4" />
                </button>
              </li>
            ))}
          </ul>

          <Button onClick={start} busy={busy} icon={Play}>
            {busy ? 'Processing…' : `Process ${files.length} photos`}
          </Button>

          {busy && (
            <div className="h-1.5 rounded-full bg-slate-100 overflow-hidden">
              <div
                className="h-full bg-primary transition-all"
                style={{ width: `${Math.round(progress * 100)}%` }}
              />
            </div>
          )}
        </>
      )}

      {done && (
        <div className="rounded-xl border border-emerald-200 bg-emerald-50 p-4 space-y-3">
          <p className="text-sm text-emerald-900">
            {done.total} photos processed.{' '}
            <Pill
              className={cx(
                'ml-1',
                done.compliant === done.total
                  ? 'bg-white text-emerald-700 border-emerald-200'
                  : 'bg-white text-amber-700 border-amber-200',
              )}
            >
              {done.compliant} ready to submit
            </Pill>
          </p>
          <p className="text-xs text-emerald-800/80">
            The ZIP holds every processed image plus reports.json with the full rule-by-rule
            breakdown, and summary.csv for a quick scan of what failed.
          </p>
          <Button
            variant="success"
            icon={Download}
            onClick={() => downloadBlob(done.blob, 'passport_photos.zip')}
          >
            Download ZIP ({formatBytes(done.blob.size)})
          </Button>
        </div>
      )}
    </div>
  )
}
