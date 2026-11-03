import { useEffect } from 'react'
import { useMap } from 'react-map-gl/maplibre'
import type { GeoJSONSource } from 'maplibre-gl'
import { getTime, subscribeTime } from '../lib/timeStore'
import { heatWeightExpression } from '../lib/geojson'
import { truckPosition } from '../lib/truck'
import type { Checkpoint } from '../lib/types'

/**
 * Renders nothing. Bridges the time store to the map imperatively so slider moves and playback
 * only call setPaintProperty / setData on a 1-point source — React never re-renders layers.
 */
export default function MapEffects({ hasHeat, startIso, truckCheckpoints }: { hasHeat: boolean; startIso: string; truckCheckpoints: Checkpoint[] | null }) {
  const { current: ref } = useMap()

  useEffect(() => {
    const map = ref?.getMap()
    if (!map) return
    const startMs = Date.parse(startIso)
    let lastKey = ''
    const apply = () => {
      const { hour, visible } = getTime()
      if (hasHeat && map.getLayer('heat')) {
        map.setPaintProperty('heat', 'heatmap-weight', heatWeightExpression(hour) as never)
        map.setLayoutProperty('heat', 'visibility', visible ? 'visible' : 'none')
      }
      const src = map.getSource('truck') as GeoJSONSource | undefined
      if (src) {
        const pos = truckCheckpoints ? truckPosition(truckCheckpoints, startMs + hour * 3600_000) : null
        const key = pos ? pos.join(',') : ''
        if (key !== lastKey) {
          lastKey = key
          src.setData({
            type: 'FeatureCollection',
            features: pos ? [{ type: 'Feature', properties: {}, geometry: { type: 'Point', coordinates: pos } }] : [],
          })
        }
      }
    }
    apply()
    const unsub = subscribeTime(apply)
    map.on('styledata', apply)
    return () => {
      unsub()
      map.off('styledata', apply)
    }
  }, [ref, hasHeat, startIso, truckCheckpoints])

  return null
}
