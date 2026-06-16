<script setup>
defineProps({
  selectedCount: {
    type: Number,
    required: true,
  },
  loading: {
    type: Boolean,
    required: true,
  },
})

const emit = defineEmits([
  'check-selected',
  'refresh-selected',
  'toggle-selected-enabled',
  'edit-selected-tags',
  'delete-selected',
  'clear-selection',
])

const actionItems = [
  {
    eventName: 'check-selected',
    icon: 'mdi-shield-check-outline',
    color: 'primary',
    tooltip: '检查选中账号状态',
    showLoading: true,
  },
  {
    eventName: 'refresh-selected',
    icon: 'mdi-autorenew',
    color: 'warning',
    tooltip: '自动刷新选中账号',
    showLoading: true,
  },
  {
    eventName: 'toggle-selected-enabled',
    icon: 'mdi-toggle-switch-outline',
    color: 'success',
    tooltip: '开启/禁用选中账号',
    showLoading: true,
  },
  {
    eventName: 'edit-selected-tags',
    icon: 'mdi-tag-plus-outline',
    color: 'info',
    tooltip: '为选中账号追加标签',
    showLoading: false,
  },
  {
    eventName: 'delete-selected',
    icon: 'mdi-delete-outline',
    color: 'error',
    tooltip: '删除选中账号',
    showLoading: false,
  },
]
</script>

<template>
  <v-slide-y-reverse-transition>
    <div
      v-if="selectedCount > 0"
      class="bulk-action-bar"
      role="toolbar"
      aria-label="批量操作"
    >
      <div class="bulk-action-pill">
        <v-tooltip text="清空选择" location="top">
          <template #activator="{ props: tooltipProps }">
            <v-btn
              v-bind="tooltipProps"
              icon="mdi-close"
              variant="text"
              size="small"
              class="bulk-icon-button"
              :disabled="loading"
              aria-label="清空选择"
              @click="emit('clear-selection')"
            ></v-btn>
          </template>
        </v-tooltip>

        <v-chip class="bulk-selected-chip" variant="flat" size="small">
          <span class="bulk-selected-count">{{ selectedCount }}</span>
          <span>项已选</span>
        </v-chip>

        <v-divider vertical class="bulk-action-divider"></v-divider>

        <v-tooltip
          v-for="action in actionItems"
          :key="action.eventName"
          :text="action.tooltip"
          location="top"
        >
          <template #activator="{ props: tooltipProps }">
            <v-btn
              v-bind="tooltipProps"
              :icon="action.icon"
              :color="action.color"
              variant="tonal"
              size="small"
              class="bulk-icon-button"
              :loading="action.showLoading && loading"
              :disabled="!action.showLoading && loading"
              :aria-label="action.tooltip"
              @click="emit(action.eventName)"
            ></v-btn>
          </template>
        </v-tooltip>
      </div>
    </div>
  </v-slide-y-reverse-transition>
</template>

<style scoped>
.bulk-action-bar {
  position: fixed;
  right: var(--v-layout-right, 0px);
  bottom: calc(var(--v-layout-bottom, 0px) + 72px);
  left: var(--v-layout-left, 0px);
  z-index: 1006;
  display: flex;
  justify-content: center;
  padding-inline: 24px;
  pointer-events: none;
}

.bulk-action-pill {
  display: flex;
  align-items: center;
  max-width: min(100%, 640px);
  padding: 8px 10px;
  overflow-x: auto;
  gap: 8px;
  color: rgba(255, 255, 255, 0.92);
  white-space: nowrap;
  pointer-events: auto;
  background: rgba(24, 24, 24, 0.92);
  border: 1px solid rgba(var(--v-border-color), 0.28);
  border-radius: 999px;
  box-shadow: 0 18px 44px rgba(0, 0, 0, 0.34);
  backdrop-filter: blur(14px);
  scrollbar-width: none;
}

.bulk-action-pill::-webkit-scrollbar {
  display: none;
}

.bulk-icon-button {
  flex: 0 0 auto;
}

.bulk-selected-chip {
  flex: 0 0 auto;
  color: rgba(24, 24, 24, 0.9);
  background: rgba(255, 255, 255, 0.96) !important;
}

.bulk-selected-count {
  margin-right: 4px;
  font-weight: 700;
}

.bulk-action-divider {
  align-self: stretch;
  opacity: 0.3;
}

@media (max-width: 600px) {
  .bulk-action-bar {
    bottom: calc(var(--v-layout-bottom, 0px) + 16px);
    padding-inline: 12px;
  }
}
</style>
