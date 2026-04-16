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
</script>

<template>
  <v-dialog
    :model-value="modelValue"
    max-width="560"
    @update:model-value="emit('update:modelValue', $event)"
  >
    <v-card prepend-icon="mdi-tag-multiple-outline" title="编辑账号标签">
      <v-card-text>
        <div class="text-body-2 mb-4">
          为账号 <span class="font-weight-bold">{{ target?.managed?.username || target?.managed?.DedeUserID }}</span> 设置标签。
        </div>
        <v-combobox
          :model-value="tagEditorInput"
          :items="availableTags"
          label="账号标签"
          placeholder="输入标签后按回车确认"
          hint="留空后保存即可清空标签"
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
          保存标签
        </v-btn>
      </v-card-actions>
    </v-card>
  </v-dialog>
</template>
