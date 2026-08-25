import { useForm } from 'react-hook-form'
import { zodResolver } from '@hookform/resolvers/zod'
import { z } from 'zod'
import type { CreateJobInput } from '@/api/jobs'
import { Button } from '@/components/ui/Button'
import styles from './ConstraintForm.module.css'
import { ESTIMATE_DISCLAIMER, PRIORITY_OPTIONS } from './scenario'

const schema = z.object({
  maxBudgetKrw: z.coerce
    .number()
    .int('예산은 정수로 입력해 주세요.')
    .positive('예산은 0보다 커야 합니다.'),
  priority: z.enum(['CHEAPEST', 'BALANCED', 'FASTEST'], {
    error: '우선순위를 선택해 주세요.',
  }),
})

const DISCLAIMER_ID = 'constraint-estimate-disclaimer'
const PRIORITY_LABEL_ID = 'constraint-priority-label'
const BUDGET_ERROR_ID = 'constraint-budget-error'
const PRIORITY_ERROR_ID = 'constraint-priority-error'

interface ConstraintFormProps {
  isSessionReady: boolean
  isSubmitting?: boolean
  onSubmit?: (input: CreateJobInput) => void
}

/**
 * 사용자가 정하는 값은 최대 예산과 우선순위 둘뿐이다.
 * GPU 종류, 공급자, 실행 명령, 최대 실행 시간은 필드로도 고급 설정으로도 노출하지 않는다.
 */
export function ConstraintForm({
  isSessionReady,
  isSubmitting = false,
  onSubmit,
}: ConstraintFormProps) {
  const {
    register,
    handleSubmit,
    formState: { errors },
  } = useForm({ resolver: zodResolver(schema), mode: 'onSubmit' })

  const submit = handleSubmit((values) => onSubmit?.(values as CreateJobInput))

  return (
    <form className={styles.form} onSubmit={submit} noValidate>
      <section className={styles.card}>
        <h2 className={styles.cardTitle}>학습 실행 요청</h2>

        <div className={styles.scenario}>
          <span className={styles.verifiedTag}>사전 검증된 고정 작업</span>
          <p className={styles.scenarioNote}>
            학습 코드와 실행 명령은 Agent가 검증해 고정했습니다. 필요 VRAM과 최대 실행
            시간은 Agent가 만든 실행안에서 확인할 수 있습니다.
          </p>
        </div>

        <div>
          <label className={styles.label} htmlFor="max-budget">
            최대 예산
          </label>
          <div className={styles.budgetField}>
            <span className={styles.budgetPrefix} aria-hidden="true">
              ₩
            </span>
            <input
              className={styles.budgetInput}
              id="max-budget"
              type="number"
              inputMode="numeric"
              min={1}
              step={1}
              placeholder="10000"
              aria-describedby={
                errors.maxBudgetKrw ? `${BUDGET_ERROR_ID} ${DISCLAIMER_ID}` : DISCLAIMER_ID
              }
              aria-invalid={errors.maxBudgetKrw ? true : undefined}
              {...register('maxBudgetKrw')}
            />
          </div>
          {errors.maxBudgetKrw && (
            <p className={styles.fieldError} id={BUDGET_ERROR_ID}>
              {errors.maxBudgetKrw.message}
            </p>
          )}
        </div>

        <div>
          <span className={styles.label} id={PRIORITY_LABEL_ID}>
            우선순위
          </span>
          <div
            className={styles.priorityGroup}
            role="radiogroup"
            aria-labelledby={PRIORITY_LABEL_ID}
            aria-describedby={errors.priority ? PRIORITY_ERROR_ID : undefined}
          >
            {PRIORITY_OPTIONS.map((option) => (
              <label className={styles.priorityOption} key={option.value}>
                <input
                  className={styles.priorityRadio}
                  type="radio"
                  value={option.value}
                  {...register('priority')}
                />
                <span className={styles.priorityTitle}>{option.title}</span>
                <span className={styles.priorityDescription}>{option.description}</span>
              </label>
            ))}
          </div>
          {errors.priority && (
            <p className={styles.fieldError} id={PRIORITY_ERROR_ID}>
              {errors.priority.message}
            </p>
          )}
        </div>

        <p className={styles.disclaimer} id={DISCLAIMER_ID}>
          {ESTIMATE_DISCLAIMER}
        </p>

        <Button
          className={styles.submit}
          variant="primary"
          type="submit"
          disabled={!isSessionReady || isSubmitting}
        >
          Agent에게 실행안 요청
        </Button>
      </section>
    </form>
  )
}
