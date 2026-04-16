import axios from 'axios'

export const createApiClient = ({ getToken, onUnauthorized }) => {
  const client = axios.create({
    baseURL: '/api',
  })

  client.interceptors.request.use((config) => {
    const token = typeof getToken === 'function' ? getToken() : ''
    if (token) {
      config.headers.Authorization = `Bearer ${token}`
    }
    return config
  })

  client.interceptors.response.use(
    (response) => response,
    (error) => {
      if (error.response?.status === 401 && typeof onUnauthorized === 'function') {
        onUnauthorized()
      }
      return Promise.reject(error)
    }
  )

  return client
}
