<script setup>
defineProps({
  modelValue: {
    type: Boolean,
    required: true,
  },
  cookie: {
    type: Object,
    required: true,
  },
  currentTab: {
    type: String,
    required: true,
  },
})

const emit = defineEmits(['update:modelValue', 'update:currentTab', 'copy'])
</script>

<template>
  <v-dialog
    :model-value="modelValue"
    max-width="800"
    @update:model-value="emit('update:modelValue', $event)"
  >
    <v-card title="Cookie 凭据详情">
      <v-tabs
        :model-value="currentTab"
        color="primary"
        align-tabs="title"
        @update:model-value="emit('update:currentTab', $event)"
      >
        <v-tab value="simple">标准</v-tab>
        <v-tab value="complete">原始</v-tab>
      </v-tabs>

      <v-window :model-value="currentTab" @update:model-value="emit('update:currentTab', $event)">
        <v-window-item value="simple">
          <v-card-text>
            <v-textarea
              :model-value="cookie.simple"
              readonly
              auto-grow
              rows="8"
              variant="filled"
              class="font-monospace text-body-2"
            ></v-textarea>
            <v-btn
              block
              color="primary"
              variant="tonal"
              class="mt-2"
              prepend-icon="mdi-content-copy"
              @click="emit('copy', cookie.simple)"
            >
              复制
            </v-btn>
          </v-card-text>
        </v-window-item>
        <v-window-item value="complete">
          <v-card-text>
            <v-textarea
              :model-value="cookie.complete"
              readonly
              rows="15"
              variant="filled"
              class="font-monospace text-caption"
            ></v-textarea>
          </v-card-text>
        </v-window-item>
      </v-window>
      <v-card-actions>
        <v-spacer></v-spacer>
        <v-btn color="primary" @click="emit('update:modelValue', false)">完成</v-btn>
      </v-card-actions>
    </v-card>
  </v-dialog>
</template>

<style scoped>
.font-monospace {
  font-family: 'Roboto Mono', 'Fira Code', monospace !important;
}
</style>
