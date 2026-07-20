import { onBeforeUnmount, reactive, watch } from 'vue'

import {
  cancelTask,
  createTask,
  deleteTask,
  getActiveTaskCount,
  getTaskUpdates,
  listTaskItems,
  listTasks,
  retryTask,
} from '../api/taskApi'
import { TERMINAL_TASK_STATUSES } from '../utils/taskUtils'

export const useTaskCenter = ({ apiClient, token, showMsg, isActive } = {}) => {
  const state = reactive({
    tasks: [],
    total: 0,
    page: 1,
    pageSize: 25,
    statusFilter: '',
    typeFilter: '',
    sourceFilter: '',
    selectedTask: null,
    items: [],
    itemTotal: 0,
    itemPage: 1,
    itemPageSize: 50,
    itemStatusFilter: '',
    revision: 0,
    loading: false,
    creating: false,
    actionLoading: false,
    activeCount: 0,
  })

  let pollTimer = null
  let polling = false
  let historyPollCounter = 0

  const hasToken = () => Boolean(typeof token === 'function' ? token() : token?.value)

  const refreshActiveCount = async () => {
    if (!hasToken()) return
    const result = await getActiveTaskCount(apiClient)
    state.activeCount = Number(result?.count || 0)
  }

  const fetchTasks = async ({ silent = false } = {}) => {
    if (!hasToken()) return
    if (!silent) state.loading = true
    try {
      const result = await listTasks(apiClient, {
        page: state.page,
        page_size: state.pageSize,
        status: state.statusFilter || undefined,
        type: state.typeFilter || undefined,
        source: state.sourceFilter || undefined,
      })
      state.tasks = result?.items || []
      state.total = Number(result?.total || 0)
      await refreshActiveCount()
    } catch (error) {
      if (!silent) showMsg?.(error?.response?.data?.detail || '获取任务历史失败', 'error')
    } finally {
      if (!silent) state.loading = false
    }
  }

  const fetchItems = async () => {
    if (!state.selectedTask) return
    const result = await listTaskItems(apiClient, state.selectedTask.id, {
      page: state.itemPage,
      page_size: state.itemPageSize,
      status: state.itemStatusFilter || undefined,
    })
    state.items = result?.items || []
    state.itemTotal = Number(result?.total || 0)
  }

  const selectTask = async (task) => {
    state.selectedTask = task
    state.revision = Number(task?.revision || 0)
    state.itemPage = 1
    await fetchItems()
  }

  const createAndOpen = async (payload) => {
    if (state.creating) return { ok: false }
    state.creating = true
    try {
      const task = await createTask(apiClient, payload)
      state.selectedTask = task
      state.revision = 0
      state.itemPage = 1
      await Promise.all([fetchTasks(), fetchItems()])
      showMsg?.('任务已创建')
      return { ok: true, task }
    } catch (error) {
      showMsg?.(error?.response?.data?.detail || '创建任务失败', 'error')
      return { ok: false, error }
    } finally {
      state.creating = false
    }
  }

  const mergeUpdates = (updates) => {
    const byId = new Map(state.items.map((item) => [item.id, item]))
    for (const item of updates || []) {
      if (byId.has(item.id)) Object.assign(byId.get(item.id), item)
    }
  }

  const poll = async () => {
    if (polling || !hasToken() || document.hidden) return
    polling = true
    try {
      const taskCenterActive = typeof isActive === 'function' && isActive()
      if (taskCenterActive && state.selectedTask) {
        const wasTerminal = TERMINAL_TASK_STATUSES.has(state.selectedTask.status)
        let hasMore = !wasTerminal
        let itemsChanged = false
        while (hasMore) {
          const result = await getTaskUpdates(apiClient, state.selectedTask.id, state.revision)
          if (result?.task) state.selectedTask = result.task
          mergeUpdates(result?.items)
          itemsChanged ||= Boolean(result?.items?.length)
          state.revision = Number(result?.next_revision || state.revision)
          hasMore = Boolean(result?.has_more)
        }
        if (itemsChanged && state.itemStatusFilter) await fetchItems()
        if (!wasTerminal && TERMINAL_TASK_STATUSES.has(state.selectedTask?.status)) {
          await Promise.all([fetchItems(), fetchTasks()])
        }
      }
      historyPollCounter = (historyPollCounter + 1) % 5
      if (taskCenterActive && historyPollCounter === 0) {
        await fetchTasks({ silent: true })
      } else {
        await refreshActiveCount()
      }
    } catch {
      // 下一轮轮询会自动恢复。
    } finally {
      polling = false
    }
  }

  const runAction = async (action, errorMessage) => {
    if (state.actionLoading) return null
    state.actionLoading = true
    try {
      return await action()
    } catch (error) {
      showMsg?.(error?.response?.data?.detail || errorMessage, 'error')
      return null
    } finally {
      state.actionLoading = false
    }
  }

  const cancelSelected = async () => {
    if (!state.selectedTask) return
    const task = await runAction(
      () => cancelTask(apiClient, state.selectedTask.id),
      '取消任务失败'
    )
    if (!task) return
    state.selectedTask = task
    showMsg?.('已请求取消任务', 'warning')
  }

  const retrySelected = async () => {
    if (!state.selectedTask) return
    const child = await runAction(
      () => retryTask(apiClient, state.selectedTask.id),
      '创建重试任务失败'
    )
    if (!child) return
    await selectTask(child)
    await fetchTasks()
    showMsg?.('失败项已创建重试任务')
  }

  const deleteSelected = async () => {
    if (!state.selectedTask) return
    const result = await runAction(
      () => deleteTask(apiClient, state.selectedTask.id),
      '删除任务历史失败'
    )
    if (!result) return
    state.selectedTask = null
    state.items = []
    await fetchTasks()
    showMsg?.('任务历史已删除')
  }

  watch(
    () => (typeof token === 'function' ? token() : token?.value),
    (value) => {
      if (!value) {
        state.tasks = []
        state.selectedTask = null
        state.activeCount = 0
        return
      }
      void fetchTasks()
    },
    { immediate: true }
  )

  pollTimer = window.setInterval(poll, 1000)
  onBeforeUnmount(() => window.clearInterval(pollTimer))

  return {
    state,
    fetchTasks,
    fetchItems,
    selectTask,
    createAndOpen,
    cancelSelected,
    retrySelected,
    deleteSelected,
  }
}
