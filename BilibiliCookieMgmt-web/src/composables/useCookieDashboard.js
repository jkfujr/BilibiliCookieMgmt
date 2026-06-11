import { computed, ref, watch } from 'vue'

import {
  checkCookies,
  deleteCookieById,
  getCookieDetail,
  listCookies,
  refreshCookies,
  setCookieEnabled,
  setCookieTags,
  testCookieHeader,
} from '../api/cookieApi'
import {
  appendAccountTags,
  extractAvailableTags,
  filterAccountsByTags,
  getAccountTags,
  normalizeTagList,
} from '../utils/accountTagUtils'
import {
  calculateAccountStats,
  clearTagFilterState,
  getAccountId,
  getToggledEnabledValue,
  normalizeAccountIds,
  removeAccountFromList,
  replaceAccountInList,
  syncSelectedAccountIds as syncAccountSelection,
} from '../utils/accountUtils'
import { runManagedRequest } from '../utils/requestUtils'

export const useCookieDashboard = ({ apiClient, token, showMsg } = {}) => {
  const accounts = ref([])
  const loading = ref(false)
  const screenshotMode = ref(false)

  const selectedTags = ref([])
  const tagMatchMode = ref('any')
  const selectedAccountIds = ref([])

  const cookieDialog = ref(false)
  const currentCookie = ref({ account: null, simple: '', complete: '' })
  const currentCookieTab = ref('simple')

  const tagDialog = ref(false)
  const tagTarget = ref(null)
  const tagEditorInput = ref([])
  const tagDialogMode = ref('single')
  const bulkTagCount = ref(0)

  const testCookieDialog = ref(false)
  const testCookieInput = ref('')

  const deleteDialog = ref(false)
  const deleteTarget = ref(null)
  const deleteDialogMode = ref('single')
  const bulkDeleteCount = ref(0)

  const selectedAccountCount = computed(() => selectedAccountIds.value.length)

  const setSelectedAccountIds = (ids) => {
    selectedAccountIds.value = normalizeAccountIds(ids)
  }

  const clearSelectedAccounts = () => {
    selectedAccountIds.value = []
  }

  const getSelectedAccountIds = () => {
    return normalizeAccountIds(selectedAccountIds.value)
  }

  const getSelectedAccounts = () => {
    const selectedIds = new Set(getSelectedAccountIds())
    return accounts.value.filter((account) => selectedIds.has(getAccountId(account)))
  }

  const syncSelectedAccountIds = () => {
    selectedAccountIds.value = syncAccountSelection(selectedAccountIds.value, accounts.value)
  }

  const getSelectedIdsOrWarn = () => {
    const ids = getSelectedAccountIds()
    if (!ids.length) {
      showMsg?.('请先选择账号', 'warning')
    }
    return ids
  }

  const getBatchMessage = (label, result) => {
    const total = Number(result?.total ?? 0)
    const succeeded = Number(result?.succeeded ?? result?.refreshed ?? 0)
    const failed = Number(result?.failed ?? 0)
    return `${label}完成：共 ${total} 个，成功 ${succeeded} 个，失败 ${failed} 个`
  }

  const runSequentialBatch = async ({ items, action }) => {
    let succeeded = 0
    let failed = 0

    for (const item of items) {
      try {
        const result = await action(item)
        if (result?.ok === false) {
          failed += 1
        } else {
          succeeded += 1
        }
      } catch (error) {
        failed += 1
      }
    }

    return {
      ok: failed === 0,
      total: items.length,
      succeeded,
      failed,
    }
  }

  const runBatchWithLoading = async ({ items, action, successLabel, emptyMessage }) => {
    if (!items.length) {
      showMsg?.(emptyMessage || '请先选择账号', 'warning')
      return { ok: false }
    }

    loading.value = true
    try {
      const result = await runSequentialBatch({ items, action })
      showMsg?.(getBatchMessage(successLabel, result), result.failed ? 'warning' : 'success')
      return result
    } finally {
      loading.value = false
    }
  }

  const replaceAccount = (updatedDoc) => {
    accounts.value = replaceAccountInList(accounts.value, updatedDoc)
  }

  const removeAccount = (dedeUserID) => {
    accounts.value = removeAccountFromList(accounts.value, dedeUserID)
    syncSelectedAccountIds()
  }

  const resetTransientState = () => {
    accounts.value = []
    selectedTags.value = []
    tagMatchMode.value = 'any'
    selectedAccountIds.value = []
    cookieDialog.value = false
    currentCookie.value = { account: null, simple: '', complete: '' }
    currentCookieTab.value = 'simple'
    tagDialog.value = false
    tagTarget.value = null
    tagEditorInput.value = []
    tagDialogMode.value = 'single'
    bulkTagCount.value = 0
    testCookieDialog.value = false
    testCookieInput.value = ''
    deleteDialog.value = false
    deleteTarget.value = null
    deleteDialogMode.value = 'single'
    bulkDeleteCount.value = 0
  }

  const fetchAccounts = async () => {
    const currentToken = typeof token === 'function' ? token() : token?.value
    if (!currentToken) {
      accounts.value = []
      return { ok: true, result: [] }
    }

    return runManagedRequest({
      request: () => listCookies(apiClient),
      showMsg,
      errorMessage: '获取账号列表失败',
      setLoading: (value) => {
        loading.value = value
      },
      onSuccess: (result) => {
        accounts.value = Array.isArray(result) ? result : []
        syncSelectedAccountIds()
      },
    })
  }

  const filteredAccounts = computed(() => {
    return filterAccountsByTags(accounts.value, selectedTags.value, tagMatchMode.value)
  })

  const availableTags = computed(() => {
    return normalizeTagList([...selectedTags.value, ...extractAvailableTags(filteredAccounts.value)])
  })

  const stats = computed(() => {
    return calculateAccountStats(filteredAccounts.value)
  })

  const clearTagFilter = () => {
    const nextState = clearTagFilterState(tagMatchMode.value)
    selectedTags.value = nextState.selectedTags
    tagMatchMode.value = nextState.matchMode
  }

  const toggleScreenshotMode = () => {
    screenshotMode.value = !screenshotMode.value
  }

  const checkAllCookies = async () => {
    return runManagedRequest({
      request: () => checkCookies(apiClient, { all: true }),
      showMsg,
      successMessage: '所有 Cookie 已检查完成',
      errorMessage: '检查请求失败',
      setLoading: (value) => {
        loading.value = value
      },
      refreshAccounts: fetchAccounts,
      shouldRefresh: true,
    })
  }

  const refreshAllCookies = async () => {
    return runManagedRequest({
      request: () => refreshCookies(apiClient, { all: true }),
      showMsg,
      successMessage: '需要刷新的 Cookie 已刷新',
      errorMessage: '刷新请求失败',
      setLoading: (value) => {
        loading.value = value
      },
      refreshAccounts: fetchAccounts,
      shouldRefresh: true,
    })
  }

  const runSelectedCheck = async () => {
    const ids = getSelectedIdsOrWarn()
    if (!ids.length) {
      return { ok: false }
    }

    return runManagedRequest({
      request: () => checkCookies(apiClient, { ids }),
      showMsg,
      errorMessage: '检查请求失败',
      setLoading: (value) => {
        loading.value = value
      },
      refreshAccounts: fetchAccounts,
      shouldRefresh: true,
      getSuccessMessage: (result) => getBatchMessage('状态检查', result),
      getSuccessColor: (result) => Number(result?.failed || 0) > 0 ? 'warning' : 'success',
    })
  }

  const runSelectedRefresh = async () => {
    const ids = getSelectedIdsOrWarn()
    if (!ids.length) {
      return { ok: false }
    }

    return runManagedRequest({
      request: () => refreshCookies(apiClient, { ids }),
      showMsg,
      errorMessage: '刷新请求失败',
      setLoading: (value) => {
        loading.value = value
      },
      refreshAccounts: fetchAccounts,
      shouldRefresh: true,
      getSuccessMessage: (result) => getBatchMessage('自动刷新', result),
      getSuccessColor: (result) => Number(result?.failed || 0) > 0 ? 'warning' : 'success',
    })
  }

  const toggleEnabled = async (account) => {
    const dedeUserID = getAccountId(account)
    if (!dedeUserID) {
      return { ok: false }
    }

    const nextEnabled = getToggledEnabledValue(account)
    return runManagedRequest({
      request: () => setCookieEnabled(apiClient, dedeUserID, nextEnabled),
      showMsg,
      successMessage: `用户 ${account?.managed?.username || dedeUserID} 已${nextEnabled ? '启用' : '禁用'}`,
      errorMessage: '状态切换失败',
      replaceAccount,
      pickUpdatedAccount: (result) => result,
    })
  }

  const toggleSelectedEnabled = async () => {
    const selectedAccounts = getSelectedAccounts()
    return runBatchWithLoading({
      items: selectedAccounts,
      successLabel: '开启/禁用',
      action: async (account) => {
        const dedeUserID = getAccountId(account)
        const updatedDoc = await setCookieEnabled(apiClient, dedeUserID, getToggledEnabledValue(account))
        replaceAccount(updatedDoc)
        return { ok: true }
      },
    })
  }

  const openTagDialog = (account) => {
    tagDialogMode.value = 'single'
    tagTarget.value = account
    tagEditorInput.value = getAccountTags(account)
    bulkTagCount.value = 0
    tagDialog.value = true
  }

  const openBulkTagDialog = () => {
    const selectedAccounts = getSelectedAccounts()
    if (!selectedAccounts.length) {
      showMsg?.('请先选择账号', 'warning')
      return
    }

    tagDialogMode.value = 'bulk'
    tagTarget.value = null
    tagEditorInput.value = []
    bulkTagCount.value = selectedAccounts.length
    tagDialog.value = true
  }

  const closeTagDialog = () => {
    tagDialog.value = false
    tagTarget.value = null
    tagEditorInput.value = []
    tagDialogMode.value = 'single'
    bulkTagCount.value = 0
  }

  const saveSingleTags = async () => {
    const dedeUserID = getAccountId(tagTarget.value)
    if (!dedeUserID) {
      return { ok: false }
    }

    const tags = normalizeTagList(tagEditorInput.value)
    return runManagedRequest({
      request: () => setCookieTags(apiClient, dedeUserID, tags),
      showMsg,
      successMessage: tags.length ? '账号标签已更新' : '账号标签已清空',
      errorMessage: '标签更新失败',
      replaceAccount,
      pickUpdatedAccount: (result) => result,
      onSuccess: () => {
        closeTagDialog()
      },
    })
  }

  const saveBulkTags = async () => {
    const tagsToAppend = normalizeTagList(tagEditorInput.value)
    if (!tagsToAppend.length) {
      showMsg?.('请输入要追加的标签', 'warning')
      return { ok: false }
    }

    const result = await runBatchWithLoading({
      items: getSelectedAccounts(),
      successLabel: '标签追加',
      action: async (account) => {
        const dedeUserID = getAccountId(account)
        const updatedDoc = await setCookieTags(apiClient, dedeUserID, appendAccountTags(account, tagsToAppend))
        replaceAccount(updatedDoc)
        return { ok: true }
      },
    })

    if (result.ok) {
      closeTagDialog()
    }

    return result
  }

  const saveTags = async () => {
    if (tagDialogMode.value === 'bulk') {
      return saveBulkTags()
    }

    return saveSingleTags()
  }

  const closeCookieDialog = () => {
    cookieDialog.value = false
  }

  const viewCookie = async (account) => {
    const dedeUserID = getAccountId(account)
    if (!dedeUserID) {
      return { ok: false }
    }

    return runManagedRequest({
      request: () => getCookieDetail(apiClient, dedeUserID),
      showMsg,
      errorMessage: '获取 Cookie 详情失败',
      onSuccess: (result) => {
        currentCookie.value = {
          account: result,
          simple: result?.managed?.header_string || '',
          complete: JSON.stringify(result, null, 4),
        }
        currentCookieTab.value = 'simple'
        cookieDialog.value = true
      },
    })
  }

  const copyContent = async (text) => {
    if (!navigator?.clipboard || !window.isSecureContext) {
      showMsg?.('当前环境不支持剪贴板复制', 'error')
      return false
    }

    try {
      await navigator.clipboard.writeText(text)
      showMsg?.('已复制到剪贴板')
      return true
    } catch (error) {
      showMsg?.('复制失败，请手动复制', 'error')
      return false
    }
  }

  const checkCookie = async (account) => {
    const dedeUserID = getAccountId(account)
    if (!dedeUserID) {
      return { ok: false }
    }

    return runManagedRequest({
      request: () => checkCookies(apiClient, { ids: [dedeUserID] }),
      showMsg,
      errorMessage: '检查请求失败',
      refreshAccounts: fetchAccounts,
      shouldRefresh: true,
      getSuccessMessage: (result) => {
        const detail = result?.details?.find((item) => item?.DedeUserID === dedeUserID)
        if (!detail) {
          return 'Cookie 检查完成'
        }
        return detail.ok ? 'Cookie 有效！' : `Cookie 无效: ${detail.message || ''}`
      },
      getSuccessColor: (result) => {
        const detail = result?.details?.find((item) => item?.DedeUserID === dedeUserID)
        return detail?.ok === false ? 'warning' : 'success'
      },
    })
  }

  const refreshCookie = async (account) => {
    const dedeUserID = getAccountId(account)
    if (!dedeUserID) {
      return { ok: false }
    }

    return runManagedRequest({
      request: () => refreshCookies(apiClient, { ids: [dedeUserID] }),
      showMsg,
      errorMessage: '刷新请求失败',
      refreshAccounts: fetchAccounts,
      shouldRefresh: true,
      getSuccessMessage: (result) => {
        const detail = result?.details?.find((item) => item?.DedeUserID === dedeUserID)
        if (!detail) {
          return '刷新完成'
        }
        return detail.ok ? '刷新成功' : `刷新失败: ${detail.message || ''}`
      },
      getSuccessColor: (result) => {
        const detail = result?.details?.find((item) => item?.DedeUserID === dedeUserID)
        return detail?.ok === false ? 'error' : 'success'
      },
    })
  }

  const requestDelete = (account) => {
    deleteDialogMode.value = 'single'
    deleteTarget.value = account
    bulkDeleteCount.value = 0
    deleteDialog.value = true
  }

  const requestBulkDelete = () => {
    const selectedAccounts = getSelectedAccounts()
    if (!selectedAccounts.length) {
      showMsg?.('请先选择账号', 'warning')
      return
    }

    deleteDialogMode.value = 'bulk'
    deleteTarget.value = null
    bulkDeleteCount.value = selectedAccounts.length
    deleteDialog.value = true
  }

  const closeDeleteDialog = () => {
    deleteDialog.value = false
    deleteTarget.value = null
    deleteDialogMode.value = 'single'
    bulkDeleteCount.value = 0
  }

  const deleteSingleCookie = async () => {
    const dedeUserID = getAccountId(deleteTarget.value)
    if (!dedeUserID) {
      return { ok: false }
    }

    return runManagedRequest({
      request: () => deleteCookieById(apiClient, dedeUserID),
      showMsg,
      successMessage: '删除成功',
      errorMessage: '删除请求失败',
      onSuccess: () => {
        removeAccount(dedeUserID)
        closeDeleteDialog()
      },
    })
  }

  const deleteSelectedCookies = async () => {
    const result = await runBatchWithLoading({
      items: getSelectedAccounts(),
      successLabel: '删除',
      action: async (account) => {
        const dedeUserID = getAccountId(account)
        await deleteCookieById(apiClient, dedeUserID)
        removeAccount(dedeUserID)
        return { ok: true }
      },
    })

    if (result.ok) {
      closeDeleteDialog()
      clearSelectedAccounts()
    }

    return result
  }

  const deleteCookie = async () => {
    if (deleteDialogMode.value === 'bulk') {
      return deleteSelectedCookies()
    }

    return deleteSingleCookie()
  }

  const openTestCookieDialog = () => {
    testCookieDialog.value = true
  }

  const closeTestCookieDialog = () => {
    testCookieDialog.value = false
  }

  const testCookie = async () => {
    const cookie = testCookieInput.value.trim()
    if (!cookie) {
      showMsg?.('请输入 Cookie 字符串', 'error')
      return { ok: false }
    }

    return runManagedRequest({
      request: () => testCookieHeader(apiClient, cookie),
      showMsg,
      errorMessage: '测试请求失败',
      getSuccessMessage: (result) => {
        return result?.is_valid ? '该 Cookie 有效！' : `该 Cookie 无效: ${result?.message || ''}`
      },
      getSuccessColor: (result) => {
        return result?.is_valid ? 'success' : 'error'
      },
    })
  }

  watch(
    () => (typeof token === 'function' ? token() : token?.value),
    (nextToken) => {
      if (!nextToken) {
        resetTransientState()
        return
      }

      void fetchAccounts()
    },
    { immediate: true }
  )

  watch(
    accounts,
    () => {
      syncSelectedAccountIds()
    },
    { deep: true }
  )

  return {
    accounts,
    availableTags,
    filteredAccounts,
    loading,
    screenshotMode,
    selectedAccountIds,
    selectedAccountCount,
    selectedTags,
    stats,
    tagMatchMode,
    cookieDialog,
    currentCookie,
    currentCookieTab,
    tagDialog,
    tagDialogMode,
    tagTarget,
    tagEditorInput,
    bulkTagCount,
    testCookieDialog,
    testCookieInput,
    deleteDialog,
    deleteDialogMode,
    deleteTarget,
    bulkDeleteCount,
    fetchAccounts,
    clearTagFilter,
    toggleScreenshotMode,
    checkAllCookies,
    refreshAllCookies,
    setSelectedAccountIds,
    clearSelectedAccounts,
    getSelectedAccounts,
    getSelectedAccountIds,
    syncSelectedAccountIds,
    runSelectedCheck,
    runSelectedRefresh,
    toggleEnabled,
    toggleSelectedEnabled,
    openTagDialog,
    openBulkTagDialog,
    closeTagDialog,
    saveTags,
    saveBulkTags,
    closeCookieDialog,
    viewCookie,
    copyContent,
    checkCookie,
    refreshCookie,
    requestDelete,
    requestBulkDelete,
    closeDeleteDialog,
    deleteCookie,
    openTestCookieDialog,
    closeTestCookieDialog,
    testCookie,
  }
}
