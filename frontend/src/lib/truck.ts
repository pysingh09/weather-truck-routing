import type { Checkpoint, Position } from './types'

/**
 * Where is the truck `t` ms after the epoch? Interpolates between checkpoints by ETA
 * (linear along the straight chord between consecutive checkpoints; checkpoints are dense
 * enough that this stays visually on the road). Returns null before departure / after arrival.
 */
export function truckPosition(checkpoints: Checkpoint[], tMs: number): Position | null {
  if (checkpoints.length < 2) return null
  const first = Date.parse(checkpoints[0].eta)
  const last = Date.parse(checkpoints[checkpoints.length - 1].eta)
  if (tMs < first || tMs > last) return null
  for (let i = 1; i < checkpoints.length; i++) {
    const a = checkpoints[i - 1]
    const b = checkpoints[i]
    const ta = Date.parse(a.eta)
    const tb = Date.parse(b.eta)
    if (tMs <= tb) {
      const f = tb === ta ? 0 : (tMs - ta) / (tb - ta)
      return [a.lon + (b.lon - a.lon) * f, a.lat + (b.lat - a.lat) * f]
    }
  }
  return null
}
