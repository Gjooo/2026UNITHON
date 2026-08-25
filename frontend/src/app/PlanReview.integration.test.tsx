import { describe, expect, it } from 'vitest'
import { screen, waitFor, within } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { http, HttpResponse } from 'msw'
import { server } from '@/test/msw/server'
import { renderApp } from '@/test/renderApp'
import balanced from '@/test/fixtures/jobs/draft-balanced.json'
import overBudget from '@/test/fixtures/jobs/draft-over-budget.json'
import noEligiblePlan from '@/test/fixtures/errors/no-eligible-plan.json'

async function submitConstraints(
  user: ReturnType<typeof userEvent.setup>,
  budget: string,
  priority: RegExp,
) {
  await screen.findByText('익명 세션')
  await user.type(screen.getByLabelText('최대 예산'), budget)
  await user.click(screen.getByRole('radio', { name: priority }))
  await user.click(screen.getByRole('button', { name: 'Agent에게 실행안 요청' }))
}

describe('실행 계약 검토', () => {
  it('submits_only_budget_and_priority_and_renders_server_recommended_plan', async () => {
    const user = userEvent.setup()
    const bodies: unknown[] = []
    server.use(
      http.post('*/api/v1/jobs', async ({ request }) => {
        bodies.push(await request.json())
        return HttpResponse.json(balanced, { status: 201 })
      }),
    )

    renderApp()
    await submitConstraints(user, '10000', /균형/)

    const recommended = await screen.findByRole('region', { name: 'Agent 추천 실행안' })
    const plan = balanced.executionPlan.recommended

    // 서버가 준 값을 그대로 표시한다. 클라이언트가 추천을 다시 계산하지 않는다.
    expect(within(recommended).getByText(plan.gpuType)).toBeInTheDocument()
    expect(within(recommended).getByText(plan.provider)).toBeInTheDocument()
    expect(within(recommended).getByText('₩650')).toBeInTheDocument()
    expect(within(recommended).getByText('약 7분')).toBeInTheDocument()
    expect(within(recommended).getByText(plan.reason)).toBeInTheDocument()

    // 사용자가 정하는 값은 두 개뿐이다.
    expect(bodies).toEqual([{ maxBudgetKrw: 10000, priority: 'BALANCED' }])

    // 내부 식별자는 화면에 노출하지 않는다.
    expect(document.body.textContent).not.toContain(plan.profileId)
    expect(document.body.textContent).not.toContain(
      balanced.executionPlan.selectionPolicyVersion,
    )
    expect(document.body.textContent).not.toContain('DEMO_SNAPSHOT')
  })

  it('keeps_over_budget_candidates_visible_but_unselectable', async () => {
    const user = userEvent.setup()
    server.use(
      http.post('*/api/v1/jobs', () => HttpResponse.json(overBudget, { status: 201 })),
    )

    renderApp()
    await submitConstraints(user, '500', /빠른 완료/)

    const comparison = await screen.findByRole('region', { name: 'GPU 후보 비교' })
    for (const candidate of overBudget.executionPlan.candidates) {
      expect(within(comparison).getByText(candidate.gpuType)).toBeInTheDocument()
    }

    // 예산을 넘는 후보도 비교 근거로 보이되 고를 수 없다.
    expect(within(comparison).getAllByText('예산 초과')).toHaveLength(2)
    expect(within(comparison).getAllByText('예산 내')).toHaveLength(1)
    expect(within(comparison).queryAllByRole('button')).toHaveLength(0)
    expect(within(comparison).queryAllByRole('radio')).toHaveLength(0)
  })

  it('keeps_constraints_after_no_eligible_plan', async () => {
    const user = userEvent.setup()
    server.use(
      http.post('*/api/v1/jobs', () =>
        HttpResponse.json(noEligiblePlan, { status: 422 }),
      ),
    )

    renderApp()
    await submitConstraints(user, '100', /저비용/)

    const alert = await screen.findByRole('alert')
    expect(alert).toHaveTextContent('이 예산 안에서 실행할 수 있는 GPU 후보가 없습니다.')

    // 입력을 잃지 않아야 예산을 조정해 다시 비교할 수 있다.
    expect(screen.getByLabelText('최대 예산')).toHaveValue(100)
    expect(screen.getByRole('radio', { name: /저비용/ })).toBeChecked()
    expect(screen.queryByRole('region', { name: 'Agent 추천 실행안' })).not.toBeInTheDocument()
  })

  it('shows_fixed_workload_facts_from_the_server_response', async () => {
    const user = userEvent.setup()
    // 시나리오 값은 서버 설정으로 바뀐다. 부스 시연에서 상한을 1분으로 낮추면
    // 화면도 1분이어야 한다. 클라이언트 상수로 굳히면 여기서 깨진다.
    const retimed = {
      ...balanced,
      scenario: { ...balanced.scenario, requiredVramGb: 48, maxRuntimeMinutes: 1 },
    }
    server.use(
      http.post('*/api/v1/jobs', () => HttpResponse.json(retimed, { status: 201 })),
    )

    renderApp()
    await submitConstraints(user, '10000', /균형/)

    const contract = await screen.findByRole('region', { name: '실행 계약 정보' })
    expect(within(contract).getByText(balanced.scenario.name)).toBeInTheDocument()
    expect(within(contract).getByText('48GB')).toBeInTheDocument()
    expect(within(contract).getByText('1분')).toBeInTheDocument()
    expect(within(contract).getByText('₩10,000')).toBeInTheDocument()
    expect(within(contract).getByText('균형')).toBeInTheDocument()
    expect(
      within(contract).getByText(balanced.executionPlan.estimateDisclaimer),
    ).toBeInTheDocument()
  })

  it('hides_repository_and_command_behind_a_disclosure', async () => {
    const user = userEvent.setup()
    server.use(
      http.post('*/api/v1/jobs', () => HttpResponse.json(balanced, { status: 201 })),
    )

    renderApp()
    await submitConstraints(user, '10000', /균형/)

    await screen.findByRole('region', { name: '실행 계약 정보' })
    expect(screen.queryByText(balanced.scenario.executionCommand)).not.toBeVisible()

    await user.click(screen.getByRole('button', { name: '고정 워크로드 정보' }))
    await waitFor(() =>
      expect(screen.getByText(balanced.scenario.executionCommand)).toBeVisible(),
    )
    expect(screen.getByText(balanced.scenario.repositoryUrl)).toBeVisible()
  })
})
