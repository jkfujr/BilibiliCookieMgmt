<script setup>
defineProps({
  drawer: {
    type: Boolean,
    required: true,
  },
  hasToken: {
    type: Boolean,
    required: true,
  },
  screenshotMode: {
    type: Boolean,
    required: true,
  },
})

const emit = defineEmits([
  'update:drawer',
  'open-login',
  'start-scan',
  'check-all',
  'refresh-all',
  'open-test',
  'toggle-screenshot',
])
</script>

<template>
  <v-navigation-drawer
    :model-value="drawer"
    width="280"
    elevation="2"
    @update:model-value="emit('update:drawer', $event)"
  >
    <v-sheet class="pa-6 text-center" color="primary">
      <v-icon size="48" icon="mdi-cookie" class="mb-2"></v-icon>
      <div class="text-h6 font-weight-bold">Bili Cookie Mgmt</div>
    </v-sheet>

    <v-list nav density="comfortable" class="mt-2">
      <v-list-item
        v-if="!hasToken"
        prepend-icon="mdi-login"
        title="管理登录"
        color="primary"
        @click="emit('open-login')"
      ></v-list-item>
      <v-list-item
        v-else
        title="服务已连接"
        prepend-icon="mdi-cloud-check"
        subtitle="API Token 已就绪"
        disabled
        color="success"
      ></v-list-item>

      <v-divider class="my-4"></v-divider>

      <v-list-subheader>账号操作</v-list-subheader>
      <v-list-item
        prepend-icon="mdi-qrcode-scan"
        title="扫码添加账号"
        color="success"
        class="mb-2"
        @click="emit('start-scan')"
      ></v-list-item>

      <v-list-subheader>全局管理</v-list-subheader>
      <v-list-item
        prepend-icon="mdi-shield-check-outline"
        title="批量状态检查"
        @click="emit('check-all')"
      ></v-list-item>
      <v-list-item
        prepend-icon="mdi-autorenew"
        title="批量自动刷新"
        @click="emit('refresh-all')"
      ></v-list-item>

      <v-divider class="my-4"></v-divider>

      <v-list-subheader>辅助工具</v-list-subheader>
      <v-list-item
        prepend-icon="mdi-flask-outline"
        title="手动测试 Cookie"
        @click="emit('open-test')"
      ></v-list-item>
      <v-list-item
        :prepend-icon="screenshotMode ? 'mdi-eye-off-outline' : 'mdi-eye-outline'"
        :title="screenshotMode ? '截图模式：开启' : '截图模式：关闭'"
        :color="screenshotMode ? 'warning' : ''"
        @click="emit('toggle-screenshot')"
      ></v-list-item>
    </v-list>

    <template #append>
      <div class="pa-4">
        <v-btn
          block
          variant="tonal"
          size="small"
          prepend-icon="mdi-github"
          href="https://github.com/jkfujr/BilibiliCookieMgmt"
          target="_blank"
        >
          Open Source
        </v-btn>
      </div>
    </template>
  </v-navigation-drawer>
</template>
