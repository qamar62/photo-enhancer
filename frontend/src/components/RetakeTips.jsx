import { Camera, CheckCircle2 } from 'lucide-react'

/**
 * The things no amount of processing can repair.
 *
 * Closed eyes, an open mouth, a hat, glare on glasses or a second face in the
 * frame are all properties of the moment the shutter fired. Saying so plainly -
 * and early - is more useful than burying them among thirty rules that passed.
 */
export default function RetakeTips({ reasons = [], blocking }) {
  if (!reasons.length) {
    if (!blocking) return null
    return (
      <div className="rounded-xl border border-amber-200 bg-amber-50 p-3 text-sm text-amber-900">
        Some rules are outside the allowed range. Look through the list below before you submit
        this photo.
      </div>
    )
  }

  return (
    <div className="rounded-xl border border-red-200 bg-red-50 p-4">
      <p className="flex items-center gap-2 font-medium text-red-900">
        <Camera className="w-4 h-4" />
        Please take another photo
      </p>
      <p className="text-xs text-red-700/80 mt-1">
        {reasons.length === 1 ? 'This is something' : 'These are things'} we cannot fix after the
        fact.
      </p>
      <ul className="mt-3 space-y-2.5">
        {reasons.map((reason) => (
          <li key={reason.id} className="flex gap-2.5">
            <CheckCircle2 className="w-4 h-4 text-red-400 mt-0.5 shrink-0" />
            <div className="min-w-0">
              <p className="text-sm font-medium text-red-900">{reason.label}</p>
              {reason.tip && <p className="text-xs text-red-700/90 mt-0.5">{reason.tip}</p>}
            </div>
          </li>
        ))}
      </ul>
    </div>
  )
}
