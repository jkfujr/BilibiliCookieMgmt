<script setup>
import { ref, computed, onMounted, watch, nextTick } from 'vue'
import axios from 'axios'
import QRCode from 'qrcode'

// State
const drawer = ref(true)
const accounts = ref([])
const loading = ref(false)
const screenshotMode = ref(false)
const token = ref(localStorage.getItem('api_token') || '')
const loginTokenInput = ref('')

// Global Feedback (Snackbar)
const snackbar = ref({
  show: false,
  text: '',
  color: 'success'
})

const showMsg = (text, color = 'success') => {
  snackbar.value = { show: true, text, color }
}

// Dialogs
const loginDialog = ref(false)
const qrDialog = ref(false)
const cookieDialog = ref(false)
const testCookieDialog = ref(false)
const deleteDialog = ref(false)

// Dialog Data
const qrCodeCanvas = ref(null)
const qrStatus = ref('')
const qrTimer = ref(null)
const currentCookie = ref({ simple: '', complete: '' })
const testCookieInput = ref('')
const deleteTarget = ref(null)
const currentCookieTab = ref('simple')

// Stats
const stats = computed(() => {
  const total = accounts.value.length
  let valid = 0, expired = 0, invalid = 0
  accounts.value.forEach(acc => {
    const status = acc.managed?.status || 'unknown'
    if (status === 'valid') valid++
    else if (status === 'expired') expired++
    else if (status === 'invalid') invalid++
  })
  return { total, valid, expired, invalid }
})

// Table Headers
const headers = [
  { title: '用户信息', key: 'user_info', align: 'start', sortable: false },
  { title: '是否启用', key: 'is_enabled', align: 'center' },
  { title: '更新时间', key: 'managed.update_time', align: 'center' },
  { title: '过期时间', key: 'expire_time', align: 'center' },
  { title: '登录状态', key: 'managed.status', align: 'center' },
  { title: '检查时间', key: 'managed.last_check_time', align: 'center' },
  { title: '操作', key: 'actions', align: 'center', sortable: false },
]

// Axios Instance
const api = axios.create({
  baseURL: '/api',
})

api.interceptors.request.use(config => {
  if (token.value) {
    config.headers.Authorization = `Bearer ${token.value}`
  }
  return config
})

api.interceptors.response.use(
  response => response,
  error => {
    if (error.response?.status === 401) {
      token.value = ''
      localStorage.removeItem('api_token')
      loginDialog.value = true
      showMsg('会话已过期，请重新登录', 'error')
    }
    return Promise.reject(error)
  }
)

// Formatting
const formatTime = (value) => {
  if (!value) return ''
  const date = new Date(typeof value === 'number' && value < 1e12 ? value * 1000 : value)
  if (isNaN(date.getTime())) return ''
  return date.toLocaleString()
}

// Methods
const fetchAccounts = async () => {
  if (!token.value) return
  loading.value = true
  try {
    const res = await api.get('/v1/cookies/')
    accounts.value = Array.isArray(res.data) ? res.data : []
  } catch (err) {
    showMsg('获取账号列表失败', 'error')
  } finally {
    loading.value = false
  }
}

const handleLogin = () => {
  if (loginTokenInput.value) {
    token.value = loginTokenInput.value
    localStorage.setItem('api_token', token.value)
    loginDialog.value = false
    showMsg('登录成功')
    fetchAccounts()
  }
}

const checkAllCookies = async () => {
  try {
    const res = await api.post('/v1/cookies/check?all=true')
    if (res.data?.ok) {
      showMsg('所有 Cookie 已检查完成')
      fetchAccounts()
    } else {
      showMsg(res.data?.message || '检查失败', 'error')
    }
  } catch (err) {
    showMsg('检查请求失败', 'error')
  }
}

const refreshAllCookies = async () => {
  try {
    const res = await api.post('/v1/cookies/refresh?all=true')
    if (res.data?.ok) {
      showMsg('需要刷新的 Cookie 已刷新')
      fetchAccounts()
    } else {
      showMsg(res.data?.message || '刷新失败', 'error')
    }
  } catch (err) {
    showMsg('刷新请求失败', 'error')
  }
}

// QR Login Logic
const startScan = async () => {
  if (!token.value) {
    loginDialog.value = true
    return
  }
  try {
    const res = await api.get('/v1/auth/tv/qrcode')
    const { auth_code, url, qrcode_url } = res.data
    const qrUrl = qrcode_url || url
    
    qrDialog.value = true
    qrStatus.value = '请使用 Bilibili 手机端扫码'
    
    await nextTick()
    QRCode.toCanvas(qrCodeCanvas.value, qrUrl, { width: 200 }, (err) => {
      if (err) console.error(err)
    })

    if (qrTimer.value) clearInterval(qrTimer.value)
    qrTimer.value = setInterval(() => verifyLogin(auth_code), 3000)
  } catch (err) {
    showMsg('获取二维码失败', 'error')
  }
}

const verifyLogin = async (auth_code) => {
  try {
    const res = await api.get('/v1/auth/tv/poll', { params: { auth_code } })
    const data = res.data
    
    if (data.code === 0 || (!data.code && data.mid)) {
        showMsg('扫码登录成功！')
        closeQrDialog()
        fetchAccounts()
    } else if (data.code === 86038) {
        qrStatus.value = '二维码已失效，请重新获取'
        clearInterval(qrTimer.value)
    }
  } catch (err) {
    console.error(err)
  }
}

const closeQrDialog = () => {
  qrDialog.value = false
  if (qrTimer.value) {
    clearInterval(qrTimer.value)
    qrTimer.value = null
  }
}

// Single Account Actions
const toggleEnabled = async (item) => {
  const newValue = !item.managed?.is_enabled
  try {
    if (!item.managed) item.managed = {}
    item.managed.is_enabled = newValue
    await api.patch(`/v1/cookies/${item.managed.DedeUserID}/enabled`, { is_enabled: newValue })
    showMsg(`用户 ${item.managed.username} 已${newValue ? '启用' : '禁用'}`)
  } catch (err) {
    item.managed.is_enabled = !newValue
    showMsg('状态切换失败', 'error')
  }
}

const viewCookie = async (item) => {
  try {
    const res = await api.get(`/v1/cookies/${item.managed.DedeUserID}`)
    currentCookie.value = {
      simple: res.data.managed?.header_string || '',
      complete: JSON.stringify(res.data, null, 4)
    }
    cookieDialog.value = true
  } catch (err) {
    showMsg('获取 Cookie 详情失败', 'error')
  }
}

const checkCookie = async (item) => {
  try {
    const res = await api.post('/v1/cookies/check?all=false', { ids: [item.managed.DedeUserID] })
    const detail = res.data.details?.find(d => d.DedeUserID === item.managed.DedeUserID)
    const ok = detail ? !!detail.ok : true
    showMsg(ok ? 'Cookie 有效！' : `Cookie 无效: ${detail?.message || ''}`, ok ? 'success' : 'warning')
    fetchAccounts()
  } catch (err) {
    showMsg('检查请求失败', 'error')
  }
}

const refreshCookie = async (item) => {
  try {
    const res = await api.post('/v1/cookies/refresh?all=false', { ids: [item.managed.DedeUserID] })
    if (res.data?.ok) {
      showMsg('刷新成功')
      fetchAccounts()
    } else {
      showMsg(res.data?.message || '刷新失败', 'error')
    }
  } catch (err) {
    showMsg('刷新请求失败', 'error')
  }
}

const deleteCookie = async () => {
  if (!deleteTarget.value) return
  try {
    const res = await api.delete(`/v1/cookies/${deleteTarget.value.managed.DedeUserID}`)
    if (res.data?.ok || res.data?.deleted) {
      showMsg('删除成功')
      fetchAccounts()
      deleteDialog.value = false
    } else {
      showMsg(res.data?.message || '删除失败', 'error')
    }
  } catch (err) {
    showMsg('删除请求失败', 'error')
  }
}

const testCookie = async () => {
  if (!testCookieInput.value) return
  try {
    const res = await api.post('/v1/cookies/test', { cookie: testCookieInput.value })
    if (res.data?.is_valid) {
      showMsg('该 Cookie 有效！')
    } else {
      showMsg(`该 Cookie 无效: ${res.data?.message}`, 'error')
    }
  } catch (err) {
    showMsg('测试请求失败', 'error')
  }
}

const getExpireTime = (item) => {
  const cookies = item.raw?.cookie_info?.cookies || []
  const sess = cookies.find(c => c.name === 'SESSDATA')
  return sess?.expires
}

onMounted(() => {
  if (token.value) {
    fetchAccounts()
  } else {
    loginDialog.value = true
  }
})
</script>

<template>
  <v-app>
    <!-- 全局消息条 -->
    <v-snackbar v-model="snackbar.show" :color="snackbar.color" :timeout="3000" location="top">
      {{ snackbar.text }}
      <template v-slot:actions>
        <v-btn variant="text" @click="snackbar.show = false">关闭</v-btn>
      </template>
    </v-snackbar>

    <v-navigation-drawer v-model="drawer" width="280" elevation="2">
      <v-sheet class="pa-6 text-center" color="primary">
        <v-icon size="48" icon="mdi-cookie" class="mb-2"></v-icon>
        <div class="text-h6 font-weight-bold">Bili Cookie Mgmt</div>
      </v-sheet>
      
      <v-list nav density="comfortable" class="mt-2">
        <v-list-item v-if="!token" @click="loginDialog = true" prepend-icon="mdi-login" title="管理登录" color="primary"></v-list-item>
        <v-list-item v-else title="服务已连接" prepend-icon="mdi-cloud-check" subtitle="API Token 已就绪" disabled color="success"></v-list-item>
        
        <v-divider class="my-4"></v-divider>
        
        <v-list-subheader>账号操作</v-list-subheader>
        <v-list-item @click="startScan" prepend-icon="mdi-qrcode-scan" title="扫码添加账号" color="success" class="mb-2"></v-list-item>
        
        <v-list-subheader>全局管理</v-list-subheader>
        <v-list-item @click="checkAllCookies" prepend-icon="mdi-shield-check-outline" title="批量状态检查"></v-list-item>
        <v-list-item @click="refreshAllCookies" prepend-icon="mdi-autorenew" title="批量自动刷新"></v-list-item>
        
        <v-divider class="my-4"></v-divider>
        
        <v-list-subheader>辅助工具</v-list-subheader>
        <v-list-item @click="testCookieDialog = true" prepend-icon="mdi-flask-outline" title="手动测试 Cookie"></v-list-item>
        <v-list-item @click="screenshotMode = !screenshotMode" :prepend-icon="screenshotMode ? 'mdi-eye-off-outline' : 'mdi-eye-outline'" :title="screenshotMode ? '截图模式：开启' : '截图模式：关闭'" :color="screenshotMode ? 'warning' : ''"></v-list-item>
      </v-list>

      <template v-slot:append>
        <div class="pa-4">
          <v-btn block variant="tonal" size="small" prepend-icon="mdi-github" href="https://github.com/nICEnnnnnnnn/BilibiliCookieMgmt" target="_blank">
            Open Source
          </v-btn>
        </div>
      </template>
    </v-navigation-drawer>

    <v-main class="bg-grey-lighten-4">
      <!-- 顶部应用栏 -->
      <v-app-bar elevation="1">
        <v-app-bar-nav-icon @click="drawer = !drawer"></v-app-bar-nav-icon>
        <v-app-bar-title>账号状态概览</v-app-bar-title>
        <v-spacer></v-spacer>
        <v-btn icon="mdi-refresh" @click="fetchAccounts" :loading="loading"></v-btn>
      </v-app-bar>

      <v-container fluid class="pa-6">
        <!-- 统计面板 -->
        <v-row class="mb-6">
          <v-col cols="12" sm="6" md="3">
            <v-card elevation="2" class="h-100">
              <div class="d-flex flex-row align-center justify-space-between pa-6">
                <div>
                  <div class="text-overline mb-1 text-medium-emphasis">账号总数</div>
                  <div class="text-h3 font-weight-bold text-primary">{{ stats.total }}</div>
                </div>
                <v-avatar size="64" color="primary" variant="tonal" rounded="lg">
                  <v-icon size="36" icon="mdi-account-group"></v-icon>
                </v-avatar>
              </div>
            </v-card>
          </v-col>

          <v-col cols="12" sm="6" md="3">
            <v-card elevation="2" class="h-100">
              <div class="d-flex flex-row align-center justify-space-between pa-6">
                <div>
                  <div class="text-overline mb-1 text-medium-emphasis">有效状态</div>
                  <div class="text-h3 font-weight-bold text-success">{{ stats.valid }}</div>
                </div>
                <v-avatar size="64" color="success" variant="tonal" rounded="lg">
                  <v-icon size="36" icon="mdi-check-circle"></v-icon>
                </v-avatar>
              </div>
            </v-card>
          </v-col>

          <v-col cols="12" sm="6" md="3">
            <v-card elevation="2" class="h-100">
              <div class="d-flex flex-row align-center justify-space-between pa-6">
                <div>
                  <div class="text-overline mb-1 text-medium-emphasis">即将过期</div>
                  <div class="text-h3 font-weight-bold text-warning">{{ stats.expired }}</div>
                </div>
                <v-avatar size="64" color="warning" variant="tonal" rounded="lg">
                  <v-icon size="36" icon="mdi-clock-alert"></v-icon>
                </v-avatar>
              </div>
            </v-card>
          </v-col>

          <v-col cols="12" sm="6" md="3">
            <v-card elevation="2" class="h-100">
              <div class="d-flex flex-row align-center justify-space-between pa-6">
                <div>
                  <div class="text-overline mb-1 text-medium-emphasis">已失效</div>
                  <div class="text-h3 font-weight-bold text-error">{{ stats.invalid }}</div>
                </div>
                <v-avatar size="64" color="error" variant="tonal" rounded="lg">
                  <v-icon size="36" icon="mdi-alert-circle"></v-icon>
                </v-avatar>
              </div>
            </v-card>
          </v-col>
        </v-row>

        <!-- 数据表格 -->
        <v-card elevation="2">
          <v-data-table :headers="headers" :items="accounts" :loading="loading" hover density="compact">
            <!-- 用户信息列 -->
            <template v-slot:item.user_info="{ item, index }">
              <div class="d-flex flex-row align-center py-1">
                <v-avatar color="grey-lighten-2" size="24" class="mr-2">
                    <v-icon icon="mdi-account" size="16"></v-icon>
                </v-avatar>
                <div class="d-flex flex-column">
                  <div class="text-body-2 font-weight-bold lh-1">{{ screenshotMode ? `用户_${index + 1}` : (item.managed?.username || '未知用户') }}</div>
                  <div class="text-caption text-grey-darken-1 font-monospace lh-1" style="font-size: 0.7rem;">{{ screenshotMode ? '********' : item.managed?.DedeUserID }}</div>
                </div>
              </div>
            </template>

            <!-- 启用开关 -->
            <template v-slot:item.is_enabled="{ item }">
              <v-switch
                :model-value="item.managed?.is_enabled"
                @update:model-value="toggleEnabled(item)"
                color="success"
                hide-details
                density="compact"
                inset
                class="scale-08"
              ></v-switch>
            </template>

            <!-- 时间格式化 -->
            <template v-slot:item.managed.update_time="{ item }">
              <div class="text-caption">{{ formatTime(item.managed?.update_time) }}</div>
            </template>

            <template v-slot:item.expire_time="{ item }">
              <div class="text-caption">{{ formatTime(getExpireTime(item)) }}</div>
            </template>

            <!-- 状态标签 -->
            <template v-slot:item.managed.status="{ item }">
              <v-chip
                v-if="item.managed?.status === 'valid'"
                color="success"
                size="x-small"
                prepend-icon="mdi-check"
                variant="flat"
                class="font-weight-bold"
              >有效</v-chip>
              <v-chip
                v-else-if="item.managed?.status === 'expired'"
                color="warning"
                size="x-small"
                prepend-icon="mdi-clock-outline"
                variant="flat"
                class="font-weight-bold"
              >过期</v-chip>
              <v-chip
                v-else-if="item.managed?.status === 'invalid'"
                color="error"
                size="x-small"
                prepend-icon="mdi-close-circle-outline"
                variant="flat"
                class="font-weight-bold"
              >无效</v-chip>
              <v-chip v-else color="grey" size="x-small" variant="flat" class="font-weight-bold">未知</v-chip>
            </template>

            <template v-slot:item.managed.last_check_time="{ item }">
              <div class="text-caption text-grey">{{ formatTime(item.managed?.last_check_time) || '-' }}</div>
            </template>

            <!-- 操作按钮 -->
            <template v-slot:item.actions="{ item }">
              <div class="d-flex justify-center">
                <v-btn icon="mdi-eye-outline" variant="text" size="x-small" color="grey-darken-1" @click="viewCookie(item)" title="查看详情"></v-btn>
                <v-btn icon="mdi-shield-check-outline" variant="text" size="x-small" color="primary" @click="checkCookie(item)" title="即时检查"></v-btn>
                <v-btn icon="mdi-refresh" variant="text" size="x-small" color="warning" @click="refreshCookie(item)" title="强制刷新"></v-btn>
                <v-btn icon="mdi-delete-outline" variant="text" size="x-small" color="error" @click="deleteTarget = item; deleteDialog = true" title="移除账号"></v-btn>
              </div>
            </template>

            <!-- 空状态插槽 -->
            <template v-slot:no-data>
              <v-sheet class="pa-12 text-center" color="transparent">
                <v-icon size="64" color="grey-lighten-1" icon="mdi-account-off-outline" class="mb-4"></v-icon>
                <div class="text-h6 text-grey">暂无已保存的账号</div>
                <v-btn color="primary" class="mt-4" prepend-icon="mdi-plus" @click="startScan">添加首个账号</v-btn>
              </v-sheet>
            </template>
          </v-data-table>
        </v-card>
      </v-container>
    </v-main>

    <!-- 登录对话框 -->
    <v-dialog v-model="loginDialog" persistent max-width="400">
      <v-card prepend-icon="mdi-lock-outline" title="身份验证">
        <v-card-text>
          <div class="text-body-2 mb-4">请输入管理 API Token 以继续操作。</div>
          <v-text-field label="API Token" v-model="loginTokenInput" type="password" variant="outlined" density="comfortable" @keyup.enter="handleLogin"></v-text-field>
        </v-card-text>
        <v-card-actions>
          <v-spacer></v-spacer>
          <v-btn color="primary" variant="flat" block @click="handleLogin">验证并连接</v-btn>
        </v-card-actions>
      </v-card>
    </v-dialog>

    <!-- 扫码登录对话框 -->
    <v-dialog v-model="qrDialog" max-width="400" persistent @after-leave="closeQrDialog">
      <v-card>
        <v-card-title class="text-center pt-6">
          <div class="text-h5 font-weight-bold">扫码登录</div>
        </v-card-title>
        <v-card-text class="text-center pb-6">
          <v-sheet class="d-inline-block pa-2 border rounded-lg mb-4">
            <canvas ref="qrCodeCanvas"></canvas>
          </v-sheet>
          <v-alert :color="qrStatus.includes('失效') ? 'error' : 'info'" variant="tonal" density="compact" class="text-body-2">
            {{ qrStatus }}
          </v-alert>
        </v-card-text>
        <v-card-actions class="bg-grey-lighten-4">
          <v-spacer></v-spacer>
          <v-btn color="grey-darken-1" variant="text" @click="closeQrDialog">取消扫码</v-btn>
        </v-card-actions>
      </v-card>
    </v-dialog>

    <!-- Cookie 详情对话框 -->
    <v-dialog v-model="cookieDialog" max-width="800">
      <v-card title="Cookie 凭据详情">
        <v-tabs v-model="currentCookieTab" color="primary" align-tabs="title">
          <v-tab value="simple">标准 Header</v-tab>
          <v-tab value="complete">原始 JSON 数据</v-tab>
        </v-tabs>

        <v-window v-model="currentCookieTab">
          <v-window-item value="simple">
            <v-card-text>
              <v-textarea v-model="currentCookie.simple" readonly auto-grow rows="8" variant="filled" class="font-monospace text-body-2"></v-textarea>
              <v-btn block color="primary" variant="tonal" class="mt-2" prepend-icon="mdi-content-copy" @click="navigator.clipboard.writeText(currentCookie.simple); showMsg('已复制到剪贴板')">复制 Header 字符串</v-btn>
            </v-card-text>
          </v-window-item>
          <v-window-item value="complete">
            <v-card-text>
              <v-textarea v-model="currentCookie.complete" readonly auto-grow rows="12" variant="filled" class="font-monospace text-caption"></v-textarea>
            </v-card-text>
          </v-window-item>
        </v-window>
        <v-card-actions>
          <v-spacer></v-spacer>
          <v-btn color="primary" @click="cookieDialog = false">完成</v-btn>
        </v-card-actions>
      </v-card>
    </v-dialog>

    <!-- 测试 Cookie 对话框 -->
    <v-dialog v-model="testCookieDialog" max-width="600">
      <v-card prepend-icon="mdi-flask-outline" title="手动 Cookie 测试">
        <v-card-text>
          <div class="text-body-2 mb-4">在此输入原始 Cookie 字符串，系统将验证其对 Bilibili API 的有效性。</div>
          <v-textarea v-model="testCookieInput" label="粘贴 Cookie 字符串" variant="outlined" rows="5" placeholder="SESSDATA=...; DedeUserID=..."></v-textarea>
        </v-card-text>
        <v-card-actions>
          <v-spacer></v-spacer>
          <v-btn color="grey" variant="text" @click="testCookieDialog = false">关闭</v-btn>
          <v-btn color="primary" variant="flat" prepend-icon="mdi-magnify" @click="testCookie">开始验证</v-btn>
        </v-card-actions>
      </v-card>
    </v-dialog>
    
    <!-- 删除确认对话框 -->
    <v-dialog v-model="deleteDialog" max-width="400">
      <v-card prepend-icon="mdi-alert-outline" title="确认移除账号">
        <v-card-text>
          确定要从系统中永久移除用户 <span class="font-weight-bold text-error">{{ deleteTarget?.managed?.username }}</span> 吗？
          此操作将同步停止该账号的所有自动刷新任务。
        </v-card-text>
        <v-card-actions>
          <v-spacer></v-spacer>
          <v-btn color="grey" variant="text" @click="deleteDialog = false">取消</v-btn>
          <v-btn color="error" variant="flat" prepend-icon="mdi-delete" @click="deleteCookie">确认移除</v-btn>
        </v-card-actions>
      </v-card>
    </v-dialog>
  </v-app>
</template>

<style>
.font-monospace {
  font-family: 'Roboto Mono', 'Fira Code', monospace !important;
}
.lh-1 {
  line-height: 1.2 !important;
}
.scale-08 {
  transform: scale(0.8);
  transform-origin: center;
}
</style>