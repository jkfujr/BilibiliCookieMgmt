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
  availableTags: {
    type: Array,
    required: true,
  },
  tagEditorInput: {
    type: Array,
    required: true,
  },
})

const emit = defineEmits(['update:modelValue', 'update:tagEditorInput', 'save', 'cancel'])

const isBulkMode = computed(() => props.mode === 'bulk')
const dialogTitle = computed(() => isBulkMode.value ? '批量追加标签' : '编辑账号标签')
const dialogText = computed(() => {
  if (isBulkMode.value) {
    return `为 ${props.bulkCount} 个账号追加标签。`
  }

  return `为账号 ${props.target?.managed?.username || props.target?.managed?.DedeUserID || ''} 设置标签。`
})
const inputHint = computed(() => isBulkMode.value ? '保存后会追加到选中账号，不会清空原标签' : '留空后保存即可清空标签')
const saveText = computed(() => isBulkMode.value ? '追加标签' : '保存标签')
</script>

<template>
  <v-dialog
    :model-value="modelValue"
    max-width="560"
    @update:model-value="emit('update:modelValue', $event)"
  >
    <v-card prepend-icon="mdi-tag-multiple-outline" :title="dialogTitle">
      <v-card-text>
        <div class="text-body-2 mb-4">{{ dialogText }}</div>
        <v-combobox
          :model-value="tagEditorInput"
          :items="availableTags"
          label="账号标签"
          placeholder="输入标签后按回车确认"
          :hint="inputHint"
          persistent-hint
          multiple
          chips
          closable-chips
          clearable
          variant="outlined"
          auto-select-first
          @update:model-value="emit('update:tagEditorInput', $event)"
        ></v-combobox>
      </v-card-text>
      <v-card-actions>
        <v-spacer></v-spacer>
        <v-btn color="grey" variant="text" @click="emit('cancel')">取消</v-btn>
        <v-btn color="primary" variant="flat" prepend-icon="mdi-content-save-outline" @click="emit('save')">
          {{ saveText }}
        </v-btn>
      </v-card-actions>
    </v-card>
  </v-dialog>
</template>
