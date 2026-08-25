import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import { act, screen, waitFor, within } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { http, HttpResponse } from 'msw'
import { server } from '@/test/msw/server'
import { renderApp } from '@/test/renderApp'
import type { TrainingJob } from '@/api/jobs'
import balanced from '@/test/fixtures/jobs/draft-balanced.json'
import startAccepted from '@/test/fixtures/jobs/start-accepted.json'
import provisioning from '@/test/fixtures/jobs/provisioning.json'
import running from '@/test/fixtures/jobs/running.json'
import terminating from '@/test/fixtures/jobs/terminating.json'
import completed from '@/test/fixtures/jobs/completed.json'
import cancelled from '@/test/fixtures/jobs/cancelled.json'

type User = ReturnType<typeof userEvent.setup>

let served: TrainingJob
let getCount = 0
let holdGet: Promise<void> | null = null

function setServed(job: unknown) {
  served = job as TrainingJob
}

beforeEach(() => {
  vi.useFakeTimers()
  getCount = 0
  holdGet = null
  setServed(provisioning)
  server.use(
    http.post('*/api/v1/jobs', () => HttpResponse.json(balanced, { status: 201 })),
    http.post('*/api/v1/jobs/:jobId/start', () =>
      HttpResponse.json(startAccepted, { status: 202 }),
    ),
    http.get('*/api/v1/jobs/:jobId', async () => {
      if (holdGet) await holdGet
      getCount += 1
      return HttpResponse.json(served)
    }),
  )
})

afterEach(() => {
  vi.useRealTimers()
})

function setup(): User {
  return userEvent.setup({ advanceTimers: vi.advanceTimersByTime })
}

async function tick(ms: number) {
  await act(async () => {
    await vi.advanceTimersByTimeAsync(ms)
  })
}

async function reachTracking(user: User) {
  renderApp()
  await screen.findByText('익명 세션')
  await user.type(screen.getByLabelText('최대 예산'), '10000')
  await user.click(screen.getByRole('radio', { name: /균형/ }))
  await user.click(screen.getByRole('button', { name: 'Agent에게 실행안 요청' }))
  await screen.findByRole('region', { name: 'Agent 추천 실행안' })
  await user.click(screen.getByRole('button', { name: '실행 승인' }))
  const dialog = await screen.findByRole('dialog', { name: '실행 승인' })
  await user.click(within(dialog).getByRole('button', { name: '승인하고 실행 시작' }))
  await screen.findByRole('region', { name: '실행 상태' })
}

describe('실행 추적', () => {
  it('polls_only_while_job_is_non_terminal', async () => {
    const user = setup()
    await reachTracking(user)

    const afterEntry = getCount
    await tick(2500)
    expect(getCount).toBe(afterEntry + 1)
    await tick(2500)
    expect(getCount).toBe(afterEntry + 2)

    setServed(completed)
    await tick(2500)
    const afterTerminal = getCount

    // 최종 상태에서는 폴링을 멈춘다.
    await tick(2500 * 4)
    expect(getCount).toBe(afterTerminal)
  })

  it('renders_provisioning_running_and_terminating_in_order', async () => {
    const user = setup()
    await reachTracking(user)

    expect(await screen.findByText('실행 환경을 준비하고 있어요')).toBeInTheDocument()

    setServed(running)
    await tick(2500)
    await waitFor(() =>
      expect(screen.getByText('학습을 실행하고 있어요')).toBeInTheDocument(),
    )

    setServed(terminating)
    await tick(2500)
    await waitFor(() =>
      expect(screen.getByText('실행 환경 종료를 확인하고 있어요')).toBeInTheDocument(),
    )
  })

  it('does_not_show_final_result_while_terminating', async () => {
    const user = setup()
    await reachTracking(user)

    // TERMINATING 응답은 이미 exitCode 0과 완료 로그를 갖고 있다.
    expect(terminating.exitCode).toBe(0)
    expect(terminating.completionLog).toBe('Training completed')

    setServed(terminating)
    await tick(2500)
    await waitFor(() =>
      expect(screen.getByText('실행 환경 종료를 확인하고 있어요')).toBeInTheDocument(),
    )

    // 자원 종료 확인 전에는 성공이라고 말하지 않는다.
    expect(screen.queryByText('학습이 완료됐어요')).not.toBeInTheDocument()
    expect(screen.queryByText(terminating.completionLog)).not.toBeInTheDocument()
    expect(document.body.textContent).not.toContain('종료 코드')
  })

  it('shows_elapsed_time_and_the_server_runtime_cap', async () => {
    const user = setup()
    vi.setSystemTime(Date.parse(provisioning.startedAt) + 72_000)
    await reachTracking(user)

    const tracker = await screen.findByRole('region', { name: '실행 상태' })
    expect(within(tracker).getByText('1분 12초')).toBeInTheDocument()
    expect(within(tracker).getByText(`최대 ${provisioning.scenario.maxRuntimeMinutes}분`)).toBeInTheDocument()

    await tick(10_000)
    await waitFor(() => expect(within(tracker).getByText('1분 22초')).toBeInTheDocument())
  })

  it('cancel_waits_for_server_confirmed_cancelled_status', async () => {
    const user = setup()
    const cancels: string[] = []
    server.use(
      http.post('*/api/v1/jobs/:jobId/cancel', ({ params }) => {
        cancels.push(String(params.jobId))
        return HttpResponse.json({ id: params.jobId, status: 'TERMINATING' }, { status: 202 })
      }),
    )

    setServed(running)
    await reachTracking(user)
    await waitFor(() =>
      expect(screen.getByText('학습을 실행하고 있어요')).toBeInTheDocument(),
    )

    await user.click(screen.getByRole('button', { name: '실행 중단' }))
    const dialog = await screen.findByRole('dialog', { name: '실행을 중단할까요?' })
    expect(cancels).toEqual([])

    setServed(terminating)
    // 202 직후의 재확인 응답을 붙들어, 서버 확인 전 화면을 실제로 관찰한다.
    let releaseGet!: () => void
    holdGet = new Promise<void>((resolve) => {
      releaseGet = resolve
    })

    await user.click(within(dialog).getByRole('button', { name: '중단하기' }))
    await waitFor(() => expect(cancels).toHaveLength(1))

    await waitFor(() =>
      expect(screen.getByText('실행 환경 종료를 확인하고 있어요')).toBeInTheDocument(),
    )
    // 서버가 CANCELLED를 주기 전에는 중단 완료라고 하지 않는다.
    expect(screen.queryByText('실행이 중단됐어요')).not.toBeInTheDocument()
    expect(screen.queryByRole('button', { name: '실행 중단' })).not.toBeInTheDocument()

    releaseGet()
    holdGet = null
    await tick(0)
    expect(screen.queryByText('실행이 중단됐어요')).not.toBeInTheDocument()

    setServed(cancelled)
    await tick(2500)
    await waitFor(() =>
      expect(screen.getByText('실행이 중단됐어요')).toBeInTheDocument(),
    )
  })
})
