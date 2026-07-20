export const createTask = async (apiClient, payload) => {
  const response = await apiClient.post('/v1/tasks', payload)
  return response.data
}

export const listTasks = async (apiClient, params = {}) => {
  const response = await apiClient.get('/v1/tasks', { params })
  return response.data
}

export const getTask = async (apiClient, taskId) => {
  const response = await apiClient.get(`/v1/tasks/${taskId}`)
  return response.data
}

export const listTaskItems = async (apiClient, taskId, params = {}) => {
  const response = await apiClient.get(`/v1/tasks/${taskId}/items`, { params })
  return response.data
}

export const getTaskUpdates = async (apiClient, taskId, after = 0) => {
  const response = await apiClient.get(`/v1/tasks/${taskId}/updates`, { params: { after } })
  return response.data
}

export const getActiveTaskCount = async (apiClient) => {
  const response = await apiClient.get('/v1/tasks/active-count')
  return response.data
}

export const cancelTask = async (apiClient, taskId) => {
  const response = await apiClient.post(`/v1/tasks/${taskId}/cancel`)
  return response.data
}

export const retryTask = async (apiClient, taskId) => {
  const response = await apiClient.post(`/v1/tasks/${taskId}/retry`)
  return response.data
}

export const deleteTask = async (apiClient, taskId) => {
  const response = await apiClient.delete(`/v1/tasks/${taskId}`)
  return response.data
}
