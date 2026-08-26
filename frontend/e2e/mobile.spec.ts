import { expect, test } from '@playwright/test'

test('e2e_mobile_contract_review', async ({ page }) => {
  await page.goto('/')
  await page.getByRole('button', { name: '시작하기' }).first().click()
  await page.getByLabel('Runpod API 키').fill('rpa_e2e_fake_key')
  await page.getByRole('button', { name: '연결하기' }).click()
  await expect(page.getByText(/Runpod 연결됨/)).toBeVisible()
  await page.getByLabel('최대 예산').fill('10000')
  await page.getByRole('radio', { name: /균형/ }).check()
  await page.getByRole('button', { name: 'Agent에게 실행안 요청' }).click()

  await expect(page.getByRole('region', { name: 'Agent 추천 실행안' })).toBeVisible()

  // 표가 화면 밖 가로 스크롤에 의존하지 않는다.
  const overflow = await page.evaluate(
    () => document.documentElement.scrollWidth - document.documentElement.clientWidth,
  )
  expect(overflow).toBeLessThanOrEqual(1)

  // 승인 CTA가 화면 안에서 닿는다.
  const approve = page.getByRole('button', { name: '실행 승인' })
  await approve.scrollIntoViewIfNeeded()
  const box = await approve.boundingBox()
  expect(box?.height ?? 0).toBeGreaterThanOrEqual(36)
})
