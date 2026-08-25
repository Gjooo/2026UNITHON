import { describe, expect, it } from 'vitest'
import { screen, waitFor, within } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { http, HttpResponse } from 'msw'
import { server } from '@/test/msw/server'
import { renderApp } from '@/test/renderApp'
import balanced from '@/test/fixtures/jobs/draft-balanced.json'
import startAccepted from '@/test/fixtures/jobs/start-accepted.json'
import demoBusy from '@/test/fixtures/errors/demo-busy.json'
import executionAlreadyUsed from '@/test/fixtures/errors/execution-already-used.json'
import runpodUnavailable from '@/test/fixtures/errors/runpod-unavailable.json'

type User = ReturnType<typeof userEvent.setup>

async function reachPlanReview(user: User) {
  server.use(http.post('*/api/v1/jobs', () => HttpResponse.json(balanced, { status: 201 })))
  renderApp()
  await screen.findByText('익명 세션')
  await user.type(screen.getByLabelText('최대 예산'), '10000')
  await user.click(screen.getByRole('radio', { name: /균형/ }))
  await user.click(screen.getByRole('button', { name: 'Agent에게 실행안 요청' }))
  await screen.findByRole('region', { name: 'Agent 추천 실행안' })
}

describe('실행 승인', () => {
  it('does_not_start_before_approval_confirmation', async () => {
    const user = userEvent.setup()
    const starts: string[] = []
    server.use(
      http.post('*/api/v1/jobs/:jobId/start', ({ params }) => {
        starts.push(String(params.jobId))
        return HttpResponse.json(startAccepted, { status: 202 })
      }),
    )

    await reachPlanReview(user)
    await user.click(screen.getByRole('button', { name: '실행 승인' }))

    // dialog가 열렸을 뿐 비용이 발생하는 요청은 아직 나가지 않는다.
    const dialog = await screen.findByRole('dialog', { name: '실행 승인' })
    expect(starts).toEqual([])

    const plan = balanced.executionPlan.recommended
    expect(within(dialog).getByText(plan.gpuType)).toBeInTheDocument()
    expect(within(dialog).getByText('₩650')).toBeInTheDocument()
    expect(within(dialog).getByText('약 7분')).toBeInTheDocument()
    expect(dialog).toHaveTextContent('예산은 실제 청구액을 제한하지 않습니다')
    expect(dialog).toHaveTextContent('이 브라우저에서는 실제 실행을 한 번만 할 수 있습니다')
  })

  it('cancels_the_dialog_without_starting_and_returns_focus', async () => {
    const user = userEvent.setup()
    const starts: string[] = []
    server.use(
      http.post('*/api/v1/jobs/:jobId/start', ({ params }) => {
        starts.push(String(params.jobId))
        return HttpResponse.json(startAccepted, { status: 202 })
      }),
    )

    await reachPlanReview(user)
    const trigger = screen.getByRole('button', { name: '실행 승인' })
    await user.click(trigger)
    await screen.findByRole('dialog', { name: '실행 승인' })

    await user.keyboard('{Escape}')

    await waitFor(() => expect(screen.queryByRole('dialog')).not.toBeInTheDocument())
    expect(starts).toEqual([])
    expect(trigger).toHaveFocus()
  })

  it('starts_once_after_confirming_execution_contract', async () => {
    const user = userEvent.setup()
    const starts: string[] = []
    let releaseStart!: () => void
    const startGate = new Promise<void>((resolve) => {
      releaseStart = resolve
    })
    server.use(
      http.post('*/api/v1/jobs/:jobId/start', async ({ params }) => {
        starts.push(String(params.jobId))
        await startGate
        return HttpResponse.json(startAccepted, { status: 202 })
      }),
    )

    await reachPlanReview(user)
    await user.click(screen.getByRole('button', { name: '실행 승인' }))
    const dialog = await screen.findByRole('dialog', { name: '실행 승인' })
    const confirm = within(dialog).getByRole('button', { name: '승인하고 실행 시작' })

    // 요청이 진행 중인 동안 다시 눌러도 비용이 두 번 발생해서는 안 된다.
    await user.click(confirm)
    await waitFor(() => expect(starts).toHaveLength(1))
    expect(confirm).toBeDisabled()
    await user.click(confirm)
    await user.click(confirm)
    expect(starts).toEqual([balanced.id])

    releaseStart()

    await screen.findByText('실행 환경을 준비하고 있어요')
    expect(starts).toEqual([balanced.id])
    expect(screen.queryByRole('region', { name: 'Agent 추천 실행안' })).not.toBeInTheDocument()
  })

  it('shows_demo_busy_without_changing_the_contract', async () => {
    const user = userEvent.setup()
    server.use(
      http.post('*/api/v1/jobs/:jobId/start', () =>
        HttpResponse.json(demoBusy, { status: 409 }),
      ),
    )

    await reachPlanReview(user)
    await user.click(screen.getByRole('button', { name: '실행 승인' }))
    const dialog = await screen.findByRole('dialog', { name: '실행 승인' })
    await user.click(within(dialog).getByRole('button', { name: '승인하고 실행 시작' }))

    const alert = await screen.findByRole('alert')
    expect(alert).toHaveTextContent(
      '지금은 다른 실행이 진행 중입니다. 대기열이 없으니 잠시 후 다시 시도해 주세요.',
    )
    // 계약은 그대로 남아 나중에 다시 승인할 수 있다.
    const recommended = screen.getByRole('region', { name: 'Agent 추천 실행안' })
    expect(within(recommended).getByText(balanced.executionPlan.recommended.gpuType)).toBeInTheDocument()
    expect(within(recommended).getByText('₩650')).toBeInTheDocument()
    expect(screen.getByRole('button', { name: '실행 승인' })).toBeEnabled()
  })

  it('shows_execution_limit_message', async () => {
    const user = userEvent.setup()
    server.use(
      http.post('*/api/v1/jobs/:jobId/start', () =>
        HttpResponse.json(executionAlreadyUsed, { status: 409 }),
      ),
    )

    await reachPlanReview(user)
    await user.click(screen.getByRole('button', { name: '실행 승인' }))
    const dialog = await screen.findByRole('dialog', { name: '실행 승인' })
    await user.click(within(dialog).getByRole('button', { name: '승인하고 실행 시작' }))

    expect(await screen.findByRole('alert')).toHaveTextContent(
      '이 브라우저에서는 실제 실행을 한 번만 할 수 있습니다.',
    )
  })

  it('warns_before_approval_when_the_execution_allowance_is_used_up', async () => {
    const user = userEvent.setup()
    server.use(
      http.post('*/api/v1/session', () =>
        HttpResponse.json(
          { expiresAt: '2026-09-01T19:47:38Z', executionAllowance: { used: 1, limit: 1 } },
          { status: 201 },
        ),
      ),
    )

    await reachPlanReview(user)

    // 409를 모르고 맞기 전에 알린다. 비용 없는 비교는 계속 허용한다.
    expect(
      screen.getByText('이 브라우저에서는 실제 실행을 한 번만 할 수 있습니다.'),
    ).toBeInTheDocument()
    expect(screen.getByRole('button', { name: '실행 승인' })).toBeDisabled()
  })

  it('shows_provider_unavailable_with_a_next_action', async () => {
    const user = userEvent.setup()
    server.use(
      http.post('*/api/v1/jobs/:jobId/start', () =>
        HttpResponse.json(runpodUnavailable, { status: 503 }),
      ),
    )

    await reachPlanReview(user)
    await user.click(screen.getByRole('button', { name: '실행 승인' }))
    const dialog = await screen.findByRole('dialog', { name: '실행 승인' })
    await user.click(within(dialog).getByRole('button', { name: '승인하고 실행 시작' }))

    // 자동 재시도하지 않고, 계약을 유지한 채 다음 행동을 알린다.
    expect(await screen.findByRole('alert')).toHaveTextContent(
      '실행 환경을 시작하거나 확인하지 못했습니다. 잠시 후 다시 확인해 주세요.',
    )
    expect(screen.getByRole('region', { name: 'Agent 추천 실행안' })).toBeInTheDocument()
    expect(screen.getByRole('button', { name: '실행 승인' })).toBeEnabled()
  })

  it('closes_the_dialog_when_start_fails_so_the_error_is_readable', async () => {
    const user = userEvent.setup()
    server.use(
      http.post('*/api/v1/jobs/:jobId/start', () =>
        HttpResponse.json(demoBusy, { status: 409 }),
      ),
    )

    await reachPlanReview(user)
    await user.click(screen.getByRole('button', { name: '실행 승인' }))
    const dialog = await screen.findByRole('dialog', { name: '실행 승인' })
    await user.click(within(dialog).getByRole('button', { name: '승인하고 실행 시작' }))

    // dialog는 fixed overlay라 열린 채로 두면 페이지의 오류 alert를 덮는다.
    // 사용자 눈에는 버튼을 눌러도 아무 일도 일어나지 않은 것처럼 보인다.
    await waitFor(() => expect(screen.queryByRole('dialog')).not.toBeInTheDocument())
    expect(await screen.findByRole('alert')).toHaveTextContent(
      '지금은 다른 실행이 진행 중입니다',
    )
    // 계약은 남고 다시 승인할 수 있다.
    expect(screen.getByRole('button', { name: '실행 승인' })).toBeEnabled()
  })
})