// Generates src/mocks/geometries.json: three Chicago -> Denver LineStrings roughly following
// I-80 (A), I-80/I-76 (B) and I-74/I-70 (C). Run: pnpm gen:mocks
import { writeFileSync } from 'node:fs'

const routes = {
  r0: [[-87.63,41.88],[-88.08,41.52],[-89.1,41.35],[-90.58,41.52],[-91.53,41.66],[-93.62,41.59],[-95.94,41.26],[-96.7,40.81],[-98.34,40.92],[-99.08,40.7],[-100.77,41.14],[-101.72,41.13],[-102.98,41.14],[-104.82,41.14],[-105.08,40.58],[-104.99,39.74]],
  r1: [[-87.63,41.88],[-88.08,41.52],[-89.1,41.35],[-90.58,41.52],[-91.53,41.66],[-93.62,41.59],[-95.94,41.26],[-96.7,40.81],[-98.34,40.92],[-99.08,40.7],[-100.77,41.14],[-101.72,41.13],[-102.26,40.99],[-103.8,40.25],[-104.5,39.95],[-104.99,39.74]],
  r2: [[-87.63,41.88],[-88.9,40.9],[-89.59,40.69],[-91.4,40.1],[-92.6,39.8],[-94.58,39.1],[-97.6,38.84],[-99.33,38.88],[-101.05,39.39],[-103.69,39.26],[-104.99,39.74]],
}
const R = 3958.8
const rad = (d) => (d * Math.PI) / 180
function hav(a, b) {
  const dLat = rad(b[1] - a[1]), dLon = rad(b[0] - a[0])
  const h = Math.sin(dLat / 2) ** 2 + Math.cos(rad(a[1])) * Math.cos(rad(b[1])) * Math.sin(dLon / 2) ** 2
  return 2 * R * Math.asin(Math.sqrt(h))
}
const out = {}
let seed = 7
const rnd = () => ((seed = (seed * 16807) % 2147483647) / 2147483647) - 0.5
for (const [id, pts] of Object.entries(routes)) {
  const line = []
  for (let i = 1; i < pts.length; i++) {
    const a = pts[i - 1], b = pts[i]
    const n = Math.max(1, Math.round(hav(a, b) / 3))
    for (let k = 0; k < n; k++) {
      const f = k / n
      const wob = k === 0 ? 0 : 0.012 * Math.sin(f * Math.PI)
      line.push([+(a[0] + (b[0] - a[0]) * f + rnd() * wob).toFixed(4), +(a[1] + (b[1] - a[1]) * f + rnd() * wob).toFixed(4)])
    }
  }
  line.push(pts[pts.length - 1])
  out[id] = line
}
writeFileSync(new URL('../src/mocks/geometries.json', import.meta.url), JSON.stringify(out))
console.log(Object.fromEntries(Object.entries(out).map(([k, v]) => [k, v.length])))
