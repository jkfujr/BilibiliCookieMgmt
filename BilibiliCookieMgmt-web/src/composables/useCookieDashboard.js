import { computed, ref, watch } from 'vue'

import {
  deleteCookieById,
  getCookieDetail,
  listCookies,
  setCookieEnabled,
  setCookieTags,
} from '../api/cookieApi'
import {
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
import { parseCookieLines, validateCookieLines } from '../utils/cookieInputUtils'
import { runManagedRequest } from '../utils/requestUtils'

export const useCookieDashboard = ({ apiClient, token, showMsg, createBackgroundTask } = {}) => {
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

  const submitTask = async (payload) => {
    if (typeof createBackgroundTask !== 'function') {
      showMsg?.('任务服务不可用', 'error')
      return { ok: false }
    }
    return createBackgroundTask(payload)
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

  const runSelectedCheck = async () => {
    const ids = getSelectedIdsOrWarn()
    if (!ids.length) {
      return { ok: false }
    }

    const result = await submitTask({ type: 'cookie_check', ids })
    if (result.ok) clearSelectedAccounts()
    return result
  }

  const runSelectedRefresh = async () => {
    const ids = getSelectedIdsOrWarn()
    if (!ids.length) {
      return { ok: false }
    }

    const result = await submitTask({ type: 'cookie_refresh', ids })
    if (result.ok) clearSelectedAccounts()
    return result
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
    if (!selectedAccounts.length) {
      showMsg?.('请先选择账号', 'warning')
      return { ok: false }
    }
    const result = await submitTask({
      type: 'cookie_enabled_update',
      items: selectedAccounts.map((account) => ({
        DedeUserID: getAccountId(account),
        is_enabled: getToggledEnabledValue(account),
      })),
    })
    if (result.ok) clearSelectedAccounts()
    return result
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

    const ids = getSelectedAccountIds()
    if (!ids.length) {
      showMsg?.('请先选择账号', 'warning')
      return { ok: false }
    }
    const result = await submitTask({ type: 'cookie_tag_append', ids, tags: tagsToAppend })

    if (result.ok) {
      closeTagDialog()
      clearSelectedAccounts()
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

    return submitTask({ type: 'cookie_check', ids: [dedeUserID] })
  }

  const refreshCookie = async (account) => {
    const dedeUserID = getAccountId(account)
    if (!dedeUserID) {
      return { ok: false }
    }

    return submitTask({ type: 'cookie_refresh', ids: [dedeUserID] })
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
    const ids = getSelectedAccountIds()
    if (!ids.length) {
      showMsg?.('请先选择账号', 'warning')
      return { ok: false }
    }
    const result = await submitTask({ type: 'cookie_delete', ids })

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
    const items = parseCookieLines(testCookieInput.value)
    const error = validateCookieLines(items)
    if (error) {
      showMsg?.(error, 'error')
      return { ok: false }
    }

    const result = await submitTask({ type: 'raw_cookie_validation', items })
    if (result.ok) {
      testCookieDialog.value = false
      testCookieInput.value = ''
    }
    return result
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
