import request from '../utils/request'

export interface RealTimeData {
  name: string
  value: number
  unit: string
  trend: 'up' | 'down' | 'stable' | 'unknown'
  updated_at: string
  source?: string
  prev_value?: number | null
  prev_time?: string | null
  change?: number | null
  change_pct?: number | null
}

export type Granularity = 'minute' | 'hour' | 'day' | 'week'

export const getRealTimeData = (indicator?: string) => {
  return request.get<RealTimeData[]>('/data/real-time', {
    params: { indicator }
  })
}

export const getRealTimeHistory = (
  indicator: string,
  granularity: Granularity = 'day',
  limit = 60
) => {
  return request.get<RealTimeData[]>('/data/real-time/history', {
    params: { indicator, granularity, limit }
  })
}

export const addRealTimeData = (data: Partial<RealTimeData>) => {
  return request.post('/data/real-time', data)
}

export const getHistoryData = (startTime?: Date, endTime?: Date, limit?: number) => {
  return request.get('/data/history', {
    params: {
      start_time: startTime?.toISOString(),
      end_time: endTime?.toISOString(),
      limit
    }
  })
}
