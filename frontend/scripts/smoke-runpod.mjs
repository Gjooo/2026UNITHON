/**
 * 승인된 staging 환경에서 실제 Provider로 한 번만 실행하는 smoke test.
 *
 * 이 명령은 실제 GPU를 만들고 실제 비용을 발생시킨다.
 * CI, `npm test`, pre-commit 어디에도 넣지 않는다.
 */
const GUARD = 'RUN_REAL_RUNPOD_SMOKE'

if (process.env[GUARD] !== 'true') {
  console.error(
    [
      '',
      '  실제 Provider를 호출하는 명령이라 기본적으로 실행하지 않습니다.',
      '  실제 GPU가 생성되고 비용이 발생합니다.',
      '',
      `  실행하려면 ${GUARD}=true 와 SMOKE_API_BASE를 함께 지정하세요.`,
      `    ${GUARD}=true SMOKE_API_BASE=https://staging.example/api/v1 npm run smoke:runpod`,
      '',
    ].join('\n'),
  )
  process.exit(1)
}

const base = process.env.SMOKE_API_BASE
if (!base) {
  console.error('SMOKE_API_BASE가 필요합니다.')
  process.exit(1)
}

const budget = Number(process.env.SMOKE_BUDGET_KRW ?? 10000)
const priority = process.env.SMOKE_PRIORITY ?? 'CHEAPEST'
const timeoutMs = Number(process.env.SMOKE_TIMEOUT_MS ?? 15 * 60 * 1000)

let cookie = ''

async function call(path, init = {}) {
  const res = await fetch(base + path, {
    ...init,
    headers: { 'Content-Type': 'application/json', ...(cookie ? { cookie } : {}), ...init.headers },
  })
  const setCookie = res.headers.get('set-cookie')
  if (setCookie) cookie = setCookie.split(';')[0]
  const text = await res.text()
  const body = text ? JSON.parse(text) : null
  if (!res.ok) throw new Error(`${path} → ${res.status} ${JSON.stringify(body)}`)
  return body
}

const sleep = (ms) => new Promise((r) => setTimeout(r, ms))

const session = await call('/session', { method: 'POST' })
console.log('session ready, allowance:', JSON.stringify(session.executionAllowance))

const job = await call('/jobs', {
  method: 'POST',
  body: JSON.stringify({ maxBudgetKrw: budget, priority }),
})
console.log('job', job.id, '→', job.executionPlan.recommended.gpuType)

// 실행 전 전역 활성 Job이 없어야 한다. 있으면 서버가 거절한다.
await call(`/jobs/${job.id}/start`, { method: 'POST' })
console.log('started. polling…')

const deadline = Date.now() + timeoutMs
let last = null
while (Date.now() < deadline) {
  last = await call(`/jobs/${job.id}`)
  console.log(' ', new Date().toISOString(), last.status)
  if (['COMPLETED', 'FAILED', 'CANCELLED'].includes(last.status)) break
  await sleep(5000)
}

if (!last || !['COMPLETED', 'FAILED', 'CANCELLED'].includes(last.status)) {
  console.error('시간 안에 최종 상태에 도달하지 못했습니다. 자원을 직접 확인하세요.')
  process.exit(1)
}

console.log('\n최종 상태:', last.status)
console.log('종료 코드 :', last.exitCode)
console.log('실패 사유 :', last.failureMessage ?? '없음')
console.log('자원 종료 :', last.podTerminatedAt ?? '확인되지 않음')

// 결과가 무엇이든 자원 종료 확인이 최우선이다.
if (!last.podTerminatedAt) {
  console.error('\n자원 종료가 확인되지 않았습니다. Provider 콘솔에서 직접 정리하세요.')
  process.exit(1)
}
console.log('\n자원 종료 확인됨.')
