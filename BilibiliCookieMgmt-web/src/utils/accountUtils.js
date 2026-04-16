export const formatTime = (value) => {
  if (!value) {
    return ''
  }

  const date = new Date(typeof value === 'number' && value < 1e12 ? value * 1000 : value)
  if (Number.isNaN(date.getTime())) {
    return ''
  }

  return date.toLocaleString()
}

export const getAccountId = (account) => {
  const dedeUserID = account?.managed?.DedeUserID
  return dedeUserID ? String(dedeUserID) : ''
}

export const getExpireTime = (account) => {
  const cookies = account?.raw?.cookie_info?.cookies || []
  const sessionCookie = cookies.find((cookie) => cookie.name === 'SESSDATA')
  return sessionCookie?.expires
}

export const calculateAccountStats = (accounts) => {
  let valid = 0
  let expired = 0
  let invalid = 0

  ;(Array.isArray(accounts) ? accounts : []).forEach((account) => {
    const status = account?.managed?.status || 'unknown'
    if (status === 'valid') {
      valid += 1
    } else if (status === 'expired') {
      expired += 1
    } else if (status === 'invalid') {
      invalid += 1
    }
  })

  return {
    total: Array.isArray(accounts) ? accounts.length : 0,
    valid,
    expired,
    invalid,
  }
}

export const replaceAccountInList = (accounts, updatedDoc) => {
  if (!Array.isArray(accounts)) {
    return []
  }

  const dedeUserID = getAccountId(updatedDoc)
  if (!dedeUserID) {
    return accounts.slice()
  }

  const index = accounts.findIndex((account) => getAccountId(account) === dedeUserID)
  if (index === -1) {
    return accounts.slice()
  }

  const nextAccounts = accounts.slice()
  nextAccounts.splice(index, 1, updatedDoc)
  return nextAccounts
}

export const removeAccountFromList = (accounts, dedeUserID) => {
  if (!Array.isArray(accounts)) {
    return []
  }

  return accounts.filter((account) => getAccountId(account) !== String(dedeUserID || ''))
}

export const findAccountById = (accounts, dedeUserID) => {
  if (!Array.isArray(accounts)) {
    return undefined
  }

  return accounts.find((account) => getAccountId(account) === String(dedeUserID || ''))
}

export const clearTagFilterState = (matchMode) => {
  return {
    selectedTags: [],
    matchMode,
  }
}
