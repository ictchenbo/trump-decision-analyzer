import request from '../utils/request'

export interface Alert {
  id?: string
  alert_time?: string
  level: 'red' | 'yellow' | 'green'
  title: string
  content: string
  trigger_factors: string[]
  status: 'unread' | 'read' | 'dismissed'
  event_id?: string
}

export const getAlerts = (level?: string, status?: string, limit?: number) => {
  return request.get<Alert[]>('/alerts/', {
    params: { level, status, limit }
  })
}

export const createAlert = (alert: Alert) => {
  return request.post('/alerts/', alert)
}

export const updateAlertStatus = (alert_id: string, status: string) => {
  return request.put(`/alerts/${alert_id}/status`, { status })
}

export const deleteAlert = (alert_id: string) => {
  return request.delete(`/alerts/${alert_id}`)
}
