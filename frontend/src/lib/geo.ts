import type { Position, Route } from './types'

export function routeBounds(route: Route): [Position, Position] {
  let minX = 180, minY = 90, maxX = -180, maxY = -90
  for (const [x, y] of route.geometry.coordinates) {
    if (x < minX) minX = x
    if (x > maxX) maxX = x
    if (y < minY) minY = y
    if (y > maxY) maxY = y
  }
  return [[minX, minY], [maxX, maxY]]
}
