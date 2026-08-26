import { afterEach, beforeEach, describe, expect, it } from 'vitest'
import { screen, waitFor, within } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { http, HttpResponse } from 'msw'
import { server } from '@/test/msw/server'
import { renderApp } from '@/test/renderApp'
import running from '@/test/fixtures/jobs/running.json'
import balanced from '@/test/fixtures/jobs/draft-balanced.json'
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

  it('explains_the_fee_model_and_that_it_is_not_charged_yet', async () => {
    renderApp()

    const pricing = await screen.findByRole('region', { name: '요금' })

    // 수수료 모델은 밝히되, 지금 청구하지 않는다는 것도 같이 말한다.
    expect(within(pricing).getByText('GPU 사용료의 15%')).toBeInTheDocument()
    expect(pricing.textContent).toMatch(/현재는 청구하지\s*않습니다/)

    // 앱에 나오는 숫자에 수수료가 없다는 점을 명시한다.
    expect(pricing.textContent).toMatch(/수수료가 포함돼 있지\s*않습니다/)

    // 지어낸 구독 등급은 만들지 않는다.
    expect(pricing.textContent).not.toMatch(/Free|Pro|Team|무료 체험/)
  })

  it('states_who_decides_what', async () => {
    renderApp()

    // PRD의 핵심 서사다. 사람이 판단을 쥐고 Agent가 운영을 가져간다.
    const roles = await screen.findByRole('region', { name: '역할' })
    expect(within(roles).getByText(/예산/)).toBeInTheDocument()
    expect(within(roles).getByText(/자원 종료/)).toBeInTheDocument()
  })

  it('shows_the_landing_again_after_only_comparing_plans', async () => {
    const user = userEvent.setup()
    server.use(
      http.post('*/api/v1/jobs', () => HttpResponse.json(balanced, { status: 201 })),
    )

    renderApp()
    const [start] = await screen.findAllByRole('button', { name: '시작하기' })
    await user.click(start)
    await user.type(await screen.findByLabelText('최대 예산'), '10000')
    await user.click(screen.getByRole('radio', { name: /균형/ }))
    await user.click(screen.getByRole('button', { name: 'Agent에게 실행안 요청' }))
    await screen.findByRole('region', { name: 'Agent 추천 실행안' })

    // 비교만 한 작업은 복구 대상이 아니다. 비용도 없고 다시 만들면 된다.
    expect(window.localStorage.getItem(ACTIVE_JOB_KEY)).toBeNull()
  })

  it('returns_to_the_landing_from_the_wordmark', async () => {
    const user = userEvent.setup()
    renderApp()
    const [start] = await screen.findAllByRole('button', { name: '시작하기' })
    await user.click(start)
    await screen.findByLabelText('최대 예산')

    await user.click(screen.getByRole('button', { name: 'UNWORK 홈으로' }))

    expect(await screen.findByRole('heading', { level: 1 })).toHaveTextContent(
      'GPU를 다루지 않고 학습을 끝냅니다',
    )
  })
})