export type RiskLevel = 0 | 1 | 2 | 3 | 4

export interface Place { label: string; lon: number; lat: number }
export type Position = [number, number]
export interface LineStringGeometry { type: 'LineString'; coordinates: Position[] }

export interface PlanRequest {
  origin: Place
  destination: Place
  departure: string
  load_lb: number
  interval_mi: 10 | 25 | 50
}

export interface Weather { wind_mph: number; gust_mph: number; rain_in_hr: number; snow_in_hr: number }

export interface Checkpoint {
  idx: number
  mile: number
  lon: number
  lat: number
  eta: string
  weather: Weather
  level: RiskLevel
  levels: { wind: RiskLevel; rain: RiskLevel; snow: RiskLevel }
  driver: 'wind' | 'rain' | 'snow' | 'load'
  note: string
}

export interface Segment {
  from_idx: number
  to_idx: number
  level: RiskLevel
  miles: number
  coordinates: Position[]
}

export interface RouteSummary {
  miles_by_level: Record<string, number>
  severe_mi: number
  high_mi: number
  no_travel_mi: number
  avg_risk: number
  max_level: RiskLevel
  has_no_travel: boolean
}

export type RouteEngine = 'valhalla-truck' | 'osrm-car-truckspeed'

export interface Route {
  id: string
  engine: RouteEngine
  rank: number
  label: string
  distance_mi: number
  duration_s: number
  arrival: string
  geometry: LineStringGeometry
  summary: RouteSummary
  reason: string
  checkpoints: Checkpoint[]
  segments: Segment[]
}

export interface PlanResponse {
  recommended_route_id: string
  all_no_travel: boolean
  routes: Route[]
}

export interface HeatmapRequest { departure: string; route_geometries: LineStringGeometry[] }
export interface HeatmapPoint { lon: number; lat: number; risk: number[] }
export interface HeatmapResponse { start: string; hours: number; points: HeatmapPoint[] }

export interface GeocodeResponse { results: Place[] }

export interface ApiErrorBody { error: string; field?: string }
