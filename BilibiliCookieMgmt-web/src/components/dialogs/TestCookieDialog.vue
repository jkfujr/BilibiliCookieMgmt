<script setup>
defineProps({
  modelValue: {
    type: Boolean,
    required: true,
  },
  cookieInput: {
    type: String,
    required: true,
  },
})

const emit = defineEmits(['update:modelValue', 'update:cookieInput', 'submit'])
</script>

<template>
  <v-dialog
    :model-value="modelValue"
    max-width="600"
    @update:model-value="emit('update:modelValue', $event)"
  >
    <v-card prepend-icon="mdi-flask-outline" title="手动 Cookie 测试">
      <v-card-text>
        <div class="text-body-2 mb-4">在此输入原始 Cookie 字符串，系统将验证其对 Bilibili API 的有效性。</div>
        <v-textarea
          :model-value="cookieInput"
          label="粘贴 Cookie 字符串"
          variant="outlined"
          rows="5"
          placeholder="SESSDATA=...; DedeUserID=..."
          @update:model-value="emit('update:cookieInput', $event)"
        ></v-textarea>
      </v-card-text>
      <v-card-actions>
        <v-spacer></v-spacer>
        <v-btn color="grey" variant="text" @click="emit('update:modelValue', false)">关闭</v-btn>
        <v-btn color="primary" variant="flat" prepend-icon="mdi-magnify" @click="emit('submit')">开始验证</v-btn>
      </v-card-actions>
    </v-card>
  </v-dialog>
</template>
