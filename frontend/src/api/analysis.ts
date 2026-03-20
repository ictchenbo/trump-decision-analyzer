import request from '../utils/request'

export interface FactorScore {
  geopolitical: number
  domestic_political: number
  financial_market: number
  energy_market: number
  decision_team: number
}

export interface FactorDetail {
  key: string
  label: string
  score: number
  weight: number
}

export interface FactorScoresResult {
  factor_scores: FactorScore
  composite_index: number
  weights: Record<string, number>
  computed_at: string
  raw_indicators: Record<string, number>
  detail: FactorDetail[]
}

export interface CompositeIndexResult {
  composite_index: number
  dynamic_weights: Record<string, number>
  factor_scores: FactorScore
}

export const calculateCompositeIndex = (factor_scores: FactorScore, context?: Record<string, any>) => {
  return request.post<CompositeIndexResult>('/analysis/composite-index', {
    factor_scores,
    context
  })
}

export const getLatestFactorScores = () => {
  return request.get<FactorScoresResult>('/analysis/factor-scores/latest')
}

export const getFactorScoresHistory = (limit = 20) => {
  return request.get<FactorScoresResult[]>('/analysis/factor-scores/history', { params: { limit } })
}

export const getLatestWarPeaceScores = () => {
  return request.get<FactorScoresResult>('/analysis/war-peace/latest')
}

export const getWarPeaceHistory = (limit = 20) => {
  return request.get<FactorScoresResult[]>('/analysis/war-peace/history', { params: { limit } })
}

export const getEventTimeline = (event_id: string) => {
  return request.get(`/analysis/timeline/${event_id}`)
}

export const runSimulation = (factor: string, adjustment: number, base_index: number) => {
  return request.post('/analysis/simulate', {
    factor,
    adjustment,
    base_index
  })
}
