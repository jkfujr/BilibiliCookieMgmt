export const isUnauthorizedError = (error) => {
  return error?.response?.status === 401
}

const resolveMessage = (resolver, fallback, payload) => {
  if (typeof resolver === 'function') {
    return resolver(payload)
  }
  return fallback
}

export const runManagedRequest = async ({
  request,
  showMsg,
  successMessage,
  getSuccessMessage,
  getSuccessColor,
  errorMessage,
  getErrorMessage,
  setLoading,
  replaceAccount,
  pickUpdatedAccount,
  refreshAccounts,
  shouldRefresh = false,
  onSuccess,
  onError,
  onFinally,
}) => {
  if (typeof setLoading === 'function') {
    setLoading(true)
  }

  try {
    const result = await request()

    if (typeof pickUpdatedAccount === 'function' && typeof replaceAccount === 'function') {
      const updatedDoc = pickUpdatedAccount(result)
      if (updatedDoc) {
        replaceAccount(updatedDoc)
      }
    }

    if (onSuccess) {
      await onSuccess(result)
    }

    if (shouldRefresh && typeof refreshAccounts === 'function') {
      await refreshAccounts()
    }

    const message = resolveMessage(getSuccessMessage, successMessage, result)
    const color = typeof getSuccessColor === 'function' ? getSuccessColor(result) : 'success'
    if (message && typeof showMsg === 'function') {
      showMsg(message, color)
    }

    return { ok: true, result }
  } catch (error) {
    if (!isUnauthorizedError(error)) {
      if (onError) {
        await onError(error)
      }

      const message = resolveMessage(getErrorMessage, errorMessage, error)
      if (message && typeof showMsg === 'function') {
        showMsg(message, 'error')
      }
    }

    return { ok: false, error }
  } finally {
    if (typeof setLoading === 'function') {
      setLoading(false)
    }

    if (onFinally) {
      await onFinally()
    }
  }
}
