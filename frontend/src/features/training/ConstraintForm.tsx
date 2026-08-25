import type { FormEvent } from 'react'
import styles from './ConstraintForm.module.css'
import { DEMO_SCENARIO, ESTIMATE_DISCLAIMER, PRIORITY_OPTIONS } from './scenario'

const DISCLAIMER_ID = 'constraint-estimate-disclaimer'
const PRIORITY_LABEL_ID = 'constraint-priority-label'

interface ConstraintFormProps {
  isSessionReady: boolean
}

/**
 * 사용자가 정하는 값은 최대 예산과 우선순위 둘뿐이다.
 * GPU 종류, 공급자, 실행 명령, 최대 실행 시간은 필드로도 고급 설정으로도 노출하지 않는다.
 */
export function ConstraintForm({ isSessionReady }: ConstraintFormProps) {
  function handleSubmit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault()
  }

  return (
    <form className={styles.form} onSubmit={handleSubmit} noValidate>
      <section className={styles.card}>
        <h2 className={styles.cardTitle}>실행 제약</h2>

        <div className={styles.scenario}>
          <div className={styles.scenarioHead}>
            <span className={styles.scenarioName}>{DEMO_SCENARIO.name}</span>
            <span className={styles.verifiedTag}>사전 검증된 데모 작업</span>
          </div>
          <dl className={styles.scenarioFacts}>
            <div>
              <dt>필요 VRAM</dt>
              <dd>{DEMO_SCENARIO.requiredVramGb}GB</dd>
            </div>
            <div>
              <dt>최대 실행 시간</dt>
              <dd>{DEMO_SCENARIO.maxRuntimeMinutes}분</dd>
            </div>
          </dl>
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
              name="maxBudgetKrw"
              type="number"
              inputMode="numeric"
              min={1}
              step={1}
              placeholder="10000"
              aria-describedby={DISCLAIMER_ID}
              
            />
          </div>
        </div>

        <div>
          <span className={styles.label} id={PRIORITY_LABEL_ID}>
            우선순위
          </span>
          <div
            className={styles.priorityGroup}
            role="radiogroup"
            aria-labelledby={PRIORITY_LABEL_ID}
          >
            {PRIORITY_OPTIONS.map((option) => (
              <label className={styles.priorityOption} key={option.value}>
                <input
                  className={styles.priorityRadio}
                  type="radio"
                  name="priority"
                  value={option.value}
                />
                <span className={styles.priorityTitle}>{option.title}</span>
                <span className={styles.priorityDescription}>{option.description}</span>
              </label>
            ))}
          </div>
        </div>

        <p className={styles.disclaimer} id={DISCLAIMER_ID}>
          {ESTIMATE_DISCLAIMER}
        </p>

        <button className={styles.submit} type="submit" disabled={!isSessionReady}>
          Agent에게 실행안 요청
        </button>
      </section>
    </form>
  )
}
