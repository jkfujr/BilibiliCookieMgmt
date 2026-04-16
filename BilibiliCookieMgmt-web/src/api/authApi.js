export const getTvQrCode = async (apiClient) => {
  const response = await apiClient.get('/v1/auth/tv/qrcode')
  return response.data
}

export const pollTvQrStatus = async (apiClient, authCode) => {
  const response = await apiClient.get('/v1/auth/tv/poll', {
    params: { auth_code: authCode },
  })
  return response.data
}
