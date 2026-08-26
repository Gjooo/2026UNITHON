import { describe, expect, it } from 'vitest'
import { createSession } from './session'

describe('createSession', () => {
  it('tells_whether_this_deployment_can_run_real_gpus', async () => {
    const session = await createSession()

    expect(session.expiresAt).toBeTruthy()
    // false면 화면이 실제 실행 선택지를 만들지 않는다.
    expect(typeof session.realExecutionAvailable).toBe('boolean')
  })
})
