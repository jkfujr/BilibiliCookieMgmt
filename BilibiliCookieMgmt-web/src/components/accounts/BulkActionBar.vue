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
</script>

<template>
  <v-expand-transition>
    <div v-if="selectedCount > 0" class="bulk-action-bar px-4 py-3">
      <div class="d-flex flex-wrap align-center ga-2">
        <v-chip color="primary" variant="tonal" size="small" prepend-icon="mdi-checkbox-marked-outline">
          已选 {{ selectedCount }} 项
        </v-chip>

        <v-spacer></v-spacer>

        <v-btn
          color="primary"
          variant="tonal"
          size="small"
          prepend-icon="mdi-shield-check-outline"
          :loading="loading"
          @click="emit('check-selected')"
        >
          状态检查
        </v-btn>
        <v-btn
          color="warning"
          variant="tonal"
          size="small"
          prepend-icon="mdi-autorenew"
          :loading="loading"
          @click="emit('refresh-selected')"
        >
          自动刷新
        </v-btn>
        <v-btn
          color="success"
          variant="tonal"
          size="small"
          prepend-icon="mdi-toggle-switch-outline"
          :loading="loading"
          @click="emit('toggle-selected-enabled')"
        >
          开启/禁用
        </v-btn>
        <v-btn
          color="info"
          variant="tonal"
          size="small"
          prepend-icon="mdi-tag-plus-outline"
          :disabled="loading"
          @click="emit('edit-selected-tags')"
        >
          标签
        </v-btn>
        <v-btn
          color="error"
          variant="tonal"
          size="small"
          prepend-icon="mdi-delete-outline"
          :disabled="loading"
          @click="emit('delete-selected')"
        >
          删除
        </v-btn>
        <v-btn
          variant="text"
          size="small"
          prepend-icon="mdi-close"
          :disabled="loading"
          @click="emit('clear-selection')"
        >
          清空选择
        </v-btn>
      </div>
    </div>
  </v-expand-transition>
</template>

<style scoped>
.bulk-action-bar {
  background: rgb(var(--v-theme-surface));
  border-bottom: 1px solid rgba(var(--v-border-color), var(--v-border-opacity));
}
</style>
