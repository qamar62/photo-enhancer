import { useState } from 'react'
import { ChevronDown, Ruler } from 'lucide-react'
import { Field, Toggle, inputClass, cx } from './ui'
import { describeSpec } from '../lib/report'

/**
 * Output size and the switches that decide how much the pipeline is allowed to
 * change. Specs come from the API rather than being hard-coded here, so adding
 * a country on the server shows up in the UI without a frontend release.
 */
export default function OptionsPanel({
  specs,
  specId,
  onSpecId,
  size,
  onSize,
  options,
  onOptions,
  disabled,
}) {
  const [advanced, setAdvanced] = useState(false)
  const spec = specs.find((s) => s.id === specId)
  const set = (patch) => onOptions({ ...options, ...patch })

  return (
    <div className="space-y-5">
      <div>
        <span className="block text-xs font-medium uppercase tracking-wide text-slate-500 mb-2">
          Photo standard
        </span>
        <div className="grid sm:grid-cols-2 gap-2">
          {specs.map((s) => (
            <button
              key={s.id}
              type="button"
              disabled={disabled}
              onClick={() => onSpecId(s.id)}
              className={cx(
                'text-left rounded-lg border px-3 py-2.5 transition-colors disabled:opacity-50',
                s.id === specId
                  ? 'border-primary bg-blue-50 ring-1 ring-primary'
                  : 'border-slate-200 hover:border-slate-300 hover:bg-slate-50',
              )}
            >
              <span className="block text-sm font-medium text-slate-800">{s.name}</span>
              <span className="block text-xs text-slate-500 mt-0.5">{describeSpec(s)}</span>
            </button>
          ))}
        </div>
        {spec?.description && (
          <p className="text-xs text-slate-500 mt-2 flex items-start gap-1.5">
            <Ruler className="w-3.5 h-3.5 mt-px shrink-0" />
            {spec.description}
          </p>
        )}
      </div>

      {/* Only a pure-pixel spec takes a custom size. Letting someone retype the
          pixels of a 35x45 mm spec would silently break the physical size the
          whole point of that spec is to guarantee. */}
      {spec && !spec.physical && (
        <div className="grid grid-cols-2 gap-3">
          <Field label="Width (px)">
            <input
              type="number"
              min={100}
              max={6000}
              disabled={disabled}
              value={size.width}
              onChange={(e) => onSize({ ...size, width: Number(e.target.value) || 0 })}
              className={inputClass}
            />
          </Field>
          <Field label="Height (px)">
            <input
              type="number"
              min={100}
              max={6000}
              disabled={disabled}
              value={size.height}
              onChange={(e) => onSize({ ...size, height: Number(e.target.value) || 0 })}
              className={inputClass}
            />
          </Field>
          <div className="col-span-2 flex flex-wrap gap-2">
            {[
              ['1200 × 1600', 1200, 1600],
              ['600 × 600', 600, 600],
              ['2000 × 2000', 2000, 2000],
            ].map(([label, w, h]) => (
              <button
                key={label}
                type="button"
                disabled={disabled}
                onClick={() => onSize({ width: w, height: h })}
                className="px-2.5 py-1 text-xs rounded-md bg-slate-100 text-slate-600 hover:bg-slate-200 disabled:opacity-50"
              >
                {label}
              </button>
            ))}
          </div>
        </div>
      )}

      <div className="space-y-1 -mx-3">
        <Toggle
          disabled={disabled}
          checked={options.removeBackground}
          onChange={(v) => set({ removeBackground: v })}
          label="Replace the background"
          hint="Cuts out the subject and lays them on a plain, light backdrop."
        />
        {options.removeBackground && (
          <div className="px-3 pb-2 flex items-center gap-3">
            <input
              type="color"
              disabled={disabled}
              value={options.background}
              onChange={(e) => set({ background: e.target.value })}
              className="h-9 w-14 rounded border border-slate-300 cursor-pointer disabled:opacity-50"
              aria-label="Background colour"
            />
            <input
              type="text"
              disabled={disabled}
              value={options.background}
              onChange={(e) => set({ background: e.target.value })}
              className={cx(inputClass, 'flex-1 font-mono')}
              placeholder="#FAFAFA"
            />
          </div>
        )}
        <Toggle
          disabled={disabled}
          checked={options.autoFrame}
          onChange={(v) => set({ autoFrame: v })}
          label="Re-frame to the standard"
          hint="Straightens the head and crops so the face and eye line land where the rules want them."
        />
      </div>

      <div>
        <button
          type="button"
          onClick={() => setAdvanced((v) => !v)}
          className="flex items-center gap-1.5 text-sm font-medium text-slate-600 hover:text-slate-900"
        >
          <ChevronDown className={cx('w-4 h-4 transition-transform', advanced && 'rotate-180')} />
          Advanced
        </button>
        {advanced && (
          <div className="mt-2 space-y-1 -mx-3">
            <Toggle
              disabled={disabled}
              checked={options.autoEnhance}
              onChange={(v) => set({ autoEnhance: v })}
              label="Correct exposure and colour"
              hint="Neutralises colour casts, evens the lighting and fixes brightness."
            />
            <Toggle
              disabled={disabled}
              checked={options.fixRedEye}
              onChange={(v) => set({ fixRedEye: v })}
              label="Remove red eye"
            />
            <Toggle
              disabled={disabled}
              checked={options.sharpen}
              onChange={(v) => set({ sharpen: v })}
              label="Sharpen"
              hint="Gentle, and only when the focus measurement says it will help."
            />
            <div className="px-3 pt-2">
              <Field label="File format" hint="PNG is lossless but much larger; most services want JPEG.">
                <select
                  disabled={disabled}
                  value={options.format}
                  onChange={(e) => set({ format: e.target.value })}
                  className={inputClass}
                >
                  <option value="jpeg">JPEG</option>
                  <option value="png">PNG</option>
                </select>
              </Field>
            </div>
          </div>
        )}
      </div>
    </div>
  )
}
