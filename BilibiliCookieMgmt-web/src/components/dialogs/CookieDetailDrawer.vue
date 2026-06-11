<script setup>
import { computed } from 'vue'

import { getAccountTags } from '../../utils/accountTagUtils'
import { formatTime, getExpireTime } from '../../utils/accountUtils'

const props = defineProps({
  modelValue: {
    type: Boolean,
    required: true,
  },
  cookie: {
    type: Object,
    required: true,
  },
  currentTab: {
    type: String,
    required: true,
  },
  screenshotMode: {
    type: Boolean,
    default: false,
  },
})

const emit = defineEmits(['update:modelValue', 'update:currentTab', 'copy'])

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

const account = computed(() => props.cookie?.account || {})
const managed = computed(() => account.value?.managed || {})
const tags = computed(() => getAccountTags(account.value))
const status = computed(() => statusMap[managed.value?.status] || statusMap.unknown)
const displayName = computed(() => props.screenshotMode ? '截图用户' : (managed.value?.username || '未知用户'))
const displayId = computed(() => props.screenshotMode ? '114514' : (managed.value?.DedeUserID || '-'))

const formatTimeOrDash = (value) => formatTime(value) || '-'
</script>

<template>
  <v-navigation-drawer
    :model-value="modelValue"
    location="right"
    temporary
    width="520"
    class="cookie-detail-drawer"
    @update:model-value="emit('update:modelValue', $event)"
  >
    <div class="d-flex flex-column h-100">
      <div class="px-5 py-4 d-flex align-center ga-3">
        <v-avatar color="grey-lighten-2" size="40">
          <v-icon icon="mdi-account" size="24"></v-icon>
        </v-avatar>
        <div class="flex-grow-1 min-width-0">
          <div class="text-subtitle-1 font-weight-bold text-truncate">{{ displayName }}</div>
          <div class="text-caption text-medium-emphasis font-monospace">{{ displayId }}</div>
        </div>
        <v-btn
          icon="mdi-close"
          variant="text"
          size="small"
          @click="emit('update:modelValue', false)"
        ></v-btn>
      </div>

      <v-divider></v-divider>

      <div class="pa-5 overflow-y-auto flex-grow-1">
        <div class="d-flex align-center ga-2 mb-4">
          <v-chip
            :color="status.color"
            size="small"
            :prepend-icon="status.icon || undefined"
            variant="flat"
            class="font-weight-bold"
          >
            {{ status.label }}
          </v-chip>
          <v-chip
            :color="managed?.is_enabled ? 'success' : 'grey'"
            size="small"
            variant="tonal"
          >
            {{ managed?.is_enabled ? '已启用' : '已停用' }}
          </v-chip>
        </div>

        <div class="mb-5">
          <div class="text-caption text-medium-emphasis mb-2">标签</div>
          <div class="d-flex flex-wrap ga-1">
            <v-chip
              v-for="tag in tags"
              :key="tag"
              color="info"
              size="x-small"
              variant="tonal"
            >
              {{ tag }}
            </v-chip>
            <v-chip
              v-if="!tags.length"
              color="grey"
              size="x-small"
              variant="outlined"
            >
              无标签
            </v-chip>
          </div>
        </div>

        <v-card variant="tonal" class="mb-5">
          <v-card-title class="text-subtitle-2">时间信息</v-card-title>
          <v-card-text>
            <div class="detail-row">
              <span>SESSDATA 过期</span>
              <span>{{ formatTimeOrDash(getExpireTime(account)) }}</span>
            </div>
            <div class="detail-row">
              <span>加入时间</span>
              <span>{{ formatTimeOrDash(managed?.join_time) }}</span>
            </div>
            <div class="detail-row">
              <span>更新时间</span>
              <span>{{ formatTimeOrDash(managed?.update_time) }}</span>
            </div>
            <div class="detail-row">
              <span>最近检查</span>
              <span>{{ formatTimeOrDash(managed?.last_check_time) }}</span>
            </div>
            <div class="detail-row">
              <span>最近刷新</span>
              <span>{{ formatTimeOrDash(managed?.last_refresh_time) }}</span>
            </div>
          </v-card-text>
        </v-card>

        <v-card variant="outlined">
          <v-tabs
            :model-value="currentTab"
            color="primary"
            @update:model-value="emit('update:currentTab', $event)"
          >
            <v-tab value="simple">标准</v-tab>
            <v-tab value="complete">原始</v-tab>
          </v-tabs>

          <v-window :model-value="currentTab" @update:model-value="emit('update:currentTab', $event)">
            <v-window-item value="simple">
              <v-card-text>
                <v-textarea
                  :model-value="cookie.simple"
                  readonly
                  auto-grow
                  rows="8"
                  variant="filled"
                  class="font-monospace text-body-2"
                ></v-textarea>
                <v-btn
                  block
                  color="primary"
                  variant="tonal"
                  class="mt-2"
                  prepend-icon="mdi-content-copy"
                  @click="emit('copy', cookie.simple)"
                >
                  复制标准 Cookie
                </v-btn>
              </v-card-text>
            </v-window-item>
            <v-window-item value="complete">
              <v-card-text>
                <v-textarea
                  :model-value="cookie.complete"
                  readonly
                  rows="16"
                  variant="filled"
                  class="font-monospace text-caption"
                ></v-textarea>
              </v-card-text>
            </v-window-item>
          </v-window>
        </v-card>
      </div>
    </div>
  </v-navigation-drawer>
</template>

<style scoped>
.font-monospace {
  font-family: 'Roboto Mono', 'Fira Code', monospace !important;
}

.cookie-detail-drawer {
  max-width: 100vw;
}

.detail-row {
  display: flex;
  justify-content: space-between;
  gap: 16px;
  padding: 6px 0;
  font-size: 0.875rem;
}

.detail-row span:first-child {
  color: rgba(var(--v-theme-on-surface), 0.6);
  flex: 0 0 auto;
}

.detail-row span:last-child {
  text-align: right;
  word-break: break-word;
}

.min-width-0 {
  min-width: 0;
}
</style>
