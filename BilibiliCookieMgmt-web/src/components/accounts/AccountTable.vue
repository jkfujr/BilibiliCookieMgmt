<script setup>
import TagFilterBar from '../dashboard/TagFilterBar.vue'
import { getAccountTags } from '../../utils/accountTagUtils'
import { formatTime, getExpireTime } from '../../utils/accountUtils'

defineProps({
  items: {
    type: Array,
    required: true,
  },
  loading: {
    type: Boolean,
    required: true,
  },
  screenshotMode: {
    type: Boolean,
    required: true,
  },
  hasTagFilter: {
    type: Boolean,
    required: true,
  },
  selectedTags: {
    type: Array,
    required: true,
  },
  availableTags: {
    type: Array,
    required: true,
  },
  matchMode: {
    type: String,
    required: true,
  },
})

const emit = defineEmits([
  'toggle-enabled',
  'edit-tags',
  'view-cookie',
  'check-cookie',
  'refresh-cookie',
  'delete-cookie',
  'clear-filter',
  'start-scan',
  'update:selected-tags',
  'update:match-mode',
])

const headers = [
  { title: '用户信息', key: 'user_info', align: 'start', sortable: false },
  { title: '标签', key: 'tags', align: 'start', sortable: false },
  { title: '是否启用', key: 'is_enabled', align: 'center' },
  { title: '加入时间', key: 'managed.join_time', align: 'center' },
  { title: '更新时间', key: 'managed.update_time', align: 'center' },
  { title: '过期时间', key: 'expire_time', align: 'center' },
  { title: '登录状态', key: 'managed.status', align: 'center' },
  { title: '检查时间', key: 'managed.last_check_time', align: 'center' },
  { title: '操作', key: 'actions', align: 'center', sortable: false },
]

const statusMap = {
  valid: {
    color: 'success',
    icon: 'mdi-check',
    label: '有效',
  },
  expired: {
    color: 'warning',
    icon: 'mdi-clock-outline',
    label: '过期',
  },
  invalid: {
    color: 'error',
    icon: 'mdi-close-circle-outline',
    label: '无效',
  },
  unknown: {
    color: 'grey',
    icon: '',
    label: '未知',
  },
}

const getStatusDisplay = (status) => {
  return statusMap[status] || statusMap.unknown
}
</script>

<template>
  <v-data-table
    :headers="headers"
    :items="items"
    :loading="loading"
    hover
    density="compact"
  >
    <template #item.user_info="{ item, index }">
      <div class="d-flex flex-row align-center py-1">
        <v-avatar color="grey-lighten-2" size="24" class="mr-2">
          <v-icon icon="mdi-account" size="16"></v-icon>
        </v-avatar>
        <div class="d-flex flex-column">
          <div class="text-body-2 font-weight-bold lh-1">
            {{ screenshotMode ? `你好 ${index + 1}` : (item.managed?.username || '未知用户') }}
          </div>
          <div class="text-caption text-grey-darken-1 font-monospace lh-1 account-id">
            {{ screenshotMode ? 114514 : item.managed?.DedeUserID }}
          </div>
        </div>
      </div>
    </template>

    <template #item.tags="{ item }">
      <div class="d-flex flex-wrap ga-1 py-2">
        <v-chip
          v-for="tag in getAccountTags(item)"
          :key="`${item.managed?.DedeUserID}-${tag}`"
          color="info"
          size="x-small"
          variant="tonal"
        >
          {{ tag }}
        </v-chip>
        <v-chip
          v-if="!getAccountTags(item).length"
          color="grey"
          size="x-small"
          variant="outlined"
        >
          无标签
        </v-chip>
      </div>
    </template>

    <template #header.tags>
      <div class="d-flex align-center ga-1">
        <span>标签</span>
        <TagFilterBar
          :selected-tags="selectedTags"
          :available-tags="availableTags"
          :match-mode="matchMode"
          @update:selected-tags="emit('update:selected-tags', $event)"
          @update:match-mode="emit('update:match-mode', $event)"
          @clear="emit('clear-filter')"
        />
      </div>
    </template>

    <template #item.is_enabled="{ item }">
      <v-switch
        :model-value="item.managed?.is_enabled"
        color="success"
        hide-details
        density="compact"
        inset
        class="scale-08"
        @update:model-value="emit('toggle-enabled', item)"
      ></v-switch>
    </template>

    <template #item.managed.join_time="{ item }">
      <div class="text-caption">{{ formatTime(item.managed?.join_time) }}</div>
    </template>

    <template #item.managed.update_time="{ item }">
      <div class="text-caption">{{ formatTime(item.managed?.update_time) }}</div>
    </template>

    <template #item.expire_time="{ item }">
      <div class="text-caption">{{ formatTime(getExpireTime(item)) }}</div>
    </template>

    <template #item.managed.status="{ item }">
      <v-chip
        :color="getStatusDisplay(item.managed?.status).color"
        size="x-small"
        :prepend-icon="getStatusDisplay(item.managed?.status).icon || undefined"
        variant="flat"
        class="font-weight-bold"
      >
        {{ getStatusDisplay(item.managed?.status).label }}
      </v-chip>
    </template>

    <template #item.managed.last_check_time="{ item }">
      <div class="text-caption text-grey">{{ formatTime(item.managed?.last_check_time) || '-' }}</div>
    </template>

    <template #item.actions="{ item }">
      <div class="d-flex justify-center">
        <v-btn
          icon="mdi-tag-edit-outline"
          variant="text"
          size="x-small"
          color="info"
          title="编辑标签"
          @click="emit('edit-tags', item)"
        ></v-btn>
        <v-btn
          icon="mdi-eye-outline"
          variant="text"
          size="x-small"
          color="grey-darken-1"
          title="查看详情"
          @click="emit('view-cookie', item)"
        ></v-btn>
        <v-btn
          icon="mdi-shield-check-outline"
          variant="text"
          size="x-small"
          color="primary"
          title="即时检查"
          @click="emit('check-cookie', item)"
        ></v-btn>
        <v-btn
          icon="mdi-refresh"
          variant="text"
          size="x-small"
          color="warning"
          title="强制刷新"
          @click="emit('refresh-cookie', item)"
        ></v-btn>
        <v-btn
          icon="mdi-delete-outline"
          variant="text"
          size="x-small"
          color="error"
          title="移除账号"
          @click="emit('delete-cookie', item)"
        ></v-btn>
      </div>
    </template>

    <template #no-data>
      <v-sheet class="pa-12 text-center" color="transparent">
        <v-icon size="64" color="grey-lighten-1" icon="mdi-account-off-outline" class="mb-4"></v-icon>
        <div class="text-h6 text-grey">
          {{ hasTagFilter ? '当前筛选条件下没有账号' : '暂无已保存的账号' }}
        </div>
        <v-btn
          v-if="hasTagFilter"
          color="primary"
          class="mt-4"
          prepend-icon="mdi-filter-off-outline"
          @click="emit('clear-filter')"
        >
          清空筛选
        </v-btn>
        <v-btn
          v-else
          color="primary"
          class="mt-4"
          prepend-icon="mdi-plus"
          @click="emit('start-scan')"
        >
          添加首个账号
        </v-btn>
      </v-sheet>
    </template>
  </v-data-table>
</template>

<style scoped>
.font-monospace {
  font-family: 'Roboto Mono', 'Fira Code', monospace !important;
}

.lh-1 {
  line-height: 1.2 !important;
}

.scale-08 {
  transform: scale(0.8);
  transform-origin: center;
}

.account-id {
  font-size: 0.7rem;
}
</style>
