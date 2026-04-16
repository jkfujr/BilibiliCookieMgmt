<script setup>
import { computed, ref, watch } from 'vue'

const props = defineProps({
  selectedTags: {
    type: Array,
    required: true,
  },
  availableTags: {
    type: Array,
    required: true,
  },
  matchMode: {
    type: String,
    required: true,
  },
})

const emit = defineEmits(['update:selectedTags', 'update:matchMode', 'clear'])

const isExpanded = ref(false)

const hasActiveFilter = computed(() => props.selectedTags.length > 0)
const hasAnyTag = computed(() => props.availableTags.length > 0 || hasActiveFilter.value)
const activeSummary = computed(() => {
  if (!hasActiveFilter.value) {
    return '未启用'
  }

  return props.matchMode === 'all'
    ? `全部匹配 ${props.selectedTags.length} 个标签`
    : `任一匹配 ${props.selectedTags.length} 个标签`
})

const shouldShowPanel = computed(() => {
  return hasActiveFilter.value || isExpanded.value
})

const openPanel = () => {
  isExpanded.value = true
}

const closePanel = () => {
  if (!hasActiveFilter.value) {
    isExpanded.value = false
  }
}

const clearFilter = () => {
  emit('clear')
  isExpanded.value = false
}

watch(
  () => props.selectedTags.length,
  (count) => {
    if (count > 0) {
      isExpanded.value = true
      return
    }

    if (!count) {
      isExpanded.value = false
    }
  },
  { immediate: true }
)
</script>

<template>
  <div v-if="hasAnyTag" class="mb-6">
    <div class="d-flex flex-wrap align-center justify-space-between ga-3 mb-3">
      <div class="d-flex flex-wrap align-center ga-2">
        <v-btn
          color="primary"
          variant="tonal"
          prepend-icon="mdi-filter-variant"
          @click="openPanel"
        >
          标签筛选
        </v-btn>
        <v-chip
          v-if="hasActiveFilter"
          color="primary"
          variant="outlined"
          size="small"
        >
          {{ activeSummary }}
        </v-chip>
        <span v-else class="text-caption text-medium-emphasis">未启用标签筛选</span>
      </div>

      <v-btn
        v-if="hasActiveFilter"
        variant="text"
        color="primary"
        size="small"
        @click="clearFilter"
      >
        清空筛选
      </v-btn>
    </div>

    <v-expand-transition>
      <v-card v-if="shouldShowPanel" elevation="2">
        <v-card-text class="pb-2">
          <v-row align="center">
            <v-col cols="12" md="7">
              <v-autocomplete
                :model-value="selectedTags"
                :items="availableTags"
                label="按标签筛选"
                placeholder="选择一个或多个标签"
                multiple
                chips
                closable-chips
                clearable
                variant="outlined"
                density="comfortable"
                hide-details
                no-data-text="暂无可选标签"
                @update:model-value="emit('update:selectedTags', $event)"
              ></v-autocomplete>
            </v-col>
            <v-col cols="12" md="3">
              <v-btn-toggle
                :model-value="matchMode"
                color="primary"
                mandatory
                divided
                class="w-100"
                @update:model-value="emit('update:matchMode', $event)"
              >
                <v-btn value="any">任一匹配</v-btn>
                <v-btn value="all">全部匹配</v-btn>
              </v-btn-toggle>
            </v-col>
            <v-col cols="12" md="2" class="d-flex justify-end">
              <v-btn
                v-if="!hasActiveFilter"
                variant="text"
                color="grey-darken-1"
                @click="closePanel"
              >
                收起
              </v-btn>
            </v-col>
          </v-row>
        </v-card-text>
      </v-card>
    </v-expand-transition>
  </div>
</template>
