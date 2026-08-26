/**
 * fixture와 살아 있는 backend의 응답을 대조한다.
 *
 * 백엔드 OpenAPI가 Job 응답에 response_model을 선언하지 않아(GET /jobs/{id} 200에
 * 스키마 없음) schema 검증만으로는 드리프트를 못 잡는다. 그래서 실제 응답의
 * 필드 구조를 fixture와 직접 비교한다. Provider는 호출하지 않는다.
 */
import fs from 'node:fs'
import path from 'node:path'
import { fileURLToPath } from 'node:url'

const here = path.dirname(fileURLToPath(import.meta.url))
const fixtures = path.join(here, '..', 'src', 'test', 'fixtures')
const base = process.env.CONTRACT_API_BASE ?? 'http://127.0.0.1:8000/api/v1'
const load = (p) => JSON.parse(fs.readFileSync(path.join(fixtures, p), 'utf8'))

/** 값이 아니라 필드 구조와 타입만 본다. 값은 서버가 계산하는 것이므로 비교 대상이 아니다. */
function shape(value, prefix = '') {
  if (Array.isArray(value)) {
    return value.length ? shape(value[0], `${prefix}[]`) : new Set([`${prefix}[]:empty`])
  }
  if (value !== null && typeof value === 'object') {
    const out = new Set()
    for (const [k, v] of Object.entries(value)) {
      const p = prefix ? `${prefix}.${k}` : k
      out.add(`${p}:${v === null ? 'null' : Array.isArray(v) ? 'array' : typeof v}`)
      for (const s of shape(v, p)) out.add(s)
    }
    return out
  }
  return new Set()
}

/** null은 어떤 타입과도 호환된다. nullable 필드가 응답 상태마다 달라지기 때문이다. */
function diff(expected, actual) {
  const nameOf = (e) => e.slice(0, e.lastIndexOf(':'))
  const actualNames = new Map([...actual].map((e) => [nameOf(e), e]))
  const expectedNames = new Map([...expected].map((e) => [nameOf(e), e]))
  const problems = []
  for (const [name, entry] of expectedNames) {
    if (!actualNames.has(name)) problems.push(`  - 응답에 없음: ${name}`)
    else {
      const a = actualNames.get(name)
      const et = entry.slice(entry.lastIndexOf(':') + 1)
      const at = a.slice(a.lastIndexOf(':') + 1)
      if (et !== at && et !== 'null' && at !== 'null') {
        problems.push(`  ~ 타입 다름: ${name} (fixture ${et} / 응답 ${at})`)
      }
    }
  }
  for (const name of actualNames.keys()) {
    if (!expectedNames.has(name)) problems.push(`  + fixture에 없음: ${name}`)
  }
  return problems
}

let cookie = ''
async function call(pathname, init = {}) {
  const res = await fetch(base + pathname, {
    ...init,
    headers: { 'Content-Type': 'application/json', ...(cookie ? { cookie } : {}), ...init.headers },
  })
  const set = res.headers.get('set-cookie')
  if (set) cookie = set.split(';')[0]
  const text = await res.text()
  return { status: res.status, body: text ? JSON.parse(text) : null }
}

let failed = 0
function compare(label, fixture, actual) {
  const problems = diff(shape(fixture), shape(actual))
  if (problems.length) {
    failed += 1
    console.error(`✗ ${label}`)
    problems.forEach((p) => console.error(p))
  } else {
    console.log(`✓ ${label}`)
  }
}

try {
  await fetch(base.replace('/api/v1', '') + '/health')
} catch {
  console.error(
    `\nbackend에 닿지 못했습니다: ${base}\n` +
      `CONTRACT_API_BASE로 주소를 지정하거나 backend를 먼저 띄우세요.\n`,
  )
  process.exit(1)
}

const session = await call('/session', { method: 'POST' })
compare('POST /session', load('session.json'), session.body)

const draft = await call('/jobs', {
  method: 'POST',
  body: JSON.stringify({ maxBudgetKrw: 10000, priority: 'BALANCED' }),
})
compare('POST /jobs (DRAFT)', load('jobs/draft-balanced.json'), draft.body)

const overBudget = await call('/jobs', {
  method: 'POST',
  body: JSON.stringify({ maxBudgetKrw: 500, priority: 'FASTEST' }),
})
compare('POST /jobs (예산 초과 후보 포함)', load('jobs/draft-over-budget.json'), overBudget.body)

const fetched = await call(`/jobs/${draft.body.id}`)
compare('GET /jobs/{id}', load('jobs/draft-balanced.json'), fetched.body)

const noPlan = await call('/jobs', {
  method: 'POST',
  body: JSON.stringify({ maxBudgetKrw: 1, priority: 'CHEAPEST' }),
})
compare('POST /jobs 422', load('errors/no-eligible-plan.json'), noPlan.body)

const badRequest = await call('/jobs', { method: 'POST', body: JSON.stringify({}) })
compare('POST /jobs 400', load('errors/validation-error.json'), badRequest.body)

const noSession = await fetch(`${base}/jobs/00000000-0000-0000-0000-000000000000`)
compare('GET /jobs/{id} 401', load('errors/session-required.json'), await noSession.json())

if (failed) {
  console.error(`\n${failed}건이 fixture와 어긋납니다. UI를 고치기 전에 계약을 먼저 맞추세요.`)
  process.exit(1)
}
console.log('\n모든 fixture가 살아 있는 backend 응답과 일치합니다.')
