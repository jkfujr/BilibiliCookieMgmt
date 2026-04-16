<script setup>
import { computed } from 'vue'

const props = defineProps({
  stats: {
    type: Object,
    required: true,
  },
})

const cards = computed(() => {
  return [
    {
      key: 'total',
      title: '账号总数',
      value: props.stats.total,
      color: 'primary',
      icon: 'mdi-account-group',
    },
    {
      key: 'valid',
      title: '有效状态',
      value: props.stats.valid,
      color: 'success',
      icon: 'mdi-check-circle',
    },
    {
      key: 'expired',
      title: '即将过期',
      value: props.stats.expired,
      color: 'warning',
      icon: 'mdi-clock-alert',
    },
    {
      key: 'invalid',
      title: '已失效',
      value: props.stats.invalid,
      color: 'error',
      icon: 'mdi-alert-circle',
    },
  ]
})
</script>

<template>
  <v-row class="mb-6">
    <v-col
      v-for="card in cards"
      :key="card.key"
      cols="12"
      sm="6"
      md="3"
    >
      <v-card elevation="2" class="h-100">
        <div class="d-flex flex-row align-center justify-space-between pa-6">
          <div>
            <div class="text-overline mb-1 text-medium-emphasis">{{ card.title }}</div>
            <div :class="`text-h3 font-weight-bold text-${card.color}`">{{ card.value }}</div>
          </div>
          <v-avatar size="64" :color="card.color" variant="tonal" rounded="lg">
            <v-icon size="36" :icon="card.icon"></v-icon>
          </v-avatar>
        </div>
      </v-card>
    </v-col>
  </v-row>
</template>
