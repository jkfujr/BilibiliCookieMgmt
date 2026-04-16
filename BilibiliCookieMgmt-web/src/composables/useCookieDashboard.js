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
import { extractAvailableTags, filterAccountsByTags, getAccountTags, normalizeTagList } from '../utils/accountTagUtils'
import {
  calculateAccountStats,
  clearTagFilterState,
  getAccountId,
  removeAccountFromList,
  replaceAccountInList,
} from '../utils/accountUtils'
import { runManagedRequest } from '../utils/requestUtils'

export const useCookieDashboard = ({ apiClient, token, showMsg } = {}) => {
  const accounts = ref([])
  const loading = ref(false)
  const screenshotMode = ref(false)

  const selectedTags = ref([])
  const tagMatchMode = ref('any')

  const cookieDialog = ref(false)
  const currentCookie = ref({ simple: '', complete: '' })
  const currentCookieTab = ref('simple')

  const tagDialog = ref(false)
  const tagTarget = ref(null)
  const tagEditorInput = ref([])

  const testCookieDialog = ref(false)
  const testCookieInput = ref('')

  const deleteDialog = ref(false)
  const deleteTarget = ref(null)

  const replaceAccount = (updatedDoc) => {
    accounts.value = replaceAccountInList(accounts.value, updatedDoc)
  }

  const removeAccount = (dedeUserID) => {
    accounts.value = removeAccountFromList(accounts.value, dedeUserID)
  }

  const resetTransientState = () => {
    accounts.value = []
    selectedTags.value = []
    tagMatchMode.value = 'any'
    cookieDialog.value = false
    currentCookie.value = { simple: '', complete: '' }
    currentCookieTab.value = 'simple'
    tagDialog.value = false
    tagTarget.value = null
    tagEditorInput.value = []
    testCookieDialog.value = false
    testCookieInput.value = ''
    deleteDialog.value = false
    deleteTarget.value = null
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

  const toggleEnabled = async (account) => {
    const dedeUserID = getAccountId(account)
    if (!dedeUserID) {
      return { ok: false }
    }

    const nextEnabled = !Boolean(account?.managed?.is_enabled)
    return runManagedRequest({
      request: () => setCookieEnabled(apiClient, dedeUserID, nextEnabled),
      showMsg,
      successMessage: `用户 ${account?.managed?.username || dedeUserID} 已${nextEnabled ? '启用' : '禁用'}`,
      errorMessage: '状态切换失败',
      replaceAccount,
      pickUpdatedAccount: (result) => result,
    })
  }

  const openTagDialog = (account) => {
    tagTarget.value = account
    tagEditorInput.value = getAccountTags(account)
    tagDialog.value = true
  }

  const closeTagDialog = () => {
    tagDialog.value = false
    tagTarget.value = null
    tagEditorInput.value = []
  }

  const saveTags = async () => {
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
    deleteTarget.value = account
    deleteDialog.value = true
  }

  const closeDeleteDialog = () => {
    deleteDialog.value = false
    deleteTarget.value = null
  }

  const deleteCookie = async () => {
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

  return {
    accounts,
    availableTags,
    filteredAccounts,
    loading,
    screenshotMode,
    selectedTags,
    stats,
    tagMatchMode,
    cookieDialog,
    currentCookie,
    currentCookieTab,
    tagDialog,
    tagTarget,
    tagEditorInput,
    testCookieDialog,
    testCookieInput,
    deleteDialog,
    deleteTarget,
    fetchAccounts,
    clearTagFilter,
    toggleScreenshotMode,
    checkAllCookies,
    refreshAllCookies,
    toggleEnabled,
    openTagDialog,
    closeTagDialog,
    saveTags,
    closeCookieDialog,
    viewCookie,
    copyContent,
    checkCookie,
    refreshCookie,
    requestDelete,
    closeDeleteDialog,
    deleteCookie,
    openTestCookieDialog,
    closeTestCookieDialog,
    testCookie,
  }
}
