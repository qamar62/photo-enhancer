import { useRef, useState } from 'react'
import { ImagePlus, Layers } from 'lucide-react'
import { cx } from './ui'

/**
 * Drop target and file picker, shared by the single and batch flows.
 *
 * `onFiles` always receives an array, even in single mode, so the caller has
 * one shape to handle. Files that are not images are dropped silently rather
 * than raising - a folder drag routinely includes a .DS_Store, and refusing the
 * whole drop over one is worse than quietly ignoring it.
 */
export default function UploadZone({ multiple = false, maxFiles, onFiles, disabled }) {
  const inputRef = useRef(null)
  const [dragging, setDragging] = useState(false)

  const accept = (list) => {
    const images = [...list].filter((f) => f.type.startsWith('image/'))
    if (!images.length) return
    onFiles(multiple ? images.slice(0, maxFiles || images.length) : [images[0]])
  }

  return (
    <div
      role="button"
      tabIndex={disabled ? -1 : 0}
      aria-disabled={disabled}
      onClick={() => !disabled && inputRef.current?.click()}
      onKeyDown={(e) => {
        if (!disabled && (e.key === 'Enter' || e.key === ' ')) {
          e.preventDefault()
          inputRef.current?.click()
        }
      }}
      onDragOver={(e) => {
        e.preventDefault()
        if (!disabled) setDragging(true)
      }}
      onDragLeave={() => setDragging(false)}
      onDrop={(e) => {
        e.preventDefault()
        setDragging(false)
        if (!disabled) accept(e.dataTransfer.files)
      }}
      className={cx(
        'rounded-xl border-2 border-dashed px-6 py-12 text-center transition-colors',
        'focus:outline-none focus-visible:ring-2 focus-visible:ring-ring',
        disabled
          ? 'border-slate-200 opacity-50 cursor-not-allowed'
          : 'cursor-pointer hover:border-primary hover:bg-blue-50/60',
        dragging ? 'border-primary bg-blue-50' : 'border-slate-300',
      )}
    >
      {multiple ? (
        <Layers className="w-12 h-12 mx-auto mb-3 text-slate-400" />
      ) : (
        <ImagePlus className="w-12 h-12 mx-auto mb-3 text-slate-400" />
      )}
      <p className="font-medium text-slate-700">
        {multiple ? 'Drop photos here, or click to browse' : 'Drop a photo here, or click to browse'}
      </p>
      <p className="text-sm text-slate-500 mt-1">
        JPG, PNG or WebP{multiple && maxFiles ? ` · up to ${maxFiles} at a time` : ''}
      </p>
      <input
        ref={inputRef}
        type="file"
        accept="image/*"
        multiple={multiple}
        className="hidden"
        onChange={(e) => {
          accept(e.target.files)
          // Reset so picking the same file twice in a row still fires onChange.
          e.target.value = ''
        }}
      />
    </div>
  )
}
