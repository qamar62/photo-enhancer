const RULES = [
  {
    title: 'Framing',
    body: 'A close-up of your head and the top of your shoulders, so your face fills 70–80% of the height.',
  },
  {
    title: 'Pose',
    body: 'Face the camera square on, with your head straight rather than tilted or turned.',
  },
  {
    title: 'Expression',
    body: 'Neutral, with your mouth closed — no grin, no visible teeth.',
  },
  {
    title: 'Eyes',
    body: 'Open and clearly visible, looking at the lens, with no hair or shadow across them.',
  },
  {
    title: 'Glasses and headwear',
    body: 'No hats or caps. Glasses only if the lenses are clear, untinted and free of glare.',
  },
  {
    title: 'Lighting',
    body: 'Even light on your face, no hard shadows on your skin or behind you, no flash reflection.',
  },
  {
    title: 'Background',
    body: 'Plain and light — a cream or pale grey wall works. We can replace it, but a clean start reads better.',
  },
  {
    title: 'Quality',
    body: 'Sharp, in focus, in colour, with no filters. The bigger the original, the better the result.',
  },
]

/**
 * What the camera has to get right.
 *
 * Deliberately phrased as things to do while taking the photo rather than as a
 * list of what we fix afterwards - the half of the standard that cannot be
 * automated is the half worth reading before the shutter fires.
 */
export default function Guidelines() {
  return (
    <div className="grid sm:grid-cols-2 lg:grid-cols-4 gap-x-6 gap-y-5">
      {RULES.map((rule) => (
        <div key={rule.title}>
          <h4 className="text-sm font-semibold text-slate-900">{rule.title}</h4>
          <p className="text-sm text-slate-600 mt-1">{rule.body}</p>
        </div>
      ))}
    </div>
  )
}
