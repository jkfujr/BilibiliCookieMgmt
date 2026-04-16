<script setup>
defineProps({
  modelValue: {
    type: Boolean,
    required: true,
  },
  status: {
    type: String,
    required: true,
  },
  canvasBinder: {
    type: Function,
    required: true,
  },
})

const emit = defineEmits(['update:modelValue', 'close'])
</script>

<template>
  <v-dialog
    :model-value="modelValue"
    max-width="400"
    persistent
    @update:model-value="emit('update:modelValue', $event)"
  >
    <v-card>
      <v-card-title class="text-center pt-6">
        <div class="text-h5 font-weight-bold">扫码登录</div>
      </v-card-title>
      <v-card-text class="text-center pb-6">
        <v-sheet class="d-inline-block pa-2 border rounded-lg mb-4">
          <canvas :ref="canvasBinder"></canvas>
        </v-sheet>
        <v-alert
          :color="status.includes('失效') ? 'error' : 'info'"
          variant="tonal"
          density="compact"
          class="text-body-2"
        >
          {{ status }}
        </v-alert>
      </v-card-text>
      <v-card-actions class="bg-grey-lighten-4">
        <v-spacer></v-spacer>
        <v-btn color="grey-darken-1" variant="text" @click="emit('close')">取消扫码</v-btn>
      </v-card-actions>
    </v-card>
  </v-dialog>
</template>
