export interface TrumpStatement {
  _id?: string
  content: string
  source: string
  post_time: string
  url?: string
  likes?: number
  shares?: number
  sentiment?: 'positive' | 'negative' | 'neutral'
  sentiment_score?: number
  translation?: string
  hawkish_score?: number
  llm_enriched?: boolean
  created_at?: string
  updated_at?: string
}

export interface TrumpStatementCreate {
  content: string
  source: string
  post_time: Date | string
  url?: string
  likes?: number
  shares?: number
  sentiment?: 'positive' | 'negative' | 'neutral'
  sentiment_score?: number
}

export interface HawkishDailyData {
  date: string
  avg_score: number
  count: number
}
