import { computed, ref } from 'vue'

import {
  buildUnauthorizedSessionState,
  clearStoredApiToken,
  loadStoredApiToken,
  saveStoredApiToken,
} from '../utils/sessionUtils'

const resolveStorage = (storage) => {
  if (storage) {
    return storage
  }

  if (typeof window !== 'undefined') {
    return window.localStorage
  }

  return null
}

export const useSession = ({ showMsg, storage } = {}) => {
  const resolvedStorage = resolveStorage(storage)
  const token = ref(loadStoredApiToken(resolvedStorage))
  const loginTokenInput = ref('')
  const loginDialog = ref(!token.value)
  const hasToken = computed(() => Boolean(token.value))

  const getToken = () => token.value

  const openLoginDialog = () => {
    loginDialog.value = true
  }

  const applyLoginToken = () => {
    const nextToken = loginTokenInput.value.trim()
    if (!nextToken) {
      return false
    }

    setSessionToken(nextToken)
    loginTokenInput.value = ''
    loginDialog.value = false
    return true
  }

  const setSessionToken = (nextToken) => {
    token.value = nextToken
    if (nextToken) {
      saveStoredApiToken(resolvedStorage, nextToken)
      return
    }
    clearStoredApiToken(resolvedStorage)
  }

  const clearSession = () => {
    setSessionToken('')
    loginTokenInput.value = ''
    loginDialog.value = true
  }

  const handleUnauthorized = () => {
    const nextState = buildUnauthorizedSessionState()
    token.value = nextState.token
    loginTokenInput.value = nextState.loginTokenInput
    loginDialog.value = nextState.loginDialog
    clearStoredApiToken(resolvedStorage)

    if (typeof showMsg === 'function') {
      showMsg('会话已过期，请重新登录', 'error')
    }
  }

  return {
    token,
    loginTokenInput,
    loginDialog,
    hasToken,
    getToken,
    openLoginDialog,
    applyLoginToken,
    setSessionToken,
    clearSession,
    handleUnauthorized,
  }
}
