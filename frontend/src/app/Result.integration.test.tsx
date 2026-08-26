import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import { act, screen, waitFor, within } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { http, HttpResponse } from 'msw'
import { server } from '@/test/msw/server'
import { renderApp } from '@/test/renderApp'
import completed from '@/test/fixtures/jobs/completed.json'
import failed from '@/test/fixtures/jobs/failed.json'
import teardownUnconfirmed from '@/test/fixtures/jobs/failed-teardown-unconfirmed.json'
import cancelled from '@/test/fixtures/jobs/cancelled.json'
import running from '@/test/fixtures/jobs/running.json'
import jobNotFound from '@/test/fixtures/errors/job-not-found.json'
import sessionExpired from '@/test/fixtures/errors/session-required.json'

const ACTIVE_JOB_KEY = 'unwork.activeJobId'

beforeEach(() => {
  window.localStorage.clear()
})

afterEach(() => {
  vi.useRealTimers()
  window.localStorage.clear()
})

function serveJob(job: object) {
  server.use(http.get('*/api/v1/jobs/:jobId', () => HttpResponse.json(job)))
}

describe('최종 결과', () => {
  it('shows_completion_log_exit_code_and_confirmed_termination', async () => {
    window.localStorage.setItem(ACTIVE_JOB_KEY, completed.id)
    serveJob(completed)
    renderApp()

    const result = await screen.findByRole('region', { name: '실행 결과' })
    expect(within(result).getByText('학습이 완료됐어요')).toBeInTheDocument()
    expect(within(result).getByText(completed.completionLog)).toBeInTheDocument()
    expect(within(result).getByText('0')).toBeInTheDocument()
    expect(
      within(result).getByText(completed.executionPlan.recommended.gpuType),
    ).toBeInTheDocument()
    expect(within(result).getByText('실행 환경 자동 종료 완료')).toBeInTheDocument()
  })

  it('shows_safe_failure_message_without_provider_secrets', async () => {
    window.localStorage.setItem(ACTIVE_JOB_KEY, failed.id)
    serveJob(failed)
    renderApp()

    const result = await screen.findByRole('region', { name: '실행 결과' })
    expect(within(result).getByText('학습이 완료되지 않았어요')).toBeInTheDocument()
    // 원인을 먼저 보여 준다. 재시도 가능성을 추정해 말하지 않는다.
    expect(within(result).getByText(failed.failureMessage)).toBeInTheDocument()
    expect(result.textContent).not.toMatch(/pod|Pod|api[_-]?key|Bearer|runpod/i)
    expect(result.textContent).not.toContain(
      failed.executionPlan.recommended.profileId,
    )

    // 종료 코드와 로그는 세부 정보 안에 둔다.
    expect(screen.queryByText('1')).not.toBeVisible()
    await userEvent.setup().click(screen.getByRole('button', { name: '세부 정보' }))
    await waitFor(() => expect(screen.getByText('1')).toBeVisible())
  })

  it('omits_teardown_confirmation_when_the_server_has_not_confirmed_it', async () => {
    window.localStorage.setItem(ACTIVE_JOB_KEY, teardownUnconfirmed.id)
    serveJob(teardownUnconfirmed)
    renderApp()

    const result = await screen.findByRole('region', { name: '실행 결과' })
    expect(within(result).queryByText('실행 환경 자동 종료 완료')).not.toBeInTheDocument()
    expect(within(result).getByText('실행 환경 종료를 아직 확인하지 못했습니다')).toBeInTheDocument()
  })

  it('shows_cancelled_result_with_confirmed_termination', async () => {
    window.localStorage.setItem(ACTIVE_JOB_KEY, cancelled.id)
    serveJob(cancelled)
    renderApp()

    const result = await screen.findByRole('region', { name: '실행 결과' })
    expect(within(result).getByText('실행이 중단됐어요')).toBeInTheDocument()
    expect(within(result).getByText('실행 환경 자동 종료 완료')).toBeInTheDocument()
  })
})

describe('새로고침 복구', () => {
  it('restores_active_job_after_reload_when_session_owns_it', async () => {
    window.localStorage.setItem(ACTIVE_JOB_KEY, running.id)
    serveJob(running)
    renderApp()

    expect(await screen.findByText('학습을 실행하고 있어요')).toBeInTheDocument()
    expect(window.localStorage.getItem(ACTIVE_JOB_KEY)).toBe(running.id)
  })

  it('clears_saved_job_after_session_expired_or_job_not_found', async () => {
    for (const [body, status] of [
      [jobNotFound, 404],
      [sessionExpired, 401],
    ] as const) {
      window.localStorage.setItem(ACTIVE_JOB_KEY, running.id)
      server.use(http.get('*/api/v1/jobs/:jobId', () => HttpResponse.json(body, { status })))

      const view = renderApp()
      expect(await screen.findByRole('alert')).toHaveTextContent(
        status === 404
          ? '이 작업을 찾을 수 없거나 현재 세션에서 볼 수 없습니다.'
          : '세션이 만료됐습니다. 새 세션을 시작해 주세요.',
      )
      expect(screen.getByLabelText('최대 예산')).toBeInTheDocument()
      await waitFor(() =>
        expect(window.localStorage.getItem(ACTIVE_JOB_KEY)).toBeNull(),
      )
      view.unmount()
    }
  })

  it('backs_off_after_transient_polling_failures', async () => {
    vi.useFakeTimers()
    let failing = false
    let gets = 0
    window.localStorage.setItem(ACTIVE_JOB_KEY, running.id)
    server.use(
      http.get('*/api/v1/jobs/:jobId', () => {
        gets += 1
        if (failing) return HttpResponse.error()
        return HttpResponse.json(running)
      }),
    )

    renderApp()
    await screen.findByText('학습을 실행하고 있어요')

    const tick = async (ms: number) => {
      await act(async () => {
        await vi.advanceTimersByTimeAsync(ms)
      })
    }

    failing = true
    await tick(2500)
    const afterFirstFailure = gets

    // 1회 실패 후 간격은 5초다. 2.5초에는 다시 요청하지 않는다.
    await tick(2500)
    expect(gets).toBe(afterFirstFailure)
    await tick(2500)
    expect(gets).toBe(afterFirstFailure + 1)

    // 2회 실패 후 간격은 10초다.
    await tick(5000)
    expect(gets).toBe(afterFirstFailure + 1)
    await tick(5000)
    expect(gets).toBe(afterFirstFailure + 2)

    // 실패 중에도 마지막 정상 상태를 유지하고 최종 상태를 추정하지 않는다.
    expect(screen.getByText('학습을 실행하고 있어요')).toBeInTheDocument()
    expect(screen.getByText('연결을 다시 확인하는 중')).toBeInTheDocument()
  })

})