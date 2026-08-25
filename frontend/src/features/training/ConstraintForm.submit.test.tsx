import { describe, expect, it, vi } from 'vitest'
import { render, screen, waitFor } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { ConstraintForm } from './ConstraintForm'

describe('ConstraintForm 제출', () => {
  it('submits_budget_and_priority_as_api_values', async () => {
    const user = userEvent.setup()
    const onSubmit = vi.fn()
    render(<ConstraintForm isSessionReady onSubmit={onSubmit} />)

    await user.type(screen.getByLabelText('최대 예산'), '10000')
    await user.click(screen.getByRole('radio', { name: /균형/ }))
    await user.click(screen.getByRole('button', { name: 'Agent에게 실행안 요청' }))

    await waitFor(() => expect(onSubmit).toHaveBeenCalledTimes(1))
    expect(onSubmit).toHaveBeenCalledWith({ maxBudgetKrw: 10000, priority: 'BALANCED' })
  })

  it('blocks_submission_until_budget_and_priority_are_valid', async () => {
    const user = userEvent.setup()
    const onSubmit = vi.fn()
    render(<ConstraintForm isSessionReady onSubmit={onSubmit} />)

    await user.click(screen.getByRole('button', { name: 'Agent에게 실행안 요청' }))

    expect(await screen.findByText('예산은 0보다 커야 합니다.')).toBeInTheDocument()
    expect(screen.getByText('우선순위를 선택해 주세요.')).toBeInTheDocument()
    expect(onSubmit).not.toHaveBeenCalled()
    expect(screen.getByLabelText('최대 예산')).toHaveAccessibleDescription(
      /예산은 0보다 커야 합니다/,
    )
  })
})
