import test from 'node:test'
import assert from 'node:assert/strict'

import {
  extractAvailableTags,
  filterAccountsByTags,
  getAccountTags,
  normalizeTagList,
} from '../BilibiliCookieMgmt-web/src/accountTagUtils.js'


const accounts = [
  {
    managed: {
      DedeUserID: '1001',
      tags: ['主力号', '直播'],
    },
  },
  {
    managed: {
      DedeUserID: '1002',
      tags: ['备用', '直播'],
    },
  },
  {
    managed: {
      DedeUserID: '1003',
      tags: [],
    },
  },
]


test('normalizeTagList 会裁剪空白并去重', () => {
  assert.deepEqual(normalizeTagList([' 主力号 ', '直播', '主力号', '', '  ']), ['主力号', '直播'])
})

test('getAccountTags 会兼容缺失标签字段', () => {
  assert.deepEqual(getAccountTags({ managed: {} }), [])
  assert.deepEqual(getAccountTags({}), [])
})

test('extractAvailableTags 会按首次出现顺序汇总标签', () => {
  assert.deepEqual(extractAvailableTags(accounts), ['主力号', '直播', '备用'])
})

test('filterAccountsByTags 在未选择标签时返回全部账号', () => {
  assert.equal(filterAccountsByTags(accounts, []).length, 3)
})

test('filterAccountsByTags 支持任一匹配', () => {
  const matched = filterAccountsByTags(accounts, ['主力号', '备用'], 'any')
  assert.deepEqual(matched.map((item) => item.managed.DedeUserID), ['1001', '1002'])
})

test('filterAccountsByTags 支持全部匹配', () => {
  const matched = filterAccountsByTags(accounts, ['直播', '备用'], 'all')
  assert.deepEqual(matched.map((item) => item.managed.DedeUserID), ['1002'])
})
