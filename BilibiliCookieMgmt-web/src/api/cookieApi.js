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

export const checkCookies = async (apiClient, { all = false, ids } = {}) => {
  const response = await apiClient.post(`/v1/cookies/check?all=${all}`, ids ? { ids } : undefined)
  return response.data
}

export const refreshCookies = async (apiClient, { all = false, ids } = {}) => {
  const response = await apiClient.post(`/v1/cookies/refresh?all=${all}`, ids ? { ids } : undefined)
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

export const testCookieHeader = async (apiClient, cookie) => {
  const response = await apiClient.post('/v1/cookies/test', { cookie })
  return response.data
}
