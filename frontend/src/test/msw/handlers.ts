import { http, HttpResponse } from 'msw'
import sessionFixture from '../fixtures/session.json'
import provisioningJob from '../fixtures/jobs/provisioning.json'

/**
 * MVP REST 계약을 흉내 내는 stateful handler 모음.
 * fixture는 백엔드가 계산한 값을 대신하는 독립 명세 데이터이며,
 * UI 코드와 같은 방식으로 비용·추천을 다시 계산하지 않는다.
 */
export function createFakeMvpApi() {
  return [
    http.post('*/api/v1/session', () =>
      HttpResponse.json(sessionFixture, { status: 201 }),
    ),
    http.get('*/api/v1/jobs/:jobId', () => HttpResponse.json(provisioningJob)),
  ]
}
