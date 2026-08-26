import { expect, test } from '@playwright/test'

/**
 * 실제 Provider로 한 번만 완주하는 smoke.
 *
 * 이 파일은 실제 GPU를 만들고 실제 비용을 발생시킨다. CI·일반 test script에
 * 포함하지 않는다. RUN_REAL_RUNPOD_SMOKE=true 없이는 실행되지 않는다.
 *
 * 학습 컨테이너가 스스로 완료 callback을 보내므로 테스트는 callback을 치지
 * 않는다. 브라우저에서 시작한 실행이 자원 종료 확인까지 가는지만 본다.
 */
const ARMED = process.env.RUN_REAL_RUNPOD_SMOKE === 'true'

test.skip(!ARMED, 'RUN_REAL_RUNPOD_SMOKE=true 없이는 실제 GPU를 만들지 않는다')

test('smoke_real_execution_reaches_confirmed_teardown', async ({ page }) => {
  test.setTimeout(25 * 60 * 1000)

  await page.goto('/')
  await page.getByRole('button', { name: '시작하기' }).first().click()
  await page.getByLabel('Runpod API 키').fill('rpa_e2e_fake_key')
  await page.getByRole('button', { name: '연결하기' }).click()
  await expect(page.getByText(/Runpod 연결됨/)).toBeVisible()

  await page.getByLabel('최대 예산').fill('10000')
  await page.getByRole('radio', { name: /균형/ }).check()
  await page.getByRole('button', { name: 'Agent에게 실행안 요청' }).click()

  const recommended = page.getByRole('region', { name: 'Agent 추천 실행안' })
  await expect(recommended).toBeVisible()
  const gpu = await recommended.locator('p').first().innerText()
  console.log(`추천 GPU: ${gpu}`)

  await page.getByRole('button', { name: '실행 승인' }).click()
  await page
    .getByRole('dialog', { name: '실행 승인' })
    .getByRole('button', { name: '승인하고 실행 시작' })
    .click()

  const startedAt = Date.now()
  await expect(page.getByText('실행 환경을 준비하고 있어요')).toBeVisible()
  // 실측상 이 구간이 가장 길다. 안내가 없으면 멈춘 것으로 읽힌다.
  await expect(page.getByText(/몇 분/)).toBeVisible()
  console.log('PROVISIONING 진입')

  // 상태를 순서대로 다 거친다고 가정하지 않는다. 학습이 짧으면 RUNNING을 건너뛴다.
  const result = page.getByRole('region', { name: '실행 결과' })
  await expect(result).toBeVisible({ timeout: 20 * 60 * 1000 })
  console.log(`최종 상태 도달까지 ${Math.round((Date.now() - startedAt) / 1000)}초`)

  const text = await result.innerText()
  console.log(text)

  // 결과가 무엇이든 자원 종료 확인이 최우선이다.
  await expect(
    result.getByText('실행 환경 자동 종료 완료'),
    '자원 종료가 확인되지 않았다. Provider 콘솔에서 직접 정리해야 한다.',
  ).toBeVisible()

  // 사용자에게 안전한 화면인지도 같이 본다.
  expect(text).not.toMatch(/pod|api[_-]?key|Bearer|runpod-/i)
})
