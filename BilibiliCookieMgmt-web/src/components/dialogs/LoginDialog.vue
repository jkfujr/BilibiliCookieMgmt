<script setup>
defineProps({
  modelValue: {
    type: Boolean,
    required: true,
  },
  tokenInput: {
    type: String,
    required: true,
  },
})

const emit = defineEmits(['update:modelValue', 'update:tokenInput', 'submit'])
</script>

<template>
  <v-dialog
    :model-value="modelValue"
    persistent
    max-width="400"
    @update:model-value="emit('update:modelValue', $event)"
  >
    <v-card prepend-icon="mdi-lock-outline" title="身份验证">
      <v-card-text>
        <div class="text-body-2 mb-4">请输入管理 API Token 以继续操作。</div>
        <v-text-field
          :model-value="tokenInput"
          label="API Token"
          type="password"
          variant="outlined"
          density="comfortable"
          @update:model-value="emit('update:tokenInput', $event)"
          @keyup.enter="emit('submit')"
        ></v-text-field>
      </v-card-text>
      <v-card-actions>
        <v-spacer></v-spacer>
        <v-btn color="primary" variant="flat" block @click="emit('submit')">验证并连接</v-btn>
      </v-card-actions>
    </v-card>
  </v-dialog>
</template>
