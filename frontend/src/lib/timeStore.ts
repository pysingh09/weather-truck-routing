import { useSyncExternalStore } from 'react'

/**
 * Tiny external store for the heatmap time cursor. Slider/play state lives here (not in React
 * state of the App) so scrubbing never re-renders the map layers: map effects subscribe
 * directly and call map.setPaintProperty.
 */
export interface TimeState { hour: number; playing: boolean; visible: boolean }

export const MAX_HOUR = 48
export const PLAY_SPEED_H_PER_S = 4

let state: TimeState = { hour: 0, playing: false, visible: true }
const listeners = new Set<() => void>()
let raf = 0
let last = 0

function emit() { listeners.forEach((l) => l()) }
export function getTime(): TimeState { return state }
export function subscribeTime(l: () => void): () => void {
  listeners.add(l)
  return () => { listeners.delete(l) }
}
export function setTime(patch: Partial<TimeState>) {
  state = { ...state, ...patch }
  emit()
}

function tick(now: number) {
  const dt = (now - last) / 1000
  last = now
  let h = state.hour + dt * PLAY_SPEED_H_PER_S
  if (h > MAX_HOUR) h = 0
  state = { ...state, hour: h }
  emit()
  if (state.playing) raf = requestAnimationFrame(tick)
}

export function setPlaying(playing: boolean) {
  cancelAnimationFrame(raf)
  setTime({ playing })
  if (playing) {
    last = performance.now()
    raf = requestAnimationFrame(tick)
  }
}

export function useTime(): TimeState {
  return useSyncExternalStore(subscribeTime, getTime)
}
