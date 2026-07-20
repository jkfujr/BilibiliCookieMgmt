import test from 'node:test'
import assert from 'node:assert/strict'

import {
  clearTagFilterState,
  getToggledEnabledValue,
  normalizeAccountIds,
  syncSelectedAccountIds,
} from '../BilibiliCookieMgmt-web/src/utils/accountUtils.js'
import { getAccountStatusDisplays } from '../BilibiliCookieMgmt-web/src/utils/accountStatusUtils.js'
import { getQrLoginPollState, getQrLoginStatusText, QR_LOGIN_POLL_STATE } from '../BilibiliCookieMgmt-web/src/utils/qrLoginUtils.js'
import { runManagedRequest } from '../BilibiliCookieMgmt-web/src/utils/requestUtils.js'
import { buildUnauthorizedSessionState } from '../BilibiliCookieMgmt-web/src/utils/sessionUtils.js'
import { parseCookieLines, validateCookieLines } from '../BilibiliCookieMgmt-web/src/utils/cookieInputUtils.js'
import { taskProgress } from '../BilibiliCookieMgmt-web/src/utils/taskUtils.js'

test('clearTagFilterState 只清空标签选择，不重置匹配模式', () => {
  const nextState = clearTagFilterState('all')
  assert.deepEqual(nextState, {
    selectedTags: [],
    matchMode: 'all',
  })
})

test('normalizeAccountIds 会去空值、去重并转成字符串', () => {
  assert.deepEqual(normalizeAccountIds(['1001', 1002, '1001', '', null, ' 1003 ']), ['1001', '1002', '1003'])
})

test('syncSelectedAccountIds 会清理不存在的选中账号', () => {
  const accounts = [
    { managed: { DedeUserID: '1001' } },
    { managed: { DedeUserID: 1002 } },
  ]

  assert.deepEqual(syncSelectedAccountIds(['1001', '1002', '404'], accounts), ['1001', '1002'])
})

test('getToggledEnabledValue 会按当前启用状态取反', () => {
  assert.equal(getToggledEnabledValue({ managed: { is_enabled: true } }), false)
  assert.equal(getToggledEnabledValue({ managed: { is_enabled: false } }), true)
  assert.equal(getToggledEnabledValue({ managed: {} }), true)
})

test('getAccountStatusDisplays 会显示有效账号基础状态', () => {
  assert.deepEqual(getAccountStatusDisplays({ managed: { status: 'valid' } }).map((item) => item.label), ['有效'])
})

test('getAccountStatusDisplays 会为有效风控账号追加风控状态', () => {
  assert.deepEqual(
    getAccountStatusDisplays({ managed: { status: 'valid', risk_controlled: true } }).map((item) => item.label),
    ['有效', '风控']
  )
})

test('getAccountStatusDisplays 不为无效账号显示遗留风控状态', () => {
  assert.deepEqual(
    getAccountStatusDisplays({ managed: { status: 'invalid', risk_controlled: true } }).map((item) => item.label),
    ['无效']
  )
})

test('getAccountStatusDisplays 会兼容缺失状态', () => {
  assert.deepEqual(getAccountStatusDisplays({ managed: {} }).map((item) => item.label), ['未知'])
})

test('二维码轮询状态按当前 API 契约判断成功、过期与等待', () => {
  assert.equal(getQrLoginPollState({ managed: { DedeUserID: '1001' } }), QR_LOGIN_POLL_STATE.SUCCESS)
  assert.equal(getQrLoginPollState({ code: 86038 }), QR_LOGIN_POLL_STATE.EXPIRED)
  assert.equal(getQrLoginPollState({ code: 86101, message: '已扫码, 等待确认' }), QR_LOGIN_POLL_STATE.PENDING)
  assert.equal(getQrLoginStatusText({ code: 86101, message: '已扫码, 等待确认' }), '已扫码, 等待确认')
})

test('buildUnauthorizedSessionState 返回清理后的登录态', () => {
  assert.deepEqual(buildUnauthorizedSessionState(), {
    token: '',
    loginTokenInput: '',
    loginDialog: true,
  })
})

test('runManagedRequest 成功时支持局部替换、整表刷新和成功提示', async () => {
  const loadingStates = []
  const messages = []
  const refreshed = []
  let replacedDoc = null

  const result = await runManagedRequest({
    request: async () => ({
      doc: {
        managed: {
          DedeUserID: '1001',
          tags: ['主力号'],
        },
      },
    }),
    showMsg: (text, color) => {
      messages.push({ text, color })
    },
    successMessage: '操作成功',
    setLoading: (value) => {
      loadingStates.push(value)
    },
    replaceAccount: (doc) => {
      replacedDoc = doc
    },
    pickUpdatedAccount: (payload) => payload.doc,
    refreshAccounts: async () => {
      refreshed.push('refresh')
    },
    shouldRefresh: true,
  })

  assert.equal(result.ok, true)
  assert.deepEqual(replacedDoc, {
    managed: {
      DedeUserID: '1001',
      tags: ['主力号'],
    },
  })
  assert.deepEqual(refreshed, ['refresh'])
  assert.deepEqual(loadingStates, [true, false])
  assert.deepEqual(messages, [{ text: '操作成功', color: 'success' }])
})

test('runManagedRequest 失败时输出错误提示并执行收尾逻辑', async () => {
  const loadingStates = []
  const messages = []
  const traces = []

  const result = await runManagedRequest({
    request: async () => {
      throw new Error('boom')
    },
    showMsg: (text, color) => {
      messages.push({ text, color })
    },
    errorMessage: '请求失败',
    setLoading: (value) => {
      loadingStates.push(value)
    },
    onFinally: async () => {
      traces.push('finally')
    },
  })

  assert.equal(result.ok, false)
  assert.deepEqual(loadingStates, [true, false])
  assert.deepEqual(messages, [{ text: '请求失败', color: 'error' }])
  assert.deepEqual(traces, ['finally'])
})

test('runManagedRequest 遇到 401 时不重复提示错误', async () => {
  const messages = []

  const result = await runManagedRequest({
    request: async () => {
      const error = new Error('unauthorized')
      error.response = { status: 401 }
      throw error
    },
    showMsg: (text, color) => {
      messages.push({ text, color })
    },
    errorMessage: '请求失败',
  })

  assert.equal(result.ok, false)
  assert.deepEqual(messages, [])
})

test('parseCookieLines 保留原始行号、重复项并忽略空行', () => {
  assert.deepEqual(parseCookieLines('A=1\r\n\r\n B=2 \nA=1'), [
    { line_number: 1, cookie: 'A=1' },
    { line_number: 3, cookie: 'B=2' },
    { line_number: 4, cookie: 'A=1' },
  ])
})

test('validateCookieLines 拒绝空输入和超长单行', () => {
  assert.equal(validateCookieLines([]), '请输入至少一条 Cookie')
  assert.match(validateCookieLines([{ line_number: 7, cookie: 'x'.repeat(8193) }]), /第 7 行/)
})

test('taskProgress 汇总所有终态数量', () => {
  assert.equal(taskProgress({ total: 10, succeeded: 3, invalid: 2, failed: 1, skipped: 1, cancelled: 1 }), 80)
})
