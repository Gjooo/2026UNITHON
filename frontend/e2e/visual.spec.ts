import { expect, test, type Page } from '@playwright/test'

/** 경과 시간처럼 매번 달라지는 값은 가려서 비교한다. */
function volatile(page: Page) {
  return [page.getByTestId('elapsed')]
}

async function noHorizontalOverflow(page: Page) {
  const overflow = await page.evaluate(
    () => document.documentElement.scrollWidth - document.documentElement.clientWidth,
  )
  expect(overflow, '본문이 가로로 넘치면 안 된다').toBeLessThanOrEqual(1)
}

async function requestPlan(page: Page) {
  await page.goto('/')
  await page.getByRole('button', { name: '시작하기' }).first().click()
  await page.getByLabel('Runpod API 키').fill('rpa_e2e_fake_key')
  await page.getByRole('button', { name: '연결하기' }).click()
  await expect(page.getByText(/Runpod 연결됨/)).toBeVisible()
  await page.getByLabel('최대 예산').fill('10000')
  await page.getByRole('radio', { name: /균형/ }).check()
  await page.getByRole('button', { name: 'Agent에게 실행안 요청' }).click()
  await expect(page.getByRole('region', { name: 'Agent 추천 실행안' })).toBeVisible()
}

test('00_landing', async ({ page }) => {
  await page.goto('/')
  await expect(page.getByRole('heading', { level: 1 })).toBeVisible()
  await noHorizontalOverflow(page)
  await expect(page).toHaveScreenshot('00-landing.png', { fullPage: true })
})

test('00b_provider_connection', async ({ page }) => {
  await page.goto('/')
  await page.getByRole('button', { name: '시작하기' }).first().click()
  await expect(page.getByLabel('Runpod API 키')).toBeVisible()
  await noHorizontalOverflow(page)
  await expect(page).toHaveScreenshot('00b-provider-connection.png', { fullPage: true })
})

test('01_constraint_form', async ({ page }) => {
  await page.goto('/')
  await page.getByRole('button', { name: '시작하기' }).first().click()
  await page.getByLabel('Runpod API 키').fill('rpa_e2e_fake_key')
  await page.getByRole('button', { name: '연결하기' }).click()
  await expect(page.getByText(/Runpod 연결됨/)).toBeVisible()
  await noHorizontalOverflow(page)
  await expect(page).toHaveScreenshot('01-constraint-form.png', { fullPage: true })
})

test('02_execution_plan_review', async ({ page }) => {
  await requestPlan(page)
  await noHorizontalOverflow(page)
  await expect(page).toHaveScreenshot('02-plan-review.png', { fullPage: true })
})

test('03_approval_dialog', async ({ page }) => {
  await requestPlan(page)
  await page.getByRole('button', { name: '실행 승인' }).click()
  const dialog = page.getByRole('dialog', { name: '실행 승인' })
  await expect(dialog).toBeVisible()
  // 배경 페이지의 스크롤 위치에 흔들리지 않도록 dialog만 비교한다.
  await expect(dialog).toHaveScreenshot('03-approval-dialog.png')
})

test('04_execution_tracking', async ({ page }) => {
  await requestPlan(page)
  await page.getByRole('button', { name: '실행 승인' }).click()
  await page
    .getByRole('dialog', { name: '실행 승인' })
    .getByRole('button', { name: '승인하고 실행 시작' })
    .click()
  await expect(page.getByText('실행 환경을 준비하고 있어요')).toBeVisible()
  await noHorizontalOverflow(page)
  await expect(page).toHaveScreenshot('04-tracking.png', {
    fullPage: true,
    mask: volatile(page),
  })
})
