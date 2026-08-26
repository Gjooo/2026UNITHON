import { expect, test, type Page, type APIRequestContext } from '@playwright/test'

/**
 * 실제 backend(fake provider 모드)에 붙여 리허설한다.
 *
 * fake 모드에는 학습 컨테이너가 없으므로 완료 callback을 테스트가 직접 친다.
 * 서비스 전체 동시 실행이 1개라 비용 없는 시나리오를 먼저 돌리고,
 * 실행하는 시나리오는 반드시 최종 상태까지 끌고 간 뒤 끝낸다.
 */
const ACTIVE_JOB_KEY = 'unwork.activeJobId'

async function requestPlan(page: Page, budget: string, priority: RegExp) {
  await page.goto('/')
  await page.getByRole('button', { name: '시작하기' }).first().click()
  await page.getByLabel('Runpod API 키').fill('rpa_e2e_fake_key')
  await page.getByRole('button', { name: '연결하기' }).click()
  await expect(page.getByText(/Runpod 연결됨/)).toBeVisible()
  await page.getByLabel('최대 예산').fill(budget)
  await page.getByRole('radio', { name: priority }).check()
  await page.getByRole('button', { name: 'Agent에게 실행안 요청' }).click()
}

async function approve(page: Page) {
  await expect(page.getByRole('region', { name: 'Agent 추천 실행안' })).toBeVisible()
  await page.getByRole('button', { name: '실행 승인' }).click()
  await page
    .getByRole('dialog', { name: '실행 승인' })
    .getByRole('button', { name: '승인하고 실행 시작' })
    .click()
  await expect(page.getByRole('region', { name: '실행 상태' })).toBeVisible()
}

async function completeJob(page: Page, request: APIRequestContext, outcome: 'SUCCEEDED' | 'FAILED') {
  const jobId = await page.evaluate((key) => localStorage.getItem(key), ACTIVE_JOB_KEY)
  expect(jobId, '실행 중인 Job ID를 복구용 저장소에서 찾을 수 있어야 한다').toBeTruthy()
  const res = await request.post(`/api/v1/internal/jobs/${jobId}/completion`, {
    data: {
      outcome,
      exitCode: outcome === 'SUCCEEDED' ? 0 : 1,
      message: outcome === 'SUCCEEDED' ? 'Training completed' : 'Training failed',
    },
  })
  expect(res.status(), '내부 완료 callback').toBe(204)
}

test.describe.configure({ mode: 'serial' })

test('e2e_backend_no_eligible_plan', async ({ page }) => {
  await requestPlan(page, '100', /저비용/)

  await expect(page.getByRole('alert')).toContainText(
    '이 예산 안에서 실행할 수 있는 GPU 후보가 없습니다.',
  )
  await expect(page.getByLabel('최대 예산')).toHaveValue('100')
})

test('e2e_backend_renders_server_plan_and_candidates', async ({ page }) => {
  await requestPlan(page, '10000', /균형/)

  const recommended = page.getByRole('region', { name: 'Agent 추천 실행안' })
  await expect(recommended).toBeVisible()
  await expect(recommended.getByText('Runpod')).toBeVisible()

  const comparison = page.getByRole('region', { name: 'GPU 후보 비교' })
  await expect(comparison.getByRole('row')).toHaveCount(4) // header + 후보 3개
  await expect(comparison.getByRole('button')).toHaveCount(0)

  // 내부 식별자가 화면에 새지 않는다.
  const text = (await page.locator('body').innerText()).toLowerCase()
  expect(text).not.toContain('profileid')
  expect(text).not.toContain('demo_snapshot')
  expect(text).not.toContain('runpod-')
})

test('e2e_backend_successful_execution_flow', async ({ page, request }) => {
  await requestPlan(page, '10000', /균형/)
  await approve(page)

  // 실행 환경 준비가 가장 오래 걸린다. 멈춘 것으로 읽히지 않게 안내가 보여야 한다.
  await expect(page.getByText('실행 환경을 준비하고 있어요')).toBeVisible()
  await expect(page.getByText(/몇 분/)).toBeVisible()

  await expect(page.getByText('학습을 실행하고 있어요')).toBeVisible({ timeout: 60_000 })
  await completeJob(page, request, 'SUCCEEDED')

  const result = page.getByRole('region', { name: '실행 결과' })
  await expect(result).toBeVisible({ timeout: 60_000 })
  await expect(result.getByText('학습이 완료됐어요')).toBeVisible()
  await expect(result.getByText('Training completed')).toBeVisible()
  await expect(result.getByText('실행 환경 자동 종료 완료')).toBeVisible()
})

test('e2e_backend_cancelled_execution_flow', async ({ page }) => {
  await requestPlan(page, '10000', /빠른 완료/)
  await approve(page)

  await page.getByRole('button', { name: '실행 중단' }).click()
  await page
    .getByRole('dialog', { name: '실행을 중단할까요?' })
    .getByRole('button', { name: '중단하기' })
    .click()

  const result = page.getByRole('region', { name: '실행 결과' })
  await expect(result).toBeVisible({ timeout: 60_000 })
  await expect(result.getByText('실행이 중단됐어요')).toBeVisible()
  await expect(result.getByText('실행 환경 자동 종료 완료')).toBeVisible()
})

test('e2e_backend_enforces_one_execution_per_browser', async ({ page, request }) => {
  await requestPlan(page, '10000', /균형/)
  await approve(page)
  await expect(page.getByText('학습을 실행하고 있어요')).toBeVisible({ timeout: 60_000 })
  await completeJob(page, request, 'SUCCEEDED')
  await expect(page.getByRole('region', { name: '실행 결과' })).toBeVisible({ timeout: 60_000 })

  // 실행 직후 남은 횟수가 화면에 반영돼야 한다. 새로고침해야 알게 되면 늦다.
  await expect(
    page.getByText('이 브라우저에서는 실제 실행을 한 번만 할 수 있습니다.'),
  ).toBeVisible()

  // 실행을 다 썼어도 결과 화면에 갇히지 않고 비용 없는 비교로 돌아갈 수 있다.
  await page.getByRole('button', { name: '다시 비교' }).click()
  await expect(page.getByLabel('최대 예산')).toBeVisible()

  await page.getByLabel('최대 예산').fill('10000')
  await page.getByRole('radio', { name: /균형/ }).check()
  await page.getByRole('button', { name: 'Agent에게 실행안 요청' }).click()
  await expect(page.getByRole('region', { name: 'Agent 추천 실행안' })).toBeVisible()
  await expect(
    page.getByText('이 브라우저에서는 실제 실행을 한 번만 할 수 있습니다.'),
  ).toBeVisible()
  await expect(page.getByRole('button', { name: '실행 승인' })).toBeDisabled()
})
