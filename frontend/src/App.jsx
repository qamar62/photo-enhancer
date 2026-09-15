import { useCallback, useEffect, useRef, useState } from 'react'
import {
  AlertCircle,
  Camera,
  ClipboardCheck,
  Layers,
  Loader2,
  RefreshCw,
  ScanFace,
  Settings2,
  Sparkles,
  User,
  X,
} from 'lucide-react'
import { analyse, enhance, getSpecs } from './lib/api'
import { dataUrlToBlob, rgbToHex } from './lib/report'
import { Button, Card, Empty, cx } from './components/ui'
import UploadZone from './components/UploadZone'
import OptionsPanel from './components/OptionsPanel'
import ComplianceReport from './components/ComplianceReport'
import ResultView from './components/ResultView'
import BatchPanel from './components/BatchPanel'
import Guidelines from './components/Guidelines'

const DEFAULT_OPTIONS = {
  removeBackground: true,
  background: '#fafafa',
  autoFrame: true,
  autoEnhance: true,
  fixRedEye: true,
  sharpen: true,
  format: 'jpeg',
}

export default function App() {
  const [catalogue, setCatalogue] = useState(null)
  const [booting, setBooting] = useState(true)
  const [specId, setSpecId] = useState(null)
  const [size, setSize] = useState({ width: 1200, height: 1600 })
  const [options, setOptions] = useState(DEFAULT_OPTIONS)

  const [mode, setMode] = useState('single')
  const [file, setFile] = useState(null)
  const [originalUrl, setOriginalUrl] = useState(null)
  const [result, setResult] = useState(null)
  const [preflight, setPreflight] = useState(null)
  const [working, setWorking] = useState(null) // 'analyse' | 'enhance' | null
  const [error, setError] = useState(null)

  // Object URLs are a manual allocation; without this the browser holds on to
  // every photo the user has looked at for the lifetime of the tab.
  const urlRef = useRef(null)
  useEffect(() => {
    urlRef.current = originalUrl
  }, [originalUrl])
  useEffect(() => () => urlRef.current && URL.revokeObjectURL(urlRef.current), [])

  useEffect(() => {
    let alive = true
    getSpecs()
      .then((data) => {
        if (!alive) return
        setCatalogue(data)
        const first = data.specs.find((s) => s.id === data.default) || data.specs[0]
        setSpecId(first?.id)
        if (first) {
          setSize({ width: first.width_px, height: first.height_px })
          setOptions((o) => ({ ...o, background: rgbToHex(first.background) }))
        }
      })
      .catch((err) => alive && setError(err.message))
      .finally(() => alive && setBooting(false))
    return () => {
      alive = false
    }
  }, [])

  const specs = catalogue?.specs || []
  const papers = catalogue?.papers || []
  const spec = specs.find((s) => s.id === specId)
  const busy = working !== null

  // A pixel-only spec is the only one that takes a custom size; sending width
  // and height with a millimetre spec would quietly override its real size.
  const sizeArgs = spec && !spec.physical ? { width: size.width, height: size.height } : {}

  const chooseFile = useCallback(
    ([next]) => {
      if (!next) return
      if (urlRef.current) URL.revokeObjectURL(urlRef.current)
      setFile(next)
      setOriginalUrl(URL.createObjectURL(next))
      setResult(null)
      setPreflight(null)
      setError(null)
    },
    [],
  )

  const reset = () => {
    if (urlRef.current) URL.revokeObjectURL(urlRef.current)
    urlRef.current = null
    setFile(null)
    setOriginalUrl(null)
    setResult(null)
    setPreflight(null)
    setError(null)
  }

  const runAnalyse = async () => {
    setWorking('analyse')
    setError(null)
    try {
      const report = await analyse(file, { specId, ...sizeArgs })
      setPreflight(report)
      setResult(null)
    } catch (err) {
      setError(err.message)
    } finally {
      setWorking(null)
    }
  }

  const runEnhance = async () => {
    setWorking('enhance')
    setError(null)
    try {
      const data = await enhance(file, { ...options, specId, ...sizeArgs })
      // One conversion here serves the download button and the print sheet;
      // re-decoding the data URL on every click would be wasteful and, for a
      // 600 dpi PNG, noticeably slow.
      setResult({ ...data, blob: dataUrlToBlob(data.image) })
      setPreflight(null)
    } catch (err) {
      setError(err.message)
    } finally {
      setWorking(null)
    }
  }

  const shownReport = result?.report || preflight

  return (
    <div className="min-h-screen bg-slate-50">
      <header className="bg-white border-b border-slate-200">
        <div className="max-w-7xl mx-auto px-4 py-5 flex items-center gap-3">
          <span className="w-10 h-10 rounded-xl bg-primary/10 flex items-center justify-center">
            <Camera className="w-5 h-5 text-primary" />
          </span>
          <div className="min-w-0">
            <h1 className="text-lg font-semibold text-slate-900 leading-tight">
              Passport Photo Studio
            </h1>
            <p className="text-sm text-slate-500">
              ICAO-compliant photos, checked rule by rule and fixed where we can.
            </p>
          </div>
          {file && mode === 'single' && (
            <Button variant="ghost" icon={RefreshCw} onClick={reset} className="ml-auto">
              Start over
            </Button>
          )}
        </div>
      </header>

      <main className="max-w-7xl mx-auto px-4 py-6 space-y-6">
        <div className="inline-flex p-1 rounded-xl bg-slate-200/70">
          {[
            { id: 'single', label: 'One photo', icon: User },
            { id: 'batch', label: 'Batch', icon: Layers },
          ].map((m) => (
            <button
              key={m.id}
              type="button"
              onClick={() => setMode(m.id)}
              className={cx(
                'inline-flex items-center gap-2 rounded-lg px-4 py-2 text-sm font-medium transition-colors',
                mode === m.id ? 'bg-white text-slate-900 shadow-sm' : 'text-slate-600',
              )}
            >
              <m.icon className="w-4 h-4" />
              {m.label}
            </button>
          ))}
        </div>

        {error && (
          <div className="flex items-start gap-3 rounded-xl border border-red-200 bg-red-50 px-4 py-3">
            <AlertCircle className="w-5 h-5 text-red-500 shrink-0 mt-0.5" />
            <p className="text-sm text-red-800 flex-1">{error}</p>
            <button type="button" onClick={() => setError(null)} aria-label="Dismiss">
              <X className="w-4 h-4 text-red-400 hover:text-red-600" />
            </button>
          </div>
        )}

        {booting ? (
          <div className="flex items-center gap-3 text-slate-500 py-20 justify-center">
            <Loader2 className="w-5 h-5 animate-spin" />
            Connecting to the photo service…
          </div>
        ) : (
          <div className="grid lg:grid-cols-12 gap-6 items-start">
            <div className="lg:col-span-5 space-y-6">
              {mode === 'single' ? (
                <Card title="Your photo" icon={ScanFace}>
                  {!file ? (
                    <UploadZone onFiles={chooseFile} />
                  ) : (
                    <div className="space-y-4">
                      <div className="rounded-xl overflow-hidden border border-slate-200 bg-slate-50">
                        <img
                          src={originalUrl}
                          alt="Your original"
                          className="w-full max-h-72 object-contain"
                        />
                      </div>
                      <div className="flex flex-wrap gap-2">
                        <Button
                          onClick={runEnhance}
                          busy={working === 'enhance'}
                          disabled={busy}
                          icon={Sparkles}
                          className="flex-1"
                        >
                          {working === 'enhance' ? 'Working…' : 'Fix and check'}
                        </Button>
                        <Button
                          variant="outline"
                          onClick={runAnalyse}
                          busy={working === 'analyse'}
                          disabled={busy}
                          icon={ClipboardCheck}
                        >
                          Check only
                        </Button>
                      </div>
                      <p className="text-xs text-slate-500">
                        “Check only” measures your photo and changes nothing — useful when a
                        service insists on an untouched original.
                      </p>
                    </div>
                  )}
                </Card>
              ) : (
                <Card title="Batch" icon={Layers}>
                  <BatchPanel
                    options={options}
                    specId={specId}
                    size={sizeArgs}
                    maxBatch={catalogue?.limits?.max_batch || 20}
                    onError={setError}
                  />
                </Card>
              )}

              <Card title="Output" icon={Settings2}>
                <OptionsPanel
                  specs={specs}
                  specId={specId}
                  onSpecId={(id) => {
                    setSpecId(id)
                    const next = specs.find((s) => s.id === id)
                    if (next) {
                      setSize({ width: next.width_px, height: next.height_px })
                      setOptions((o) => ({ ...o, background: rgbToHex(next.background) }))
                    }
                  }}
                  size={size}
                  onSize={setSize}
                  options={options}
                  onOptions={setOptions}
                  disabled={busy}
                />
              </Card>
            </div>

            <div className="lg:col-span-7 space-y-6">
              {mode === 'batch' ? (
                <Card title="How batch works" icon={Layers}>
                  <p className="text-sm text-slate-600">
                    Every photo runs through the same pipeline and the same rule set as a single
                    upload, with the output settings on the left. You get one ZIP back containing
                    the processed images, a <code className="text-xs">reports.json</code> with the
                    full rule-by-rule result for each photo, and a{' '}
                    <code className="text-xs">summary.csv</code> listing the score, verdict and any
                    failures at a glance.
                  </p>
                  <p className="text-sm text-slate-600 mt-3">
                    A photo that cannot be processed — no face found, or a corrupt file — is
                    recorded as an error in the reports rather than stopping the batch.
                  </p>
                </Card>
              ) : result ? (
                <>
                  <Card title="Result" icon={Sparkles}>
                    <ResultView
                      result={result}
                      originalUrl={originalUrl}
                      papers={papers}
                      spec={spec}
                    />
                  </Card>
                  <Card title="Compliance report" icon={ClipboardCheck}>
                    <ComplianceReport report={result.report} fixes={result.report.fixes_applied} />
                  </Card>
                </>
              ) : shownReport ? (
                <Card
                  title="Compliance report"
                  icon={ClipboardCheck}
                  actions={
                    <span className="text-xs text-slate-400">Your original, unmodified</span>
                  }
                >
                  <ComplianceReport report={shownReport} />
                </Card>
              ) : (
                <Card bodyClassName="p-5 h-full">
                  <Empty icon={ScanFace} title="Nothing to show yet">
                    Add a photo and we will measure it against every rule in the standard, fix
                    what can be fixed, and tell you plainly about anything that needs a retake.
                  </Empty>
                </Card>
              )}
            </div>
          </div>
        )}

        <Card title="Before you take the photo" icon={Camera}>
          <Guidelines />
        </Card>
      </main>

      <footer className="max-w-7xl mx-auto px-4 pb-10 text-center text-xs text-slate-400">
        Geometry, background, lighting, colour and focus are corrected automatically. Expression,
        eyes, headwear and glare are reported but never faked.
      </footer>
    </div>
  )
}
