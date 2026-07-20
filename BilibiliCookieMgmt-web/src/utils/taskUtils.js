export const TERMINAL_TASK_STATUSES = new Set(['completed', 'completed_with_errors', 'cancelled', 'failed'])

export const TASK_TYPE_LABELS = {
  raw_cookie_validation: '原始 Cookie 校验',
  cookie_check: '账号状态检查',
  cookie_refresh: '账号刷新',
  cookie_enabled_update: '批量启停',
  cookie_tag_append: '批量追加标签',
  cookie_delete: '批量删除',
  bili_ticket_refresh: 'ticket 刷新',
  risk_control_check: '风控检查',
}

export const TASK_STATUS_LABELS = {
  queued: '排队中',
  running: '运行中',
  cancelling: '取消中',
  completed: '已完成',
  completed_with_errors: '部分失败',
  cancelled: '已取消',
  failed: '任务失败',
  pending: '待处理',
  succeeded: '成功',
  invalid: '无效',
  skipped: '已跳过',
}

export const taskStatusColor = (status) => {
  if (['completed', 'succeeded'].includes(status)) return 'success'
  if (['completed_with_errors', 'invalid', 'skipped'].includes(status)) return 'warning'
  if (['failed', 'cancelled'].includes(status)) return 'error'
  if (status === 'running') return 'primary'
  return 'grey'
}

export const taskProgress = (task) => {
  const total = Number(task?.total || 0)
  if (!total) return 0
  const completed = ['succeeded', 'invalid', 'failed', 'skipped', 'cancelled']
    .reduce((sum, key) => sum + Number(task?.[key] || 0), 0)
  return Math.min(100, Math.round((completed / total) * 100))
}
