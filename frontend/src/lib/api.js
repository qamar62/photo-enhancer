/**
 * The one place that knows what the backend looks like.
 *
 * Paths are absolute from /api/v1 because that is where the routes are mounted
 * on the server as well - in production nginx forwards the prefix untouched, so
 * the same string works in both environments and only the origin changes.
 */
import axios from 'axios'

export const API_BASE =
  import.meta.env.VITE_API_URL ?? (import.meta.env.PROD ? '' : 'http://localhost:8000')

const V1 = `${API_BASE}/api/v1`

/**
 * FastAPI puts its message in `detail`, but a request made with
 * responseType:'blob' gets its *error* body as a Blob too, so the JSON has to
 * be read back out of it before there is anything to show the user. Without
 * this every failed download would read "Request failed with status code 400".
 */
async function explain(error, fallback) {
  const data = error?.response?.data
  if (data instanceof Blob) {
    try {
      const parsed = JSON.parse(await data.text())
      if (parsed?.detail) return parsed.detail
    } catch {
      /* not JSON - fall through */
    }
  }
  if (typeof data === 'string' && data) return data
  if (data?.detail) return data.detail
  if (error?.code === 'ERR_NETWORK') {
    return 'Cannot reach the photo service. Is the backend running?'
  }
  return error?.message || fallback
}

export class ApiError extends Error {
  constructor(message, status) {
    super(message)
    this.name = 'ApiError'
    this.status = status
  }
}

async function call(fn, fallback) {
  try {
    return await fn()
  } catch (error) {
    throw new ApiError(await explain(error, fallback), error?.response?.status)
  }
}

/**
 * Turn the UI's option state into the multipart fields the API expects.
 * Booleans have to go over as "true"/"false" strings: FormData stringifies
 * everything anyway, and Python's bool parser reads "false" as false but would
 * read a raw `false` object as the string "[object Object]", i.e. true.
 */
function appendOptions(form, options = {}) {
  const {
    specId,
    width,
    height,
    removeBackground = true,
    background,
    autoFrame = true,
    autoEnhance = true,
    fixRedEye = true,
    sharpen = true,
    format = 'jpeg',
    quality,
  } = options

  if (specId) form.append('spec', specId)
  if (width) form.append('width', String(Math.round(width)))
  if (height) form.append('height', String(Math.round(height)))
  form.append('remove_background', removeBackground ? 'true' : 'false')
  if (background) form.append('background', background)
  form.append('auto_frame', autoFrame ? 'true' : 'false')
  form.append('auto_enhance', autoEnhance ? 'true' : 'false')
  form.append('fix_red_eye', fixRedEye ? 'true' : 'false')
  form.append('sharpen', sharpen ? 'true' : 'false')
  form.append('format', format)
  if (quality) form.append('quality', String(quality))
  return form
}

/** Specs, papers, category labels and upload limits - fetched once on boot. */
export function getSpecs() {
  return call(async () => (await axios.get(`${V1}/specs`)).data, 'Could not load photo specifications.')
}

/** Measure a photo without changing it. Returns a report with no `fixes_applied`. */
export function analyse(file, { specId, width, height } = {}) {
  const form = new FormData()
  form.append('file', file)
  if (specId) form.append('spec', specId)
  if (width) form.append('width', String(Math.round(width)))
  if (height) form.append('height', String(Math.round(height)))
  return call(
    async () => (await axios.post(`${V1}/analyse`, form)).data,
    'Could not check that photo.',
  )
}

/** Fix and re-frame one photo. Returns { image (data URL), mime, filename, bytes, report }. */
export function enhance(file, options, { signal } = {}) {
  const form = appendOptions(new FormData(), options)
  form.append('file', file)
  return call(
    async () => (await axios.post(`${V1}/process`, form, { signal })).data,
    'Could not process that photo.',
  )
}

/**
 * Process many photos at once. The ZIP holds the images plus reports.json and
 * summary.csv; the tally comes back in headers so the UI can summarise the
 * result without unzipping it in the browser.
 */
export function batch(files, options, { signal, onProgress } = {}) {
  const form = appendOptions(new FormData(), options)
  files.forEach((file) => form.append('files', file))
  return call(async () => {
    const response = await axios.post(`${V1}/batch`, form, {
      responseType: 'blob',
      signal,
      onUploadProgress: (event) => {
        if (onProgress && event.total) onProgress(event.loaded / event.total)
      },
    })
    return {
      blob: response.data,
      total: Number(response.headers['x-batch-total'] || files.length),
      compliant: Number(response.headers['x-batch-compliant'] || 0),
    }
  }, 'Could not process that batch.')
}

/**
 * Tile a photo onto printable paper.
 *
 * Pass the already-enhanced image with alreadyProcessed:true - re-running the
 * pipeline on an output that is already cropped to the head would crop it
 * again, and the second pass has nothing left to work with.
 */
export function printSheet(file, { specId, paper, dpi = 300, cutGuides = true, alreadyProcessed = true } = {}) {
  const form = new FormData()
  form.append('file', file)
  if (specId) form.append('spec', specId)
  if (paper) form.append('paper', paper)
  form.append('dpi', String(dpi))
  form.append('cut_guides', cutGuides ? 'true' : 'false')
  form.append('already_processed', alreadyProcessed ? 'true' : 'false')
  return call(async () => {
    const response = await axios.post(`${V1}/sheet`, form, { responseType: 'blob' })
    let info = null
    try {
      info = JSON.parse(response.headers['x-sheet-info'] || 'null')
    } catch {
      info = null
    }
    return { blob: response.data, info }
  }, 'Could not build the print sheet.')
}
