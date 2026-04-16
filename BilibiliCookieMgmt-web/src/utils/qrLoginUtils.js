export const QR_LOGIN_POLL_STATE = {
  SUCCESS: 'success',
  EXPIRED: 'expired',
  PENDING: 'pending',
}

export const getQrLoginPollState = (data) => {
  if (data?.managed) {
    return QR_LOGIN_POLL_STATE.SUCCESS
  }

  if (data?.code === 86038) {
    return QR_LOGIN_POLL_STATE.EXPIRED
  }

  return QR_LOGIN_POLL_STATE.PENDING
}

export const getQrLoginStatusText = (data) => {
  return data?.message || '请在手机端确认登录'
}
