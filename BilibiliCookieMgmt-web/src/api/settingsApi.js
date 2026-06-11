export const getSettings = async (apiClient) => {
  const response = await apiClient.get('/v1/settings/')
  return response.data
}

export const updateSettings = async (apiClient, settings) => {
  const response = await apiClient.put('/v1/settings/', settings)
  return response.data
}
