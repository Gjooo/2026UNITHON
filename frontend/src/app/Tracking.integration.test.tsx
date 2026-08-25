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
import terminatingFailed from '@/test/fixtures/jobs/terminating-failed.json'
import invalidJobState from '@/test/fixtures/errors/invalid-job-state.json'

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

  it('does_not_show_the_failure_message_before_the_final_status', async () => {
    const user = setup()
    await reachTracking(user)

    // 실패 callback이 오면 서버는 결과를 즉시 기록하지만 상태는 TERMINATING에 머문다.
    expect(terminatingFailed.status).toBe('TERMINATING')
    expect(terminatingFailed.failureMessage).toBe('CUDA out of memory at step 120')

    setServed(terminatingFailed)
    await tick(2500)
    await waitFor(() =>
      expect(screen.getByText('실행 환경 종료를 확인하고 있어요')).toBeInTheDocument(),
    )

    expect(screen.queryByText('학습이 완료되지 않았어요')).not.toBeInTheDocument()
    expect(screen.queryByText(terminatingFailed.failureMessage)).not.toBeInTheDocument()
  })

  it('tolerates_a_status_that_skips_running', async () => {
    const user = setup()
    await reachTracking(user)
    await waitFor(() =>
      expect(screen.getByText('실행 환경을 준비하고 있어요')).toBeInTheDocument(),
    )

    // 실제 GPU에서 RUNNING은 몇 초라 폴링이 통째로 건너뛸 수 있다.
    setServed(terminating)
    await tick(2500)
    await waitFor(() =>
      expect(screen.getByText('실행 환경 종료를 확인하고 있어요')).toBeInTheDocument(),
    )

    // 건너뛴 단계도 완료로 표시하고, 순서대로 지났다고 가정하지 않는다.
    const steps = screen.getAllByRole('listitem')
    expect(steps[0]).toHaveTextContent('완료')
    expect(steps[1]).toHaveTextContent('완료')
    expect(steps[2]).toHaveTextContent('진행 중')
  })

  it('tells_the_user_that_preparing_the_environment_takes_minutes', async () => {
    const user = setup()
    await reachTracking(user)

    // 실측 7분 30초. 안내가 없으면 멈춘 것으로 읽힌다.
    const tracker = await screen.findByRole('region', { name: '실행 상태' })
    expect(within(tracker).getByText(/몇 분/)).toBeInTheDocument()
  })

  it('explains_when_cancel_is_no_longer_possible', async () => {
    const user = setup()
    server.use(
      http.post('*/api/v1/jobs/:jobId/cancel', () =>
        HttpResponse.json(invalidJobState, { status: 409 }),
      ),
    )

    setServed(running)
    await reachTracking(user)
    await waitFor(() =>
      expect(screen.getByText('학습을 실행하고 있어요')).toBeInTheDocument(),
    )

    await user.click(screen.getByRole('button', { name: '실행 중단' }))
    const dialog = await screen.findByRole('dialog', { name: '실행을 중단할까요?' })
    await user.click(within(dialog).getByRole('button', { name: '중단하기' }))

    // 서버가 거절하면 상태를 추정하지 말고 그대로 알린다.
    expect(await screen.findByRole('alert')).toHaveTextContent(
      '이 작업은 현재 이 행동을 할 수 있는 상태가 아닙니다.',
    )
    expect(screen.getByText('학습을 실행하고 있어요')).toBeInTheDocument()
  })
})