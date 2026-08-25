import { expect, test, type Page } from '@playwright/test'

async function requestPlan(page: Page, budget: string, priority: RegExp) {
  await page.goto('/')
  await expect(page.getByText('익명 세션')).toBeVisible()
  await page.getByLabel('최대 예산').fill(budget)
  await page.getByRole('radio', { name: priority }).check()
  await page.getByRole('button', { name: 'Agent에게 실행안 요청' }).click()
}

test('e2e_successful_execution_flow', async ({ page }) => {
  await requestPlan(page, '10000', /균형/)

  const recommended = page.getByRole('region', { name: 'Agent 추천 실행안' })
  await expect(recommended).toBeVisible()
  await expect(recommended.getByText('NVIDIA L40S')).toBeVisible()

  await page.getByRole('button', { name: '실행 승인' }).click()
  const dialog = page.getByRole('dialog', { name: '실행 승인' })
  await expect(dialog).toContainText('예산은 실제 청구액을 제한하지 않습니다')
  await dialog.getByRole('button', { name: '승인하고 실행 시작' }).click()

  await expect(page.getByText('실행 환경을 준비하고 있어요')).toBeVisible()
  await expect(page.getByText('학습을 실행하고 있어요')).toBeVisible({ timeout: 15_000 })
  await expect(page.getByText('실행 환경 종료를 확인하고 있어요')).toBeVisible({ timeout: 15_000 })

  const result = page.getByRole('region', { name: '실행 결과' })
  await expect(result).toBeVisible({ timeout: 15_000 })
  await expect(result.getByText('학습이 완료됐어요')).toBeVisible()
  await expect(result.getByText('Training completed')).toBeVisible()
  await expect(result.getByText('실행 환경 자동 종료 완료')).toBeVisible()
})

test('e2e_no_eligible_plan', async ({ page }) => {
  await requestPlan(page, '100', /저비용/)

  await expect(page.getByRole('alert')).toContainText(
    '이 예산 안에서 실행할 수 있는 GPU 후보가 없습니다.',
  )
  // 입력을 유지해 예산만 고쳐 다시 비교할 수 있다.
  await expect(page.getByLabel('최대 예산')).toHaveValue('100')
  await expect(page.getByRole('radio', { name: /저비용/ })).toBeChecked()
})

test('e2e_cancelled_execution_flow', async ({ page }) => {
  await requestPlan(page, '10000', /빠른 완료/)

  await page.getByRole('button', { name: '실행 승인' }).click()
  await page
    .getByRole('dialog', { name: '실행 승인' })
    .getByRole('button', { name: '승인하고 실행 시작' })
    .click()

  await page.getByRole('button', { name: '실행 중단' }).click()
  const dialog = page.getByRole('dialog', { name: '실행을 중단할까요?' })
  await expect(dialog).toBeVisible()
  await dialog.getByRole('button', { name: '중단하기' }).click()

  await expect(page.getByText('실행 환경 종료를 확인하고 있어요')).toBeVisible()
  const result = page.getByRole('region', { name: '실행 결과' })
  await expect(result).toBeVisible({ timeout: 15_000 })
  await expect(result.getByText('실행이 중단됐어요')).toBeVisible()
  await expect(result.getByText('실행 환경 자동 종료 완료')).toBeVisible()
})

test('e2e_over_budget_candidates_stay_visible', async ({ page }) => {
  await requestPlan(page, '500', /빠른 완료/)

  const comparison = page.getByRole('region', { name: 'GPU 후보 비교' })
  await expect(comparison).toBeVisible()
  await expect(comparison.getByText('예산 초과')).toHaveCount(2)
  await expect(comparison.getByText('예산 내')).toHaveCount(1)
  await expect(comparison.getByRole('button')).toHaveCount(0)
})

test('e2e_recovers_the_active_job_after_reload', async ({ page }) => {
  await requestPlan(page, '10000', /균형/)
  await page.getByRole('button', { name: '실행 승인' }).click()
  await page
    .getByRole('dialog', { name: '실행 승인' })
    .getByRole('button', { name: '승인하고 실행 시작' })
    .click()
  await expect(page.getByText('실행 환경을 준비하고 있어요')).toBeVisible()

  await page.reload()

  // 새로고침해도 서버가 소유를 인정한 Job으로 돌아온다.
  await expect(page.getByRole('region', { name: '실행 상태' })).toBeVisible()
  await expect(page.getByLabel('최대 예산')).toHaveCount(0)
})

test('e2e_keeps_workload_details_behind_a_disclosure', async ({ page }) => {
  await requestPlan(page, '10000', /균형/)
  await expect(page.getByRole('region', { name: '실행 계약 정보' })).toBeVisible()

  // jsdom은 hidden 속성만 보지만 브라우저에서는 author CSS가 [hidden]을 이길 수 있다.
  // toBeHidden()은 "DOM에 없음"도 통과시키므로, 붙어 있는데 보이지 않는지를 나눠 본다.
  const command = page.getByText('./run-demo-training.sh')
  await expect(command).toBeAttached()
  await expect(command).not.toBeVisible()

  await page.getByRole('button', { name: '고정 워크로드 정보' }).click()
  await expect(command).toBeVisible()
  await expect(page.getByText('https://github.com/example/golden-path')).toBeVisible()
})

test('e2e_failed_execution_shows_safe_cause_behind_a_disclosure', async ({ page, request }) => {
  await request.post('http://127.0.0.1:8787/__fake/outcome', { data: { outcome: 'FAILED' } })

  await requestPlan(page, '10000', /균형/)
  await page.getByRole('button', { name: '실행 승인' }).click()
  await page
    .getByRole('dialog', { name: '실행 승인' })
    .getByRole('button', { name: '승인하고 실행 시작' })
    .click()

  const result = page.getByRole('region', { name: '실행 결과' })
  await expect(result).toBeVisible({ timeout: 15_000 })
  await expect(result.getByText('학습이 완료되지 않았어요')).toBeVisible()
  await expect(result.getByText('CUDA out of memory at step 120')).toBeVisible()

  // 종료 코드는 세부 정보 안에 접혀 있어야 한다.
  const exitCode = result.getByText('종료 코드')
  await expect(exitCode).toBeAttached()
  await expect(exitCode).not.toBeVisible()

  await result.getByRole('button', { name: '세부 정보' }).click()
  await expect(exitCode).toBeVisible()

  await request.post('http://127.0.0.1:8787/__fake/outcome', { data: { outcome: 'COMPLETED' } })
})
