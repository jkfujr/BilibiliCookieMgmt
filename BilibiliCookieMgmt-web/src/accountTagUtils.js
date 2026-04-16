export const normalizeTagList = (tags) => {
  if (!Array.isArray(tags)) {
    return []
  }

  const normalized = []
  const seen = new Set()

  tags.forEach((tag) => {
    const value = typeof tag === 'string' ? tag.trim() : ''
    if (!value || seen.has(value)) {
      return
    }
    seen.add(value)
    normalized.push(value)
  })

  return normalized
}

export const getAccountTags = (account) => {
  return normalizeTagList(account?.managed?.tags || [])
}

export const extractAvailableTags = (accounts) => {
  const available = []
  const seen = new Set()

  ;(Array.isArray(accounts) ? accounts : []).forEach((account) => {
    getAccountTags(account).forEach((tag) => {
      if (seen.has(tag)) {
        return
      }
      seen.add(tag)
      available.push(tag)
    })
  })

  return available
}

export const filterAccountsByTags = (accounts, selectedTags, matchMode = 'any') => {
  const source = Array.isArray(accounts) ? accounts : []
  const normalizedSelected = normalizeTagList(selectedTags)

  if (!normalizedSelected.length) {
    return source
  }

  return source.filter((account) => {
    const accountTags = getAccountTags(account)
    if (!accountTags.length) {
      return false
    }

    if (matchMode === 'all') {
      return normalizedSelected.every((tag) => accountTags.includes(tag))
    }

    return normalizedSelected.some((tag) => accountTags.includes(tag))
  })
}
