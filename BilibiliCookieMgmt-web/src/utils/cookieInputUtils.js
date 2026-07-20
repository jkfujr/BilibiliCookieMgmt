export const COOKIE_BATCH_LIMIT = 5000
export const COOKIE_LINE_LIMIT = 8192
export const COOKIE_PAYLOAD_LIMIT = 25 * 1024 * 1024

export const parseCookieLines = (input) => {
  return String(input || '')
    .split(/\r\n|\n|\r/)
    .map((cookie, index) => ({ line_number: index + 1, cookie: cookie.trim() }))
    .filter((item) => item.cookie)
}

export const validateCookieLines = (items) => {
  if (!items.length) {
    return '请输入至少一条 Cookie'
  }
  if (items.length > COOKIE_BATCH_LIMIT) {
    return `单次最多校验 ${COOKIE_BATCH_LIMIT} 条 Cookie`
  }
  const oversized = items.find((item) => item.cookie.length > COOKIE_LINE_LIMIT)
  if (oversized) {
    return `第 ${oversized.line_number} 行超过 ${COOKIE_LINE_LIMIT} 字符`
  }
  const bytes = new TextEncoder().encode(items.map((item) => item.cookie).join('\n')).length
  if (bytes > COOKIE_PAYLOAD_LIMIT) {
    return 'Cookie 原文总大小超过 25 MiB'
  }
  return ''
}
