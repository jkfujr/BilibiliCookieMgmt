export const API_TOKEN_STORAGE_KEY = 'api_token'

export const loadStoredApiToken = (storage) => {
  if (!storage) {
    return ''
  }
  return storage.getItem(API_TOKEN_STORAGE_KEY) || ''
}

export const saveStoredApiToken = (storage, token) => {
  if (!storage) {
    return
  }
  storage.setItem(API_TOKEN_STORAGE_KEY, token)
}

export const clearStoredApiToken = (storage) => {
  if (!storage) {
    return
  }
  storage.removeItem(API_TOKEN_STORAGE_KEY)
}

export const buildUnauthorizedSessionState = () => {
  return {
    token: '',
    loginTokenInput: '',
    loginDialog: true,
  }
}
