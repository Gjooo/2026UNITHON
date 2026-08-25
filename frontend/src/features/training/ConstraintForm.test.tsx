import { describe, expect, it } from 'vitest'
import { render, screen, within } from '@testing-library/react'
import { ConstraintForm } from './ConstraintForm'

describe('ConstraintForm', () => {
  it('renders_accessible_empty_constraint_form', () => {
    render(<ConstraintForm isSessionReady={false} />)

    const budget = screen.getByLabelText('최대 예산')
    expect(budget).toHaveValue(null)
    expect(budget).toHaveAccessibleDescription(
      '예상 비용은 실제 청구액을 제한하지 않으며, Agent는 검증된 데모 실행안 안에서 선택합니다.',
    )

    const priority = screen.getByRole('radiogroup', { name: '우선순위' })
    const options = within(priority).getAllByRole('radio')
    expect(options).toHaveLength(3)
    expect(options.map((option) => option.getAttribute('value'))).toEqual([
      'CHEAPEST',
      'BALANCED',
      'FASTEST',
    ])
    options.forEach((option) => expect(option).not.toBeChecked())
    expect(within(priority).getByRole('radio', { name: /저비용/ })).toBeInTheDocument()
    expect(within(priority).getByRole('radio', { name: /균형/ })).toBeInTheDocument()
    expect(within(priority).getByRole('radio', { name: /빠른 완료/ })).toBeInTheDocument()

    expect(screen.getByText('Stable Diffusion 1.5 LoRA')).toBeInTheDocument()
    expect(screen.getByText('24GB')).toBeInTheDocument()
    expect(screen.getByText('10분')).toBeInTheDocument()
    expect(screen.getByText('사전 검증된 데모 작업')).toBeInTheDocument()

    expect(
      screen.getByRole('button', { name: 'Agent에게 실행안 요청' }),
    ).toBeInTheDocument()
  })

  it('exposes_no_infrastructure_control_beyond_budget_and_priority', () => {
    render(<ConstraintForm isSessionReady />)

    expect(screen.getAllByRole('spinbutton')).toHaveLength(1)
    expect(screen.getAllByRole('radio')).toHaveLength(3)
    expect(screen.queryAllByRole('textbox')).toHaveLength(0)
    expect(screen.queryAllByRole('combobox')).toHaveLength(0)
    expect(screen.queryAllByRole('checkbox')).toHaveLength(0)
    expect(screen.getAllByRole('button')).toHaveLength(1)
  })
})
