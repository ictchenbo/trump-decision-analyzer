import axios from 'axios'
import { ElMessage } from 'element-plus'

const request = axios.create({
  baseURL: '/api',
  timeout: 10000
})

request.interceptors.request.use(
  config => config,
  error => Promise.reject(error)
)

request.interceptors.response.use(
  response => response.data,
  error => {
    ElMessage.error({
      message: error.response?.data?.message || '请求失败',
      duration: 3000
    })
    return Promise.reject(error)
  }
)

// 拦截器已将 response.data 直接返回，覆盖 axios 默认类型
const typedRequest = {
  get<T = any>(url: string, config?: Parameters<typeof request.get>[1]): Promise<T> {
    return request.get(url, config) as unknown as Promise<T>
  },
  post<T = any>(url: string, data?: any, config?: Parameters<typeof request.post>[2]): Promise<T> {
    return request.post(url, data, config) as unknown as Promise<T>
  },
  put<T = any>(url: string, data?: any, config?: Parameters<typeof request.put>[2]): Promise<T> {
    return request.put(url, data, config) as unknown as Promise<T>
  },
  delete<T = any>(url: string, config?: Parameters<typeof request.delete>[1]): Promise<T> {
    return request.delete(url, config) as unknown as Promise<T>
  },
}

export default typedRequest
