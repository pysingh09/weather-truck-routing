import { useCallback, useEffect, useMemo, useRef, useState } from 'react'
import Map, { Layer, Marker, Popup, Source } from 'react-map-gl/maplibre'
import type { MapLayerMouseEvent, MapRef } from 'react-map-gl/maplibre'
import type { ExpressionSpecification, LineLayerSpecification, CircleLayerSpecification } from 'maplibre-gl'
import type { FeatureCollection } from 'geojson'
import MapEffects from './MapEffects'
import { buildCheckpointsGeoJSON, buildHeatmapGeoJSON, buildSegmentsGeoJSON, heatWeightExpression } from '../lib/geojson'
import { routeBounds } from '../lib/geo'
import { formatLocalTime } from '../lib/format'
import { getTime } from '../lib/timeStore'
import { riskColor, riskLabel, riskMatchExpression } from '../lib/risk-colors'
import type { HeatmapResponse, PlanResponse, Route } from '../lib/types'

const STYLE = 'https://tiles.openfreemap.org/styles/positron'
const EMPTY: FeatureCollection = { type: 'FeatureCollection', features: [] }
const expr = (e: unknown) => e as ExpressionSpecification
const isSel = (id: string) => expr(['==', ['get', 'routeId'], id])

const HEAT_COLOR = expr([
  'interpolate', ['linear'], ['heatmap-density'],
  0, 'rgba(34,197,94,0)', 0.12, 'rgba(34,197,94,0.45)', 0.3, 'rgba(234,179,8,0.6)',
  0.5, 'rgba(249,115,22,0.68)', 0.72, 'rgba(220,38,38,0.75)', 1, 'rgba(126,34,206,0.85)',
])
const HEAT_RADIUS = expr(['interpolate', ['linear'], ['zoom'], 3, 28, 5, 55, 7, 110, 9, 220])

interface Props {
  plan: PlanResponse | null
  selectedId: string
  onSelect: (id: string) => void
  heatmap: HeatmapResponse | undefined
  startIso: string
}

export default function MapView({ plan, selectedId, onSelect, heatmap, startIso }: Props) {
  const mapRef = useRef<MapRef>(null)
  // Heatmap sits under the basemap's labels (first symbol layer) so place names stay readable.
  const [labelLayerId, setLabelLayerId] = useState<string | undefined>()
  const onLoad = useCallback(() => {
    const layers = mapRef.current?.getMap().getStyle().layers ?? []
    setLabelLayerId(layers.find((l) => l.type === 'symbol')?.id)
  }, [])
  const [popup, setPopup] = useState<{ plan: PlanResponse | null; routeId: string; idx: number } | null>(null)

  // Sources are built once per response — selection never rebuilds data.
  const segments = useMemo(() => (plan ? buildSegmentsGeoJSON(plan) : EMPTY), [plan])
  const checkpoints = useMemo(() => (plan ? buildCheckpointsGeoJSON(plan) : EMPTY), [plan])
  const heatData = useMemo(() => (heatmap ? buildHeatmapGeoJSON(heatmap) : null), [heatmap])
  const [initialHeatPaint] = useState(() => ({
    'heatmap-weight': expr(heatWeightExpression(getTime().hour)),
    'heatmap-color': HEAT_COLOR,
    'heatmap-radius': HEAT_RADIUS,
    'heatmap-intensity': 1,
    'heatmap-opacity': 0.8,
  }))

  const selected: Route | undefined = plan?.routes.find((r) => r.id === selectedId)
  const recommended = plan?.routes.find((r) => r.id === plan.recommended_route_id)

  useEffect(() => {
    if (!selected) return
    const mobile = window.innerWidth < 768
    mapRef.current?.fitBounds(routeBounds(selected), {
      padding: mobile
        ? { top: 130, bottom: Math.round(window.innerHeight * 0.52), left: 30, right: 30 }
        : { top: 70, bottom: 140, left: 60, right: 60 },
      duration: 900,
    })
  }, [selected])

  const lineCasing = useMemo<LineLayerSpecification['paint']>(() => ({
    'line-color': '#ffffff',
    'line-width': expr(['case', isSel(selectedId), 9, 5]),
    'line-opacity': expr(['case', isSel(selectedId), 1, 0.35]),
  }), [selectedId])
  const lineLayout = useMemo<LineLayerSpecification['layout']>(() => ({
    'line-cap': 'round', 'line-join': 'round',
    'line-sort-key': expr(['case', isSel(selectedId), 1, 0]),
  }), [selectedId])
  const linePaint = useMemo<LineLayerSpecification['paint']>(() => ({
    'line-color': riskMatchExpression('level'),
    'line-width': expr(['case', isSel(selectedId), 6, 3]),
    'line-opacity': expr(['case', isSel(selectedId), 1, 0.35]),
  }), [selectedId])
  const cpFilter = useMemo(() => expr(['==', ['get', 'routeId'], selectedId]), [selectedId])
  const cpPaint = useMemo<CircleLayerSpecification['paint']>(() => ({
    'circle-color': riskMatchExpression('level'),
    'circle-radius': expr(['interpolate', ['linear'], ['zoom'], 3, 3.5, 8, 6, 12, 8]),
    'circle-stroke-color': '#ffffff',
    'circle-stroke-width': 1.5,
  }), [])

  const onClick = useCallback((e: MapLayerMouseEvent) => {
    const f = e.features?.[0]
    if (!f) { setPopup(null); return }
    if (f.layer.id === 'checkpoints') {
      setPopup({ plan, routeId: f.properties.routeId as string, idx: f.properties.idx as number })
    } else if (f.layer.id === 'route-lines') {
      onSelect(f.properties.routeId as string)
    }
  }, [onSelect, plan])

  const popupCp = popup && popup.plan === plan && popup.routeId === selectedId ? plan?.routes.find((r) => r.id === popup.routeId)?.checkpoints[popup.idx] : undefined
  const setCursor = (c: string) => { const m = mapRef.current?.getMap(); if (m) m.getCanvas().style.cursor = c }

  return (
    <Map
      ref={mapRef}
      mapStyle={STYLE}
      initialViewState={{ longitude: -96, latitude: 39, zoom: 3.6 }}
      interactiveLayerIds={plan ? ['route-lines', 'checkpoints'] : []}
      onClick={onClick}
      onLoad={onLoad}
      onMouseEnter={() => setCursor('pointer')}
      onMouseLeave={() => setCursor('')}
      style={{ width: '100%', height: '100%' }}
    >
      {heatData && (
        <Source id="heat" type="geojson" data={heatData}>
          <Layer id="heat" type="heatmap" beforeId={labelLayerId} paint={initialHeatPaint} />
        </Source>
      )}
      <Source id="routes" type="geojson" data={segments}>
        <Layer id="route-casing" type="line" layout={lineLayout} paint={lineCasing} />
        <Layer id="route-lines" type="line" layout={lineLayout} paint={linePaint} />
      </Source>
      <Source id="checkpoints" type="geojson" data={checkpoints}>
        <Layer id="checkpoints" type="circle" filter={cpFilter} paint={cpPaint} />
      </Source>
      <Source id="truck" type="geojson" data={EMPTY}>
        <Layer id="truck-halo" type="circle" paint={{ 'circle-radius': 13, 'circle-color': '#0f172a', 'circle-opacity': 0.25 }} />
        <Layer id="truck" type="circle" paint={{ 'circle-radius': 7, 'circle-color': '#0f172a', 'circle-stroke-color': '#fff', 'circle-stroke-width': 2.5 }} />
      </Source>

      {plan && selected && (
        <>
          <Marker longitude={selected.geometry.coordinates[0][0]} latitude={selected.geometry.coordinates[0][1]} anchor="center">
            <div title="Origin" className="h-4 w-4 rounded-full border-[3px] border-white bg-slate-900 shadow" />
          </Marker>
          <Marker longitude={selected.geometry.coordinates.at(-1)![0]} latitude={selected.geometry.coordinates.at(-1)![1]} anchor="center">
            <div title="Destination" className="h-4 w-4 rotate-45 border-[3px] border-white bg-slate-900 shadow" />
          </Marker>
        </>
      )}

      {popup && popupCp && (
        <Popup longitude={popupCp.lon} latitude={popupCp.lat} anchor="bottom" offset={10} closeOnClick={false} onClose={() => setPopup(null)} maxWidth="260px">
          <div className="text-sm">
            <div className="mb-1 flex items-center gap-2 font-semibold">
              <span className="inline-block h-3 w-3 rounded-full" style={{ background: riskColor(popupCp.level) }} />
              {riskLabel(popupCp.level)}
            </div>
            <dl className="grid grid-cols-[auto_1fr] gap-x-3 gap-y-0.5 text-xs text-slate-700">
              <dt className="text-slate-400">Mile</dt><dd>{popupCp.mile.toFixed(0)}</dd>
              <dt className="text-slate-400">ETA</dt><dd>{formatLocalTime(popupCp.eta)}</dd>
              <dt className="text-slate-400">Wind</dt><dd>{popupCp.weather.wind_mph.toFixed(0)} mph (gust {popupCp.weather.gust_mph.toFixed(0)})</dd>
              <dt className="text-slate-400">Rain</dt><dd>{popupCp.weather.rain_in_hr.toFixed(2)} in/hr</dd>
              <dt className="text-slate-400">Snow</dt><dd>{popupCp.weather.snow_in_hr.toFixed(2)} in/hr</dd>
            </dl>
            <p className="mt-1.5 text-xs text-slate-500">{popupCp.note}</p>
          </div>
        </Popup>
      )}

      <MapEffects hasHeat={!!heatData} startIso={startIso} truckCheckpoints={recommended?.checkpoints ?? null} />
    </Map>
  )
}
