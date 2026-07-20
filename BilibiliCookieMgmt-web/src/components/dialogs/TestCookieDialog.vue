<script setup>
import { computed } from 'vue'

import { parseCookieLines, validateCookieLines } from '../../utils/cookieInputUtils'

const props = defineProps({
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

const parsedItems = computed(() => parseCookieLines(props.cookieInput))
const validationError = computed(() => validateCookieLines(parsedItems.value))
</script>

<template>
  <v-dialog
    :model-value="modelValue"
    max-width="800"
    @update:model-value="emit('update:modelValue', $event)"
  >
    <v-card prepend-icon="mdi-flask-outline" title="手动 Cookie 测试">
      <v-card-text>
        <v-textarea
          :model-value="cookieInput"
          label="Cookie 列表"
          variant="outlined"
          rows="10"
          no-resize
          placeholder="SESSDATA=...; DedeUserID=..."
          :hint="`已识别 ${parsedItems.length} 条`"
          persistent-hint
          :error-messages="validationError && cookieInput ? [validationError] : []"
          @update:model-value="emit('update:cookieInput', $event)"
        ></v-textarea>
      </v-card-text>
      <v-card-actions>
        <v-spacer></v-spacer>
        <v-btn color="grey" variant="text" @click="emit('update:modelValue', false)">关闭</v-btn>
        <v-btn
          color="primary"
          variant="flat"
          prepend-icon="mdi-play"
          :disabled="Boolean(validationError)"
          @click="emit('submit')"
        >开始验证</v-btn>
      </v-card-actions>
    </v-card>
  </v-dialog>
</template>
