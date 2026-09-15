/**
 * The handful of primitives every panel repeats. Small on purpose: this is a
 * styling layer over plain elements, not a component library - anything that
 * needs real behaviour lives in its own file.
 */
import { Loader2 } from 'lucide-react'

export function cx(...parts) {
  return parts.filter(Boolean).join(' ')
}

export function Card({ title, icon: Icon, actions, className, bodyClassName, children }) {
  return (
    <section
      className={cx(
        'bg-white rounded-2xl border border-slate-200 shadow-sm overflow-hidden',
        className,
      )}
    >
      {title && (
        <header className="flex items-center gap-3 px-5 py-4 border-b border-slate-100">
          {Icon && <Icon className="w-5 h-5 text-primary shrink-0" />}
          <h2 className="font-semibold text-slate-900">{title}</h2>
          {actions && <div className="ml-auto flex items-center gap-2">{actions}</div>}
        </header>
      )}
      <div className={cx('p-5', bodyClassName)}>{children}</div>
    </section>
  )
}

const VARIANTS = {
  primary: 'bg-primary text-white hover:bg-blue-700 disabled:hover:bg-primary',
  success: 'bg-emerald-600 text-white hover:bg-emerald-700 disabled:hover:bg-emerald-600',
  ghost: 'bg-slate-100 text-slate-700 hover:bg-slate-200 disabled:hover:bg-slate-100',
  outline:
    'bg-white text-slate-700 border border-slate-300 hover:bg-slate-50 disabled:hover:bg-white',
}

export function Button({
  variant = 'primary',
  busy = false,
  icon: Icon,
  className,
  children,
  disabled,
  ...rest
}) {
  return (
    <button
      {...rest}
      disabled={disabled || busy}
      className={cx(
        'inline-flex items-center justify-center gap-2 rounded-lg px-4 py-2.5 text-sm font-medium',
        'transition-colors focus:outline-none focus-visible:ring-2 focus-visible:ring-ring focus-visible:ring-offset-2',
        'disabled:opacity-50 disabled:cursor-not-allowed',
        VARIANTS[variant],
        className,
      )}
    >
      {busy ? <Loader2 className="w-4 h-4 animate-spin" /> : Icon && <Icon className="w-4 h-4" />}
      {children}
    </button>
  )
}

/** A checkbox that reads as a setting rather than a form field. */
export function Toggle({ checked, onChange, label, hint, disabled }) {
  return (
    <label
      className={cx(
        'flex items-start gap-3 rounded-lg px-3 py-2.5 cursor-pointer select-none',
        disabled ? 'opacity-50 cursor-not-allowed' : 'hover:bg-slate-50',
      )}
    >
      <input
        type="checkbox"
        checked={checked}
        disabled={disabled}
        onChange={(e) => onChange(e.target.checked)}
        className="mt-0.5 w-4 h-4 rounded border-slate-300 text-primary focus:ring-ring"
      />
      <span className="min-w-0">
        <span className="block text-sm font-medium text-slate-800">{label}</span>
        {hint && <span className="block text-xs text-slate-500 mt-0.5">{hint}</span>}
      </span>
    </label>
  )
}

export function Field({ label, hint, children, className }) {
  return (
    <label className={cx('block', className)}>
      <span className="block text-xs font-medium uppercase tracking-wide text-slate-500 mb-1.5">
        {label}
      </span>
      {children}
      {hint && <span className="block text-xs text-slate-500 mt-1">{hint}</span>}
    </label>
  )
}

export const inputClass =
  'w-full px-3 py-2 rounded-lg border border-slate-300 text-sm text-slate-800 bg-white ' +
  'focus:outline-none focus:ring-2 focus:ring-ring focus:border-transparent'

export function Pill({ className, children }) {
  return (
    <span
      className={cx(
        'inline-flex items-center gap-1 rounded-full border px-2 py-0.5 text-xs font-medium',
        className,
      )}
    >
      {children}
    </span>
  )
}

export function Empty({ icon: Icon, title, children }) {
  return (
    <div className="flex flex-col items-center justify-center text-center rounded-xl border-2 border-dashed border-slate-200 px-6 py-12 h-full">
      {Icon && <Icon className="w-12 h-12 text-slate-300 mb-3" />}
      <p className="font-medium text-slate-600">{title}</p>
      {children && <p className="text-sm text-slate-400 mt-1 max-w-xs">{children}</p>}
    </div>
  )
}
