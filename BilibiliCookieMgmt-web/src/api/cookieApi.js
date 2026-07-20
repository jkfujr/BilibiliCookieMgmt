export const listCookies = async (apiClient) => {
  const response = await apiClient.get('/v1/cookies/')
  return response.data
}

export const getCookieDetail = async (apiClient, dedeUserID) => {
  const response = await apiClient.get(`/v1/cookies/${dedeUserID}`)
  return response.data
}

export const deleteCookieById = async (apiClient, dedeUserID) => {
  const response = await apiClient.delete(`/v1/cookies/${dedeUserID}`)
  return response.data
}

export const setCookieEnabled = async (apiClient, dedeUserID, isEnabled) => {
  const response = await apiClient.patch(`/v1/cookies/${dedeUserID}/enabled`, {
    is_enabled: isEnabled,
  })
  return response.data
}

export const setCookieTags = async (apiClient, dedeUserID, tags) => {
  const response = await apiClient.patch(`/v1/cookies/${dedeUserID}/tags`, {
    tags,
  })
  return response.data
}
