import request from '../utils/request'
import type { TrumpStatement } from '../models/trump_statement'

export interface TrumpStatementResponse {
  total: number
  statements: TrumpStatement[]
  fetch_time: string
}

export const getTrumpStatements = (
  source?: string,
  start_time?: Date,
  end_time?: Date,
  limit?: number,
  offset?: number,
  keyword?: string
) => {
  return request.get<TrumpStatementResponse>('/trump-statements', {
    params: {
      source,
      start_time: start_time?.toISOString(),
      end_time: end_time?.toISOString(),
      limit,
      offset,
      keyword
    }
  })
}

export const getTrumpStatement = (id: string) => {
  return request.get<TrumpStatement>(`/trump-statements/${id}`)
}

export const createTrumpStatement = (data: Partial<TrumpStatement>) => {
  return request.post('/trump-statements', data)
}

export const batchCreateTrumpStatements = (data: Partial<TrumpStatement>[]) => {
  return request.post('/trump-statements/batch', data)
}

export const deleteTrumpStatement = (id: string) => {
  return request.delete(`/trump-statements/${id}`)
}
