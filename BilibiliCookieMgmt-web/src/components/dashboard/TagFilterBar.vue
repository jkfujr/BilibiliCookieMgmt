<script setup>
import { computed, ref } from 'vue'

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

const menu = ref(false)

const hasActiveFilter = computed(() => props.selectedTags.length > 0)
const hasAnyTag = computed(() => props.availableTags.length > 0 || hasActiveFilter.value)
const matchModeLabel = computed(() => {
  return props.matchMode === 'all' ? '全部匹配' : '任一匹配'
})

const triggerLabel = computed(() => {
  if (!hasActiveFilter.value) {
    return '标签筛选'
  }

  return `已筛选 ${props.selectedTags.length} 个`
})

const panelHint = computed(() => {
  if (!hasActiveFilter.value) {
    return '仅影响当前表格与统计卡片'
  }

  return `${matchModeLabel.value} · ${props.selectedTags.length} 个标签生效中`
})

const removeTag = (tagToRemove) => {
  emit(
    'update:selectedTags',
    props.selectedTags.filter((tag) => tag !== tagToRemove)
  )
}

const clearFilter = () => {
  emit('clear')
  menu.value = false
}
</script>

<template>
  <v-menu
    v-if="hasAnyTag"
    v-model="menu"
    :close-on-content-click="false"
    location="bottom end"
    offset="12"
  >
    <template #activator="{ props: menuProps }">
      <v-badge
        :content="selectedTags.length"
        :model-value="hasActiveFilter"
        color="primary"
        inline
      >
        <v-btn
          v-bind="menuProps"
          :color="hasActiveFilter ? 'primary' : 'grey-darken-1'"
          :variant="hasActiveFilter ? 'tonal' : 'text'"
          icon="mdi-filter-variant"
          size="x-small"
        ></v-btn>
      </v-badge>
    </template>

    <v-card class="tag-filter-popover" elevation="10">
      <v-card-text class="pa-5">
        <div class="d-flex align-start justify-space-between ga-4 mb-4">
          <div>
            <div class="text-subtitle-1 font-weight-bold">标签筛选</div>
            <div class="text-caption text-medium-emphasis">{{ panelHint }}</div>
          </div>
          <v-btn
            icon="mdi-close"
            size="small"
            variant="text"
            color="grey-darken-1"
            @click="menu = false"
          ></v-btn>
        </div>

        <v-autocomplete
          :model-value="selectedTags"
          :items="availableTags"
          label="筛选标签"
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

        <div v-if="hasActiveFilter" class="d-flex flex-wrap ga-2 mt-4">
          <v-chip
            v-for="tag in selectedTags"
            :key="tag"
            color="primary"
            variant="outlined"
            size="small"
            closable
            @click:close="removeTag(tag)"
          >
            {{ tag }}
          </v-chip>
        </div>

        <div class="d-flex flex-wrap align-center justify-space-between ga-3 mt-4">
          <v-btn-toggle
            :model-value="matchMode"
            color="primary"
            mandatory
            divided
            density="comfortable"
            @update:model-value="emit('update:matchMode', $event)"
          >
            <v-btn value="any">任一匹配</v-btn>
            <v-btn value="all">全部匹配</v-btn>
          </v-btn-toggle>

          <div class="d-flex align-center ga-2">
            <v-chip
              v-if="hasActiveFilter"
              color="primary"
              variant="tonal"
              size="small"
            >
              {{ matchModeLabel }}
            </v-chip>
            <v-btn
              v-if="hasActiveFilter"
              variant="text"
              color="primary"
              size="small"
              @click="clearFilter"
            >
              清空
            </v-btn>
            <v-btn
              variant="text"
              color="grey-darken-1"
              size="small"
              @click="menu = false"
            >
              完成
            </v-btn>
          </div>
        </div>
      </v-card-text>
    </v-card>
  </v-menu>
</template>

<style scoped>
.tag-filter-popover {
  width: min(480px, calc(100vw - 32px));
  border: 1px solid rgba(255, 255, 255, 0.08);
  border-radius: 18px;
  backdrop-filter: blur(10px);
}
</style>
