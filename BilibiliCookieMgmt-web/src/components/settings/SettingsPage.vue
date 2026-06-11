<script setup>
import { onMounted, ref } from 'vue'

import { getSettings, updateSettings } from '../../api/settingsApi'

const props = defineProps({
  apiClient: {
    type: Object,
    required: true,
  },
})

const emit = defineEmits(['saved', 'error'])

const settings = ref(null)
const loading = ref(false)
const saving = ref(false)
const apiTokenInput = ref('')
const gotifyTokenInput = ref('')
const clearApiToken = ref(false)
const clearGotifyToken = ref(false)

const numberRules = [
  (value) => Number.isInteger(Number(value)) && Number(value) > 0 || '请输入正整数',
]

const loadSettings = async () => {
  loading.value = true
  try {
    settings.value = await getSettings(props.apiClient)
    apiTokenInput.value = ''
    gotifyTokenInput.value = ''
    clearApiToken.value = false
    clearGotifyToken.value = false
  } catch (error) {
    emit('error', '获取设置失败')
  } finally {
    loading.value = false
  }
}

const normalizeNumber = (value) => Number(value)

const buildPayload = () => {
  const payload = JSON.parse(JSON.stringify(settings.value))

  payload.PORT = normalizeNumber(payload.PORT)
  payload.GOTIFY.priority = normalizeNumber(payload.GOTIFY.priority)
  payload.SCHEDULER.COOKIE_CHECK.interval_seconds = normalizeNumber(payload.SCHEDULER.COOKIE_CHECK.interval_seconds)
  payload.SCHEDULER.COOKIE_REFRESH.interval_seconds = normalizeNumber(payload.SCHEDULER.COOKIE_REFRESH.interval_seconds)
  payload.SCHEDULER.COOKIE_REFRESH.scan_interval_seconds = normalizeNumber(payload.SCHEDULER.COOKIE_REFRESH.scan_interval_seconds)
  payload.SCHEDULER.BILI_TICKET_REFRESH.interval_seconds = normalizeNumber(payload.SCHEDULER.BILI_TICKET_REFRESH.interval_seconds)
  payload.SCHEDULER.RISK_CONTROL_CHECK.interval_seconds = normalizeNumber(payload.SCHEDULER.RISK_CONTROL_CHECK.interval_seconds)

  payload.API_TOKEN.token = {}
  if (clearApiToken.value) {
    payload.API_TOKEN.token.value = ''
  } else if (apiTokenInput.value) {
    payload.API_TOKEN.token.value = apiTokenInput.value
  }

  payload.GOTIFY.token = {}
  if (clearGotifyToken.value) {
    payload.GOTIFY.token.value = ''
  } else if (gotifyTokenInput.value) {
    payload.GOTIFY.token.value = gotifyTokenInput.value
  }

  return payload
}

const saveSettings = async () => {
  if (!settings.value) {
    return
  }

  saving.value = true
  try {
    const payload = buildPayload()
    const result = await updateSettings(props.apiClient, payload)
    settings.value = result.settings
    emit('saved', {
      result,
      apiToken: Object.prototype.hasOwnProperty.call(payload.API_TOKEN.token, 'value') ? payload.API_TOKEN.token.value : null,
    })
    apiTokenInput.value = ''
    gotifyTokenInput.value = ''
    clearApiToken.value = false
    clearGotifyToken.value = false
  } catch (error) {
    emit('error', error?.response?.data?.detail || '保存设置失败')
  } finally {
    saving.value = false
  }
}

onMounted(loadSettings)
</script>

<template>
  <div>
    <div class="d-flex align-center justify-space-between mb-6">
      <div>
        <div class="text-h5 font-weight-bold">系统设置</div>
        <div class="text-body-2 text-medium-emphasis">运行中安全项会立即生效，基础项保存后需重启。</div>
      </div>
      <div class="d-flex ga-2">
        <v-btn
          variant="tonal"
          prepend-icon="mdi-refresh"
          :loading="loading"
          @click="loadSettings"
        >
          重新加载
        </v-btn>
        <v-btn
          color="primary"
          prepend-icon="mdi-content-save"
          :loading="saving"
          :disabled="!settings"
          @click="saveSettings"
        >
          保存
        </v-btn>
      </div>
    </div>

    <v-progress-linear
      v-if="loading"
      indeterminate
      color="primary"
      class="mb-4"
    ></v-progress-linear>

    <v-row v-if="settings" dense>
      <v-col cols="12" lg="6">
        <v-card elevation="2" class="mb-4">
          <v-card-title class="d-flex align-center ga-2">
            <v-icon icon="mdi-server-outline"></v-icon>
            基础
          </v-card-title>
          <v-card-text>
            <v-row dense>
              <v-col cols="12" md="6">
                <v-text-field
                  v-model="settings.HOST"
                  label="HOST"
                  variant="outlined"
                  density="comfortable"
                ></v-text-field>
              </v-col>
              <v-col cols="12" md="6">
                <v-text-field
                  v-model.number="settings.PORT"
                  label="PORT"
                  type="number"
                  variant="outlined"
                  density="comfortable"
                  :rules="numberRules"
                ></v-text-field>
              </v-col>
              <v-col cols="12">
                <v-text-field
                  v-model="settings.STORAGE.cookie_dir"
                  label="Cookie 存储目录"
                  variant="outlined"
                  density="comfortable"
                  prepend-inner-icon="mdi-folder-outline"
                ></v-text-field>
              </v-col>
            </v-row>
          </v-card-text>
        </v-card>

        <v-card elevation="2" class="mb-4">
          <v-card-title class="d-flex align-center ga-2">
            <v-icon icon="mdi-lock-outline"></v-icon>
            鉴权
          </v-card-title>
          <v-card-text>
            <v-switch
              v-model="settings.API_TOKEN.enable"
              color="primary"
              label="启用 API Token"
              hide-details
              inset
              class="mb-3"
            ></v-switch>
            <v-alert
              :color="settings.API_TOKEN.token.configured ? 'success' : 'warning'"
              variant="tonal"
              density="compact"
              class="mb-4"
            >
              {{ settings.API_TOKEN.token.configured ? '当前已配置 API Token' : '当前未配置 API Token' }}
            </v-alert>
            <v-text-field
              v-model="apiTokenInput"
              label="新 API Token"
              type="password"
              variant="outlined"
              density="comfortable"
              autocomplete="new-password"
              :disabled="clearApiToken"
            ></v-text-field>
            <v-checkbox
              v-model="clearApiToken"
              label="清空 API Token"
              color="warning"
              density="compact"
              hide-details
            ></v-checkbox>
          </v-card-text>
        </v-card>

        <v-card elevation="2" class="mb-4">
          <v-card-title class="d-flex align-center ga-2">
            <v-icon icon="mdi-bilibili"></v-icon>
            Bili
          </v-card-title>
          <v-card-text>
            <v-switch
              v-model="settings.BILI.bili_ticket_enabled"
              color="primary"
              label="启用 bili_ticket"
              hide-details
              inset
            ></v-switch>
            <v-switch
              v-model="settings.BILI.risk_control_enabled"
              color="primary"
              label="启用风控检测"
              hide-details
              inset
            ></v-switch>
          </v-card-text>
        </v-card>
      </v-col>

      <v-col cols="12" lg="6">
        <v-card elevation="2" class="mb-4">
          <v-card-title class="d-flex align-center ga-2">
            <v-icon icon="mdi-bell-outline"></v-icon>
            通知
          </v-card-title>
          <v-card-text>
            <v-switch
              v-model="settings.GOTIFY.enable"
              color="primary"
              label="启用 Gotify"
              hide-details
              inset
              class="mb-3"
            ></v-switch>
            <v-row dense>
              <v-col cols="12">
                <v-text-field
                  v-model="settings.GOTIFY.url"
                  label="Gotify URL"
                  variant="outlined"
                  density="comfortable"
                  prepend-inner-icon="mdi-web"
                ></v-text-field>
              </v-col>
              <v-col cols="12">
                <v-alert
                  :color="settings.GOTIFY.token.configured ? 'success' : 'warning'"
                  variant="tonal"
                  density="compact"
                  class="mb-4"
                >
                  {{ settings.GOTIFY.token.configured ? '当前已配置 Gotify Token' : '当前未配置 Gotify Token' }}
                </v-alert>
                <v-text-field
                  v-model="gotifyTokenInput"
                  label="新 Gotify Token"
                  type="password"
                  variant="outlined"
                  density="comfortable"
                  autocomplete="new-password"
                  :disabled="clearGotifyToken"
                ></v-text-field>
                <v-checkbox
                  v-model="clearGotifyToken"
                  label="清空 Gotify Token"
                  color="warning"
                  density="compact"
                  hide-details
                ></v-checkbox>
              </v-col>
              <v-col cols="12" md="4">
                <v-text-field
                  v-model.number="settings.GOTIFY.priority"
                  label="优先级"
                  type="number"
                  variant="outlined"
                  density="comfortable"
                ></v-text-field>
              </v-col>
              <v-col cols="12" md="8">
                <v-text-field
                  v-model="settings.GOTIFY.title"
                  label="标题"
                  variant="outlined"
                  density="comfortable"
                ></v-text-field>
              </v-col>
            </v-row>
          </v-card-text>
        </v-card>

        <v-card elevation="2" class="mb-4">
          <v-card-title class="d-flex align-center ga-2">
            <v-icon icon="mdi-timer-cog-outline"></v-icon>
            调度
          </v-card-title>
          <v-card-text>
            <v-row dense>
              <v-col cols="12" md="6">
                <v-switch
                  v-model="settings.SCHEDULER.COOKIE_CHECK.enable"
                  color="primary"
                  label="健康检查"
                  hide-details
                  inset
                ></v-switch>
                <v-text-field
                  v-model.number="settings.SCHEDULER.COOKIE_CHECK.interval_seconds"
                  label="健康检查间隔"
                  type="number"
                  suffix="秒"
                  variant="outlined"
                  density="comfortable"
                  :rules="numberRules"
                ></v-text-field>
              </v-col>
              <v-col cols="12" md="6">
                <v-switch
                  v-model="settings.SCHEDULER.COOKIE_REFRESH.enable"
                  color="primary"
                  label="自动刷新"
                  hide-details
                  inset
                ></v-switch>
                <v-text-field
                  v-model.number="settings.SCHEDULER.COOKIE_REFRESH.interval_seconds"
                  label="刷新阈值"
                  type="number"
                  suffix="秒"
                  variant="outlined"
                  density="comfortable"
                  :rules="numberRules"
                ></v-text-field>
                <v-text-field
                  v-model.number="settings.SCHEDULER.COOKIE_REFRESH.scan_interval_seconds"
                  label="扫描间隔"
                  type="number"
                  suffix="秒"
                  variant="outlined"
                  density="comfortable"
                  :rules="numberRules"
                ></v-text-field>
              </v-col>
              <v-col cols="12" md="6">
                <v-switch
                  v-model="settings.SCHEDULER.BILI_TICKET_REFRESH.enable"
                  color="primary"
                  label="ticket 刷新"
                  hide-details
                  inset
                ></v-switch>
                <v-text-field
                  v-model.number="settings.SCHEDULER.BILI_TICKET_REFRESH.interval_seconds"
                  label="ticket 扫描间隔"
                  type="number"
                  suffix="秒"
                  variant="outlined"
                  density="comfortable"
                  :rules="numberRules"
                ></v-text-field>
              </v-col>
              <v-col cols="12" md="6">
                <v-text-field
                  v-model.number="settings.SCHEDULER.RISK_CONTROL_CHECK.interval_seconds"
                  label="风控检测间隔"
                  type="number"
                  suffix="秒"
                  variant="outlined"
                  density="comfortable"
                  :rules="numberRules"
                ></v-text-field>
              </v-col>
            </v-row>
          </v-card-text>
        </v-card>
      </v-col>
    </v-row>
  </div>
</template>
