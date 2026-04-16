<script setup>
defineProps({
  modelValue: {
    type: Boolean,
    required: true,
  },
  target: {
    type: Object,
    default: null,
  },
})

const emit = defineEmits(['update:modelValue', 'confirm', 'cancel'])
</script>

<template>
  <v-dialog
    :model-value="modelValue"
    max-width="400"
    @update:model-value="emit('update:modelValue', $event)"
  >
    <v-card prepend-icon="mdi-alert-outline" title="确认移除账号">
      <v-card-text>
        确定要从系统中永久移除用户 <span class="font-weight-bold text-error">{{ target?.managed?.username }}</span> 吗？
        此操作将同步停止该账号的所有自动刷新任务。
      </v-card-text>
      <v-card-actions>
        <v-spacer></v-spacer>
        <v-btn color="grey" variant="text" @click="emit('cancel')">取消</v-btn>
        <v-btn color="error" variant="flat" prepend-icon="mdi-delete" @click="emit('confirm')">确认移除</v-btn>
      </v-card-actions>
    </v-card>
  </v-dialog>
</template>
