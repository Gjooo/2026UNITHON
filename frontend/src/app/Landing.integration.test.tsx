import { afterEach, beforeEach, describe, expect, it } from 'vitest'
import { screen, waitFor, within } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { http, HttpResponse } from 'msw'
import { server } from '@/test/msw/server'
import { renderApp } from '@/test/renderApp'
import running from '@/test/fixtures/jobs/running.json'
import sessionFixture from '@/test/fixtures/session.json'

const ACTIVE_JOB_KEY = 'unwork.activeJobId'

beforeEach(() => window.localStorage.clear())
afterEach(() => window.localStorage.clear())

describe('랜딩', () => {
  it('opens_on_the_landing_page_not_the_form', async () => {
    renderApp()

    expect(await screen.findByRole('heading', { level: 1 })).toBeInTheDocument()
    // 랜딩은 상단바·히어로·하단에서 각각 들어올 수 있어야 한다.
    expect(screen.getAllByRole('button', { name: '시작하기' }).length).toBeGreaterThan(1)
    // 제품을 설명하기 전에 입력부터 요구하지 않는다.
    expect(screen.queryByLabelText('최대 예산')).not.toBeInTheDocument()
  })

  it('does_not_create_a_session_until_the_user_enters', async () => {
    const user = userEvent.setup()
    const sessions: string[] = []
    server.use(
      http.post('*/api/v1/session', ({ request }) => {
        sessions.push(request.url)
        return HttpResponse.json(sessionFixture, { status: 201 })
      }),
    )

    renderApp()
    const [start] = await screen.findAllByRole('button', { name: '시작하기' })
    // 제품 설명만 보고 가는 사람에게 쿠키를 심지 않는다.
    expect(sessions).toEqual([])

    await user.click(start)
    await waitFor(() => expect(sessions).toHaveLength(1))
  })

  it('enters_the_app_from_the_landing_cta', async () => {
    const user = userEvent.setup()
    renderApp()

    const [start] = await screen.findAllByRole('button', { name: '시작하기' })
    await user.click(start)

    expect(await screen.findByLabelText('최대 예산')).toBeInTheDocument()
    expect(screen.queryAllByRole('button', { name: '시작하기' })).toHaveLength(0)
  })

  it('skips_the_landing_when_a_job_is_already_active', async () => {
    window.localStorage.setItem(ACTIVE_JOB_KEY, running.id)
    server.use(http.get('*/api/v1/jobs/:jobId', () => HttpResponse.json(running)))

    renderApp()

    // 새로고침한 사용자를 소개 화면으로 되돌리지 않는다.
    expect(await screen.findByText('학습을 실행하고 있어요')).toBeInTheDocument()
    expect(screen.queryAllByRole('button', { name: '시작하기' })).toHaveLength(0)
  })

  it('states_only_charges_the_product_actually_makes', async () => {
    renderApp()

    const pricing = await screen.findByRole('region', { name: '요금' })

    // 실행 경로에는 수수료가 붙지 않는다. 붙는다고 적으면 앱 안의 숫자와 어긋난다.
    expect(pricing.textContent).not.toMatch(/수수료|15%/)
    expect(pricing.textContent).not.toMatch(/Free|Pro|Team|무료 체험/)

    // 비용은 사용자가 연결한 계정에서 직접 나간다.
    expect(within(pricing).getByText(/본인의 Runpod 계정/)).toBeInTheDocument()
    expect(within(pricing).getByText('₩0')).toBeInTheDocument()

    // 화면에 나오는 숫자는 앱의 실행안 비교와 같은 값이어야 한다.
    expect(within(pricing).getByText('₩450')).toBeInTheDocument()
    expect(within(pricing).getByText('₩650')).toBeInTheDocument()
    expect(within(pricing).getByText('₩900')).toBeInTheDocument()
  })

  it('states_who_decides_what', async () => {
    renderApp()

    // PRD의 핵심 서사다. 사람이 판단을 쥐고 Agent가 운영을 가져간다.
    const roles = await screen.findByRole('region', { name: '역할' })
    expect(within(roles).getByText(/예산/)).toBeInTheDocument()
    expect(within(roles).getByText(/자원 종료/)).toBeInTheDocument()
  })
})
