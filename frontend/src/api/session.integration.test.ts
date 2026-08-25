import { describe, expect, it } from 'vitest'
import { createSession } from './session'

describe('createSession', () => {
  it('returns_remaining_execution_allowance_from_the_server', async () => {
    const session = await createSession()

    // 실행 버튼을 누르기 전에 남은 횟수를 안내할 수 있어야 한다.
    expect(session.executionAllowance).toEqual({ used: 0, limit: 1 })
  })
})
