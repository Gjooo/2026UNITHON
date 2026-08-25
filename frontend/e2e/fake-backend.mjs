/**
 * E2E용 Fake backend. API-spec.md의 상태 머신만 재현하고 Provider를 호출하지 않는다.
 * 응답 값은 src/test/fixtures의 실서버 캡처를 그대로 쓴다.
 */
import http from 'node:http'
import fs from 'node:fs'
import path from 'node:path'
import { fileURLToPath } from 'node:url'
import crypto from 'node:crypto'

const here = path.dirname(fileURLToPath(import.meta.url))
const fixtures = path.join(here, '..', 'src', 'test', 'fixtures')
const load = (p) => JSON.parse(fs.readFileSync(path.join(fixtures, p), 'utf8'))

const DRAFT = load('jobs/draft-balanced.json')
const DRAFT_OVER_BUDGET = load('jobs/draft-over-budget.json')
const PROVISIONING = load('jobs/provisioning.json')
const RUNNING = load('jobs/running.json')
const TERMINATING = load('jobs/terminating.json')
const COMPLETED = load('jobs/completed.json')
const CANCELLED = load('jobs/cancelled.json')
const FAILED = load('jobs/failed.json')
const ERR = {
  noEligiblePlan: load('errors/no-eligible-plan.json'),
  sessionRequired: load('errors/session-required.json'),
  jobNotFound: load('errors/job-not-found.json'),
  demoBusy: load('errors/demo-busy.json'),
  executionUsed: load('errors/execution-already-used.json'),
  validation: load('errors/validation-error.json'),
}

// 스크립트에서 시나리오를 고르기 위한 스위치. 실제 서버에는 없는 테스트 전용 제어다.
const scenario = process.env.FAKE_SCENARIO ?? 'success'
const PROVISION_MS = Number(process.env.FAKE_PROVISION_MS ?? 800)
const RUN_MS = Number(process.env.FAKE_RUN_MS ?? 800)

const sessions = new Map()
const jobs = new Map()

// 테스트가 결과 분기를 고르기 위한 제어. 실제 API에는 없는 __fake 이름공간이다.
let nextOutcome = 'COMPLETED'
let forceBusy = false

function send(res, status, body, headers = {}) {
  const payload = body === null ? '' : JSON.stringify(body)
  res.writeHead(status, { 'Content-Type': 'application/json', ...headers })
  res.end(payload)
}

function sessionOf(req) {
  const raw = req.headers.cookie ?? ''
  const match = /unwork_session=([^;]+)/.exec(raw)
  return match ? sessions.get(match[1]) : undefined
}

function readBody(req) {
  return new Promise((resolve) => {
    let data = ''
    req.on('data', (chunk) => (data += chunk))
    req.on('end', () => {
      try {
        resolve(data ? JSON.parse(data) : {})
      } catch {
        resolve(null)
      }
    })
  })
}

function withStatus(base, status, jobId, constraint) {
  return { ...base, id: jobId, status, constraint: constraint ?? base.constraint }
}

const server = http.createServer(async (req, res) => {
  const url = new URL(req.url, 'http://localhost')
  const { pathname } = url

  if (req.method === 'POST' && pathname === '/__fake/busy') {
    const body = await readBody(req)
    forceBusy = Boolean(body?.busy)
    return send(res, 204, null)
  }

  if (req.method === 'POST' && pathname === '/__fake/outcome') {
    const body = await readBody(req)
    nextOutcome = body?.outcome === 'FAILED' ? 'FAILED' : 'COMPLETED'
    return send(res, 204, null)
  }

  if (req.method === 'POST' && pathname === '/api/v1/session') {
    // 만들거나 **갱신**한다. 기존 쿠키가 유효하면 같은 세션을 유지해야 한다.
    // 매번 새로 발급하면 진행 중인 Job의 소유권이 끊긴다.
    const existing = sessionOf(req)
    const session = existing ?? { token: crypto.randomUUID(), executionUsed: false }
    sessions.set(session.token, session)
    return send(
      res,
      201,
      {
        expiresAt: '2026-09-01T19:47:38Z',
        executionAllowance: { used: session.executionUsed ? 1 : 0, limit: 1 },
      },
      { 'Set-Cookie': `unwork_session=${session.token}; HttpOnly; Path=/; SameSite=Lax` },
    )
  }

  const session = sessionOf(req)
  if (!session) return send(res, 401, ERR.sessionRequired)

  if (req.method === 'POST' && pathname === '/api/v1/jobs') {
    const body = await readBody(req)
    if (!body || typeof body.maxBudgetKrw !== 'number' || !body.priority) {
      return send(res, 400, ERR.validation)
    }
    if (scenario === 'no-eligible-plan' || body.maxBudgetKrw < 450) {
      return send(res, 422, ERR.noEligiblePlan)
    }
    const base = body.maxBudgetKrw < 650 ? DRAFT_OVER_BUDGET : DRAFT
    const id = crypto.randomUUID()
    const job = withStatus(base, 'DRAFT', id, {
      maxBudgetKrw: body.maxBudgetKrw,
      priority: body.priority,
    })
    job.ownerToken = session.token
    jobs.set(id, job)
    return send(res, 201, stripOwner(job))
  }

  const jobMatch = /^\/api\/v1\/jobs\/([^/]+)(\/start|\/cancel)?$/.exec(pathname)
  if (!jobMatch) return send(res, 404, ERR.jobNotFound)

  const job = jobs.get(jobMatch[1])
  if (!job || job.ownerToken !== session.token) return send(res, 404, ERR.jobNotFound)
  const action = jobMatch[2]

  if (req.method === 'GET' && !action) {
    advance(job)
    return send(res, 200, stripOwner(job))
  }

  if (req.method === 'POST' && action === '/start') {
    if (job.status !== 'DRAFT') return send(res, 409, ERR.demoBusy)
    if (forceBusy || scenario === 'demo-busy') return send(res, 409, ERR.demoBusy)
    if (session.executionUsed) return send(res, 409, ERR.executionUsed)
    session.executionUsed = true
    setStatus(job, 'PROVISIONING', PROVISIONING)
    job.provisionAt = Date.now() + PROVISION_MS
    return send(res, 202, { id: job.id, status: 'PROVISIONING' })
  }

  if (req.method === 'POST' && action === '/cancel') {
    if (!['PROVISIONING', 'RUNNING'].includes(job.status)) {
      return send(res, 409, ERR.demoBusy)
    }
    setStatus(job, 'TERMINATING', TERMINATING)
    job.finalStatus = 'CANCELLED'
    job.finalAt = Date.now() + 400
    return send(res, 202, { id: job.id, status: 'TERMINATING' })
  }

  return send(res, 404, ERR.jobNotFound)
})

function stripOwner({ ownerToken, provisionAt, runAt, finalAt, finalStatus, ...rest }) {
  return rest
}

function setStatus(job, status, template) {
  const { id, constraint, ownerToken } = job
  Object.assign(job, template, { id, constraint, ownerToken, status })
}

/** 시간이 지나면 다음 상태로 넘어간다. Provider 호출은 없다. */
function advance(job) {
  const now = Date.now()
  if (job.status === 'PROVISIONING' && job.provisionAt && now >= job.provisionAt) {
    setStatus(job, 'RUNNING', RUNNING)
    job.runAt = now + RUN_MS
    return
  }
  if (job.status === 'RUNNING' && job.runAt && now >= job.runAt) {
    setStatus(job, 'TERMINATING', TERMINATING)
    job.finalStatus = nextOutcome
    job.finalAt = now + 400
    return
  }
  if (job.status === 'TERMINATING' && job.finalAt && now >= job.finalAt) {
    const template =
      job.finalStatus === 'CANCELLED' ? CANCELLED : job.finalStatus === 'FAILED' ? FAILED : COMPLETED
    setStatus(job, job.finalStatus, template)
  }
}

const port = Number(process.env.FAKE_PORT ?? 8787)
server.listen(port, () => console.log(`fake backend on http://127.0.0.1:${port}`))
