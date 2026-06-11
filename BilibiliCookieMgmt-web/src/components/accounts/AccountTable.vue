<script setup>
import { computed } from 'vue'

import TagFilterBar from '../dashboard/TagFilterBar.vue'
import { getAccountTags } from '../../utils/accountTagUtils'
import { formatTime, getAccountId, getExpireTime } from '../../utils/accountUtils'

const props = defineProps({
  items: {
    type: Array,
    required: true,
  },
  selectedAccountIds: {
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
  'update:selected-account-ids',
  'update:selected-tags',
  'update:match-mode',
])

const headers = [
  { title: '用户信息', key: 'user_info', align: 'start', sortable: false },
  { title: '标签', key: 'tags', align: 'start', sortable: false },
  { title: 'SESSDATA 过期', key: 'expire_time', align: 'center' },
  { title: '登录状态', key: 'managed.status', align: 'center' },
  { title: '操作', key: 'actions', align: 'end', sortable: false },
]

const selectedValues = computed(() => {
  return props.selectedAccountIds.map((id) => String(id))
})

const isSameAccountId = (left, right) => {
  return String(left || '') === String(right || '')
}

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

const getEnabledText = (account) => {
  return account?.managed?.is_enabled ? '禁用' : '开启'
}

const getEnabledIcon = (account) => {
  return account?.managed?.is_enabled ? 'mdi-toggle-switch-off-outline' : 'mdi-toggle-switch-outline'
}

const getMenuItems = (account) => [
  {
    title: '测试',
    icon: 'mdi-shield-check-outline',
    color: 'primary',
    eventName: 'check-cookie',
  },
  {
    title: getEnabledText(account),
    icon: getEnabledIcon(account),
    color: account?.managed?.is_enabled ? 'warning' : 'success',
    eventName: 'toggle-enabled',
  },
  {
    title: '查看详情',
    icon: 'mdi-eye-outline',
    color: 'grey-darken-1',
    eventName: 'view-cookie',
  },
  {
    title: '编辑标签',
    icon: 'mdi-tag-edit-outline',
    color: 'info',
    eventName: 'edit-tags',
  },
  {
    title: '强制刷新',
    icon: 'mdi-refresh',
    color: 'warning',
    eventName: 'refresh-cookie',
  },
  {
    title: '删除',
    icon: 'mdi-delete-outline',
    color: 'error',
    eventName: 'delete-cookie',
  },
]

const emitRowAction = (eventName, account) => {
  emit(eventName, account)
}
</script>

<template>
  <v-data-table
    :headers="headers"
    :items="items"
    :model-value="selectedValues"
    :loading="loading"
    item-value="managed.DedeUserID"
    :value-comparator="isSameAccountId"
    show-select
    hover
    density="compact"
    @update:model-value="emit('update:selected-account-ids', $event.map((id) => String(id)))"
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

    <template #item.actions="{ item }">
      <div class="d-flex justify-end align-center ga-1 action-cell">
        <v-btn
          prepend-icon="mdi-shield-check-outline"
          variant="tonal"
          size="small"
          color="primary"
          slim
          @click="emit('check-cookie', item)"
        >
          测试
        </v-btn>
        <v-btn
          :prepend-icon="getEnabledIcon(item)"
          variant="tonal"
          size="small"
          :color="item.managed?.is_enabled ? 'warning' : 'success'"
          slim
          @click="emit('toggle-enabled', item)"
        >
          {{ getEnabledText(item) }}
        </v-btn>

        <v-menu location="bottom end">
          <template #activator="{ props: menuProps }">
            <v-btn
              v-bind="menuProps"
              append-icon="mdi-chevron-down"
              variant="text"
              size="small"
            >
              全部
            </v-btn>
          </template>
          <v-list density="compact" min-width="160">
            <v-list-item
              v-for="menuItem in getMenuItems(item)"
              :key="`${getAccountId(item)}-${menuItem.eventName}`"
              :prepend-icon="menuItem.icon"
              :title="menuItem.title"
              :base-color="menuItem.color"
              @click="emitRowAction(menuItem.eventName, item)"
            ></v-list-item>
          </v-list>
        </v-menu>
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

.account-id {
  font-size: 0.7rem;
}

.action-cell {
  min-width: 220px;
}
</style>
