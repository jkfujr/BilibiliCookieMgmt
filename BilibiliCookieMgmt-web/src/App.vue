<script setup>
import { ref } from 'vue'

import { createApiClient } from './api/client'
import AccountTable from './components/accounts/AccountTable.vue'
import StatsCards from './components/dashboard/StatsCards.vue'
import TagFilterBar from './components/dashboard/TagFilterBar.vue'
import CookieDetailDialog from './components/dialogs/CookieDetailDialog.vue'
import DeleteConfirmDialog from './components/dialogs/DeleteConfirmDialog.vue'
import LoginDialog from './components/dialogs/LoginDialog.vue'
import QrLoginDialog from './components/dialogs/QrLoginDialog.vue'
import TagEditorDialog from './components/dialogs/TagEditorDialog.vue'
import TestCookieDialog from './components/dialogs/TestCookieDialog.vue'
import AppSidebar from './components/layout/AppSidebar.vue'
import { useCookieDashboard } from './composables/useCookieDashboard'
import { useQrLogin } from './composables/useQrLogin'
import { useSession } from './composables/useSession'

const drawer = ref(true)
const snackbar = ref({
  show: false,
  text: '',
  color: 'success',
})

const showMsg = (text, color = 'success') => {
  snackbar.value = {
    show: true,
    text,
    color,
  }
}

const {
  token,
  loginTokenInput,
  loginDialog,
  hasToken,
  getToken,
  openLoginDialog,
  applyLoginToken,
  handleUnauthorized,
} = useSession({ showMsg })

const apiClient = createApiClient({
  getToken,
  onUnauthorized: handleUnauthorized,
})

const {
  availableTags,
  filteredAccounts,
  loading,
  screenshotMode,
  selectedTags,
  stats,
  tagMatchMode,
  cookieDialog,
  currentCookie,
  currentCookieTab,
  tagDialog,
  tagTarget,
  tagEditorInput,
  testCookieDialog,
  testCookieInput,
  deleteDialog,
  deleteTarget,
  fetchAccounts,
  clearTagFilter,
  toggleScreenshotMode,
  checkAllCookies,
  refreshAllCookies,
  toggleEnabled,
  openTagDialog,
  closeTagDialog,
  saveTags,
  closeCookieDialog,
  viewCookie,
  copyContent,
  checkCookie,
  refreshCookie,
  requestDelete,
  closeDeleteDialog,
  deleteCookie,
  openTestCookieDialog,
  testCookie,
} = useCookieDashboard({
  apiClient,
  token,
  showMsg,
})

const {
  qrDialog,
  qrStatus,
  bindQrCodeCanvas,
  startScan,
  closeQrDialog,
} = useQrLogin({
  apiClient,
  hasToken,
  openLoginDialog,
  showMsg,
  onLoginSuccess: fetchAccounts,
})

const submitLogin = () => {
  if (!loginTokenInput.value.trim()) {
    showMsg('请输入 API Token', 'error')
    return
  }

  if (applyLoginToken()) {
    showMsg('登录成功')
  }
}

const updateSelectedTags = (value) => {
  selectedTags.value = value
}

const updateTagMatchMode = (value) => {
  tagMatchMode.value = value || 'any'
}

const updateLoginDialog = (value) => {
  loginDialog.value = value
}

const updateQrDialog = (value) => {
  if (value) {
    qrDialog.value = true
    return
  }
  closeQrDialog()
}

const updateCookieDialog = (value) => {
  if (value) {
    cookieDialog.value = true
    return
  }
  closeCookieDialog()
}

const updateTagDialog = (value) => {
  if (value) {
    tagDialog.value = true
    return
  }
  closeTagDialog()
}

const updateDeleteDialog = (value) => {
  if (value) {
    deleteDialog.value = true
    return
  }
  closeDeleteDialog()
}
</script>

<template>
  <v-app>
    <v-snackbar
      v-model="snackbar.show"
      :color="snackbar.color"
      :timeout="3000"
      location="top"
    >
      {{ snackbar.text }}
      <template #actions>
        <v-btn variant="text" @click="snackbar.show = false">关闭</v-btn>
      </template>
    </v-snackbar>

    <AppSidebar
      :drawer="drawer"
      :has-token="hasToken"
      :screenshot-mode="screenshotMode"
      @update:drawer="drawer = $event"
      @open-login="openLoginDialog"
      @start-scan="startScan"
      @check-all="checkAllCookies"
      @refresh-all="refreshAllCookies"
      @open-test="openTestCookieDialog"
      @toggle-screenshot="toggleScreenshotMode"
    />

    <v-main class="bg-grey-lighten-4">
      <v-app-bar elevation="1">
        <v-app-bar-nav-icon @click="drawer = !drawer"></v-app-bar-nav-icon>
        <v-app-bar-title>账号状态概览</v-app-bar-title>
        <v-spacer></v-spacer>
        <v-btn icon="mdi-refresh" :loading="loading" @click="fetchAccounts"></v-btn>
      </v-app-bar>

      <v-container fluid class="pa-6">
        <StatsCards :stats="stats" />

        <TagFilterBar
          :selected-tags="selectedTags"
          :available-tags="availableTags"
          :match-mode="tagMatchMode"
          @update:selected-tags="updateSelectedTags"
          @update:match-mode="updateTagMatchMode"
          @clear="clearTagFilter"
        />

        <v-card elevation="2">
          <AccountTable
            :items="filteredAccounts"
            :loading="loading"
            :screenshot-mode="screenshotMode"
            :has-tag-filter="selectedTags.length > 0"
            @toggle-enabled="toggleEnabled"
            @edit-tags="openTagDialog"
            @view-cookie="viewCookie"
            @check-cookie="checkCookie"
            @refresh-cookie="refreshCookie"
            @delete-cookie="requestDelete"
            @clear-filter="clearTagFilter"
            @start-scan="startScan"
          />
        </v-card>
      </v-container>
    </v-main>

    <LoginDialog
      :model-value="loginDialog"
      :token-input="loginTokenInput"
      @update:model-value="updateLoginDialog"
      @update:token-input="loginTokenInput = $event"
      @submit="submitLogin"
    />

    <QrLoginDialog
      :model-value="qrDialog"
      :status="qrStatus"
      :canvas-binder="bindQrCodeCanvas"
      @update:model-value="updateQrDialog"
      @close="closeQrDialog"
    />

    <CookieDetailDialog
      :model-value="cookieDialog"
      :cookie="currentCookie"
      :current-tab="currentCookieTab"
      @update:model-value="updateCookieDialog"
      @update:current-tab="currentCookieTab = $event"
      @copy="copyContent"
    />

    <TagEditorDialog
      :model-value="tagDialog"
      :target="tagTarget"
      :available-tags="availableTags"
      :tag-editor-input="tagEditorInput"
      @update:model-value="updateTagDialog"
      @update:tag-editor-input="tagEditorInput = $event"
      @save="saveTags"
      @cancel="closeTagDialog"
    />

    <TestCookieDialog
      v-model="testCookieDialog"
      :cookie-input="testCookieInput"
      @update:cookie-input="testCookieInput = $event"
      @submit="testCookie"
    />

    <DeleteConfirmDialog
      :model-value="deleteDialog"
      :target="deleteTarget"
      @update:model-value="updateDeleteDialog"
      @confirm="deleteCookie"
      @cancel="closeDeleteDialog"
    />
  </v-app>
</template>
