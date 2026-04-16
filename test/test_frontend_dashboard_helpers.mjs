import test from 'node:test'
import assert from 'node:assert/strict'

import { clearTagFilterState } from '../BilibiliCookieMgmt-web/src/utils/accountUtils.js'
import { getQrLoginPollState, getQrLoginStatusText, QR_LOGIN_POLL_STATE } from '../BilibiliCookieMgmt-web/src/utils/qrLoginUtils.js'
import { runManagedRequest } from '../BilibiliCookieMgmt-web/src/utils/requestUtils.js'
import { buildUnauthorizedSessionState } from '../BilibiliCookieMgmt-web/src/utils/sessionUtils.js'

test('clearTagFilterState 只清空标签选择，不重置匹配模式', () => {
  const nextState = clearTagFilterState('all')
  assert.deepEqual(nextState, {
    selectedTags: [],
    matchMode: 'all',
  })
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
