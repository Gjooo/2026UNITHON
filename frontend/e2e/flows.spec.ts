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
  // 실제 GPU에서 RUNNING은 몇 초라 폴링이 건너뛸 수 있다. 관찰을 요구하지 않는다.
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

test('e2e_completes_the_contract_with_keyboard_only', async ({ page }) => {
  await page.goto('/')
  await expect(page.getByText('익명 세션')).toBeVisible()

  // 예산 입력까지 Tab으로 닿는다.
  const budget = page.getByLabel('최대 예산')
  await budget.focus()
  await page.keyboard.type('10000')

  // radiogroup은 화살표로 조작한다. radio가 시각적으로 숨겨져 있어도 닿아야 한다.
  await page.keyboard.press('Tab')
  const first = page.getByRole('radio', { name: /저비용/ })
  await expect(first).toBeFocused()
  await page.keyboard.press('ArrowDown')
  await expect(page.getByRole('radio', { name: /균형/ })).toBeChecked()

  // 선택된 카드에 보이는 focus 표시가 있어야 한다.
  const outline = await page.evaluate(() => {
    const input = document.querySelector('input[type=radio]:focus') as HTMLElement | null
    const card = input?.closest('label') as HTMLElement | null
    return card ? getComputedStyle(card).outlineStyle : 'none'
  })
  expect(outline, '포커스된 우선순위 카드에 보이는 외곽선이 있어야 한다').not.toBe('none')

  await page.keyboard.press('Tab')
  await expect(page.getByRole('button', { name: 'Agent에게 실행안 요청' })).toBeFocused()
  await page.keyboard.press('Enter')

  await expect(page.getByRole('region', { name: 'Agent 추천 실행안' })).toBeVisible()

  // 승인 dialog도 키보드로 열고 닫는다.
  await page.getByRole('button', { name: '실행 승인' }).focus()
  await page.keyboard.press('Enter')
  const dialog = page.getByRole('dialog', { name: '실행 승인' })
  await expect(dialog).toBeVisible()
  await expect(dialog.getByRole('button', { name: '취소' })).toBeFocused()

  await page.keyboard.press('Escape')
  await expect(dialog).toBeHidden()
  await expect(page.getByRole('button', { name: '실행 승인' })).toBeFocused()
})

test('e2e_start_error_is_not_covered_by_the_dialog', async ({ page, request }) => {
  await request.post('http://127.0.0.1:8787/__fake/busy', { data: { busy: true } })

  await requestPlan(page, '10000', /균형/)
  await page.getByRole('button', { name: '실행 승인' }).click()
  await page
    .getByRole('dialog', { name: '실행 승인' })
    .getByRole('button', { name: '승인하고 실행 시작' })
    .click()

  const alert = page.getByRole('alert')
  await expect(alert).toBeVisible()

  // 페이지가 길다. 승인 버튼은 아래, 오류는 위에 있어 시야 밖에 나타날 수 있다.
  await expect(alert).toBeInViewport()

  // toBeVisible()은 다른 요소에 덮였는지 보지 않는다. dialog가 fixed overlay라
  // 열린 채로 두면 alert가 화면에 있으면서도 보이지 않는다. 실제로 위에 있는
  // 요소가 alert인지 좌표로 확인한다.
  const stacking = await page.evaluate(() => {
    const el = document.querySelector('[role="alert"]')
    if (!el) return 'no-alert'
    const r = el.getBoundingClientRect()
    const top = document.elementFromPoint(r.left + r.width / 2, r.top + r.height / 2)
    return top && el.contains(top) ? 'on-top' : 'covered'
  })
  expect(stacking, '오류 문구가 dialog에 덮이면 사용자는 아무 반응도 없다고 느낀다').toBe('on-top')

  await expect(page.getByRole('button', { name: '실행 승인' })).toBeEnabled()
  await request.post('http://127.0.0.1:8787/__fake/busy', { data: { busy: false } })
})
