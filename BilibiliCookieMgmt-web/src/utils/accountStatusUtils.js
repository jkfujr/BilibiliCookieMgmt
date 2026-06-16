const baseStatusDisplays = {
  valid: {
    key: 'valid',
    color: 'success',
    icon: 'mdi-check',
    label: '有效',
  },
  expired: {
    key: 'expired',
    color: 'warning',
    icon: 'mdi-clock-outline',
    label: '过期',
  },
  invalid: {
    key: 'invalid',
    color: 'error',
    icon: 'mdi-close-circle-outline',
    label: '无效',
  },
  unknown: {
    key: 'unknown',
    color: 'grey',
    icon: '',
    label: '未知',
  },
}

const riskControlDisplay = {
  key: 'risk_controlled',
  color: 'warning',
  icon: 'mdi-alert-outline',
  label: '风控',
}

export const getAccountStatusDisplay = (status) => {
  return baseStatusDisplays[status] || baseStatusDisplays.unknown
}

export const getAccountStatusDisplays = (account) => {
  const status = account?.managed?.status || 'unknown'
  const displays = [getAccountStatusDisplay(status)]

  if (status === 'valid' && account?.managed?.risk_controlled === true) {
    displays.push(riskControlDisplay)
  }

  return displays
}
