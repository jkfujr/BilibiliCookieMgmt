<script setup>
import { computed } from 'vue'

const props = defineProps({
  modelValue: {
    type: Boolean,
    required: true,
  },
  mode: {
    type: String,
    default: 'single',
  },
  bulkCount: {
    type: Number,
    default: 0,
  },
  target: {
    type: Object,
    default: null,
  },
})

const emit = defineEmits(['update:modelValue', 'confirm', 'cancel'])

const isBulkMode = computed(() => props.mode === 'bulk')
const title = computed(() => isBulkMode.value ? '确认批量移除账号' : '确认移除账号')
const message = computed(() => {
  if (isBulkMode.value) {
    return `确定要从系统中永久移除选中的 ${props.bulkCount} 个账号吗？`
  }

  return `确定要从系统中永久移除用户 ${props.target?.managed?.username || props.target?.managed?.DedeUserID || ''} 吗？`
})
</script>

<template>
  <v-dialog
    :model-value="modelValue"
    max-width="400"
    @update:model-value="emit('update:modelValue', $event)"
  >
    <v-card prepend-icon="mdi-alert-outline" :title="title">
      <v-card-text>
        <span class="font-weight-bold text-error">{{ message }}</span>
        此操作将同步停止相关账号的所有自动刷新任务。
      </v-card-text>
      <v-card-actions>
        <v-spacer></v-spacer>
        <v-btn color="grey" variant="text" @click="emit('cancel')">取消</v-btn>
        <v-btn color="error" variant="flat" prepend-icon="mdi-delete" @click="emit('confirm')">确认移除</v-btn>
      </v-card-actions>
    </v-card>
  </v-dialog>
</template>
