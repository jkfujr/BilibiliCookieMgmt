<script setup>
import { computed } from 'vue'

import {
  TASK_STATUS_LABELS,
  TASK_TYPE_LABELS,
  TERMINAL_TASK_STATUSES,
  taskProgress,
  taskStatusColor,
} from '../../utils/taskUtils'

const props = defineProps({
  center: {
    type: Object,
    required: true,
  },
  screenshotMode: {
    type: Boolean,
    default: false,
  },
})

const state = computed(() => props.center.state)
const selected = computed(() => state.value.selectedTask)
const progress = computed(() => taskProgress(selected.value))
const canCancel = computed(() => selected.value && !TERMINAL_TASK_STATUSES.has(selected.value.status))
const canRetry = computed(() => selected.value && TERMINAL_TASK_STATUSES.has(selected.value.status) && selected.value.failed > 0)
const canDelete = computed(() => selected.value && TERMINAL_TASK_STATUSES.has(selected.value.status))

const typeOptions = Object.entries(TASK_TYPE_LABELS).map(([value, title]) => ({ value, title }))
const statusOptions = [
  'queued',
  'running',
  'cancelling',
  'completed',
  'completed_with_errors',
  'cancelled',
  'failed',
].map((value) => ({ value, title: TASK_STATUS_LABELS[value] }))
const sourceOptions = [
  { value: 'manual', title: '手动' },
  { value: 'scheduled', title: '定时' },
  { value: 'retry', title: '重试' },
]
const itemStatusOptions = ['pending', 'running', 'succeeded', 'invalid', 'failed', 'skipped', 'cancelled']
  .map((value) => ({ value, title: TASK_STATUS_LABELS[value] || value }))

const totalPages = computed(() => Math.max(1, Math.ceil(state.value.total / state.value.pageSize)))
const itemPages = computed(() => Math.max(1, Math.ceil(state.value.itemTotal / state.value.itemPageSize)))

const formatTime = (value) => value ? new Date(value).toLocaleString('zh-CN') : '-'
const taskLabel = (value) => TASK_TYPE_LABELS[value] || value
const statusLabel = (value) => TASK_STATUS_LABELS[value] || value
const sourceLabel = (value) => sourceOptions.find((item) => item.value === value)?.title || value
const displaySubject = (item) => {
  if (props.screenshotMode && item.subject_id) return '******'
  return item.subject_id || '-'
}

const refreshHistory = async () => {
  state.value.page = 1
  await props.center.fetchTasks()
}

const refreshItems = async () => {
  state.value.itemPage = 1
  await props.center.fetchItems()
}
</script>

<template>
  <div class="task-center">
    <div class="task-toolbar">
      <div>
        <div class="text-h5 font-weight-bold">任务中心</div>
        <div class="text-body-2 text-medium-emphasis">{{ state.activeCount }} 个任务正在运行或排队</div>
      </div>
      <v-btn
        icon="mdi-refresh"
        variant="tonal"
        :loading="state.loading"
        aria-label="刷新任务"
        @click="center.fetchTasks"
      ></v-btn>
    </div>

    <v-sheet border rounded="lg" class="task-section">
      <div class="task-filters">
        <v-select
          v-model="state.typeFilter"
          :items="typeOptions"
          label="任务类型"
          clearable
          hide-details
          density="compact"
          variant="outlined"
          @update:model-value="refreshHistory"
        ></v-select>
        <v-select
          v-model="state.statusFilter"
          :items="statusOptions"
          label="任务状态"
          clearable
          hide-details
          density="compact"
          variant="outlined"
          @update:model-value="refreshHistory"
        ></v-select>
        <v-select
          v-model="state.sourceFilter"
          :items="sourceOptions"
          label="来源"
          clearable
          hide-details
          density="compact"
          variant="outlined"
          @update:model-value="refreshHistory"
        ></v-select>
      </div>

      <v-table class="task-history-table" density="comfortable" fixed-header height="320">
        <thead>
          <tr>
            <th>任务</th>
            <th>来源</th>
            <th>状态</th>
            <th>进度</th>
            <th>创建时间</th>
          </tr>
        </thead>
        <tbody>
          <tr
            v-for="task in state.tasks"
            :key="task.id"
            class="task-row"
            :class="{ 'task-row--active': selected?.id === task.id }"
            @click="center.selectTask(task)"
          >
            <td>
              <div class="font-weight-medium">{{ taskLabel(task.type) }}</div>
              <div class="text-caption text-medium-emphasis">{{ task.id.slice(0, 12) }}</div>
            </td>
            <td>{{ sourceLabel(task.source) }}</td>
            <td><v-chip size="small" :color="taskStatusColor(task.status)">{{ statusLabel(task.status) }}</v-chip></td>
            <td>{{ task.succeeded + task.invalid + task.failed + task.skipped + task.cancelled }} / {{ task.total }}</td>
            <td>{{ formatTime(task.created_at) }}</td>
          </tr>
          <tr v-if="!state.tasks.length">
            <td colspan="5" class="text-center text-medium-emphasis py-8">暂无任务记录</td>
          </tr>
        </tbody>
      </v-table>
      <v-pagination
        v-if="totalPages > 1"
        v-model="state.page"
        :length="totalPages"
        density="comfortable"
        class="pa-2"
        @update:model-value="center.fetchTasks"
      ></v-pagination>
    </v-sheet>

    <v-sheet v-if="selected" border rounded="lg" class="task-section task-detail">
      <div class="task-detail-header">
        <div>
          <div class="text-h6 font-weight-bold">{{ taskLabel(selected.type) }}</div>
          <div class="task-id text-caption text-medium-emphasis">{{ selected.id }} · {{ formatTime(selected.created_at) }}</div>
        </div>
        <div class="task-actions">
          <v-btn
            v-if="canCancel"
            color="warning"
            variant="tonal"
            prepend-icon="mdi-stop-circle-outline"
            :loading="state.actionLoading"
            @click="center.cancelSelected"
          >取消</v-btn>
          <v-btn
            v-if="canRetry"
            color="primary"
            variant="tonal"
            prepend-icon="mdi-replay"
            :loading="state.actionLoading"
            @click="center.retrySelected"
          >重试失败项</v-btn>
          <v-btn
            v-if="canDelete"
            color="error"
            variant="text"
            prepend-icon="mdi-delete-outline"
            :loading="state.actionLoading"
            @click="center.deleteSelected"
          >删除记录</v-btn>
        </div>
      </div>

      <v-progress-linear :model-value="progress" height="8" color="primary" rounded></v-progress-linear>
      <div class="task-stats">
        <div><span>总数</span><strong>{{ selected.total }}</strong></div>
        <div><span>成功</span><strong class="text-success">{{ selected.succeeded }}</strong></div>
        <div><span>无效</span><strong class="text-warning">{{ selected.invalid }}</strong></div>
        <div><span>失败</span><strong class="text-error">{{ selected.failed }}</strong></div>
        <div><span>跳过</span><strong>{{ selected.skipped }}</strong></div>
        <div><span>取消</span><strong>{{ selected.cancelled }}</strong></div>
      </div>

      <div class="task-item-toolbar">
        <v-select
          v-model="state.itemStatusFilter"
          :items="itemStatusOptions"
          label="明细状态"
          clearable
          hide-details
          density="compact"
          variant="outlined"
          max-width="240"
          @update:model-value="refreshItems"
        ></v-select>
        <v-chip :color="taskStatusColor(selected.status)" variant="tonal">{{ statusLabel(selected.status) }}</v-chip>
      </div>

      <v-table class="task-items-table" density="compact" fixed-header height="420">
        <thead>
          <tr>
            <th>序号</th>
            <th>原始行</th>
            <th>账号</th>
            <th>状态</th>
            <th>结果</th>
          </tr>
        </thead>
        <tbody>
          <tr v-for="item in state.items" :key="item.id">
            <td>{{ item.position + 1 }}</td>
            <td>{{ item.line_number || '-' }}</td>
            <td>{{ displaySubject(item) }}</td>
            <td><v-chip size="x-small" :color="taskStatusColor(item.status)">{{ statusLabel(item.status) }}</v-chip></td>
            <td class="task-message">{{ item.result?.message || '-' }}</td>
          </tr>
          <tr v-if="!state.items.length">
            <td colspan="5" class="text-center text-medium-emphasis py-8">暂无明细</td>
          </tr>
        </tbody>
      </v-table>
      <v-pagination
        v-if="itemPages > 1"
        v-model="state.itemPage"
        :length="itemPages"
        density="comfortable"
        class="pa-2"
        @update:model-value="center.fetchItems"
      ></v-pagination>
    </v-sheet>
  </div>
</template>

<style scoped>
.task-center {
  display: grid;
  gap: 20px;
}

.task-toolbar,
.task-detail-header,
.task-item-toolbar {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 16px;
}

.task-section {
  overflow: hidden;
  border-radius: 6px !important;
}

.task-filters {
  display: grid;
  grid-template-columns: repeat(3, minmax(160px, 1fr));
  gap: 12px;
  padding: 16px;
}

.task-row {
  cursor: pointer;
}

.task-row:hover,
.task-row--active {
  background: rgba(var(--v-theme-primary), 0.08);
}

.task-detail-header,
.task-item-toolbar {
  padding: 16px;
}

.task-actions {
  display: flex;
  flex-wrap: wrap;
  justify-content: flex-end;
  gap: 8px;
}

.task-detail-header > div:first-child {
  min-width: 0;
}

.task-id {
  overflow-wrap: anywhere;
}

.task-stats {
  display: grid;
  grid-template-columns: repeat(6, minmax(80px, 1fr));
  gap: 1px;
  background: rgba(var(--v-border-color), var(--v-border-opacity));
}

.task-stats > div {
  display: flex;
  flex-direction: column;
  gap: 4px;
  padding: 14px 16px;
  background: rgb(var(--v-theme-surface));
}

.task-stats span {
  color: rgba(var(--v-theme-on-surface), 0.65);
  font-size: 0.75rem;
}

.task-message {
  max-width: 420px;
  overflow-wrap: anywhere;
}

@media (max-width: 760px) {
  .task-filters,
  .task-stats {
    grid-template-columns: repeat(2, minmax(0, 1fr));
  }

  .task-detail-header,
  .task-item-toolbar {
    align-items: stretch;
    flex-direction: column;
  }

  .task-toolbar {
    align-items: center;
  }

  .task-actions {
    justify-content: flex-start;
  }

  .task-item-toolbar .v-chip {
    align-self: flex-start;
  }

  .task-history-table :deep(table) {
    min-width: 720px;
  }

  .task-items-table :deep(table) {
    min-width: 680px;
  }
}
</style>
