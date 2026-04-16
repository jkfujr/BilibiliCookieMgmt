import { nextTick, onBeforeUnmount, ref } from 'vue'
import QRCode from 'qrcode'

import { getTvQrCode, pollTvQrStatus } from '../api/authApi'
import { getQrLoginPollState, getQrLoginStatusText, QR_LOGIN_POLL_STATE } from '../utils/qrLoginUtils'
import { runManagedRequest } from '../utils/requestUtils'

const POLL_INTERVAL_MS = 3000

export const useQrLogin = ({ apiClient, hasToken, openLoginDialog, showMsg, onLoginSuccess } = {}) => {
  const qrDialog = ref(false)
  const qrStatus = ref('')
  const qrLoading = ref(false)
  const qrCodeCanvas = ref(null)
  const qrTimer = ref(null)

  const bindQrCodeCanvas = (element) => {
    qrCodeCanvas.value = element
  }

  const stopPolling = () => {
    if (qrTimer.value) {
      clearInterval(qrTimer.value)
      qrTimer.value = null
    }
  }

  const closeQrDialog = () => {
    qrDialog.value = false
    qrStatus.value = ''
    stopPolling()
  }

  const renderQrCode = async (qrcodeUrl) => {
    await nextTick()

    if (!qrCodeCanvas.value) {
      throw new Error('二维码画布未准备就绪')
    }

    await QRCode.toCanvas(qrCodeCanvas.value, qrcodeUrl, { width: 200 })
  }

  const handlePollResult = async (data) => {
    const pollState = getQrLoginPollState(data)

    if (pollState === QR_LOGIN_POLL_STATE.SUCCESS) {
      closeQrDialog()
      if (typeof showMsg === 'function') {
        showMsg('扫码登录成功！')
      }
      if (typeof onLoginSuccess === 'function') {
        await onLoginSuccess(data)
      }
      return
    }

    if (pollState === QR_LOGIN_POLL_STATE.EXPIRED) {
      qrStatus.value = '二维码已失效，请重新获取'
      stopPolling()
      return
    }

    qrStatus.value = getQrLoginStatusText(data)
  }

  const pollStatus = async (authCode) => {
    try {
      const data = await pollTvQrStatus(apiClient, authCode)
      await handlePollResult(data)
    } catch (error) {
      if (typeof console !== 'undefined') {
        console.error(error)
      }
    }
  }

  const startScan = async () => {
    const authenticated = typeof hasToken === 'function' ? hasToken() : Boolean(hasToken?.value)
    if (!authenticated) {
      if (typeof openLoginDialog === 'function') {
        openLoginDialog()
      }
      return
    }

    const result = await runManagedRequest({
      request: () => getTvQrCode(apiClient),
      showMsg,
      errorMessage: '获取二维码失败',
      setLoading: (value) => {
        qrLoading.value = value
      },
    })

    if (!result.ok) {
      return
    }

    const authCode = result.result?.auth_code
    const qrcodeUrl = result.result?.qrcode_url
    if (!authCode || !qrcodeUrl) {
      if (typeof showMsg === 'function') {
        showMsg('二维码响应缺少必要字段', 'error')
      }
      return
    }

    qrDialog.value = true
    qrStatus.value = '请使用 Bilibili 手机端扫码'

    try {
      await renderQrCode(qrcodeUrl)
    } catch (error) {
      closeQrDialog()
      if (typeof showMsg === 'function') {
        showMsg('二维码绘制失败', 'error')
      }
      return
    }

    stopPolling()
    qrTimer.value = setInterval(() => {
      void pollStatus(authCode)
    }, POLL_INTERVAL_MS)
  }

  onBeforeUnmount(() => {
    stopPolling()
  })

  return {
    qrDialog,
    qrStatus,
    qrLoading,
    bindQrCodeCanvas,
    startScan,
    closeQrDialog,
  }
}
