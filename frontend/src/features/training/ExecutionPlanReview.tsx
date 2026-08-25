import { useId, useState } from 'react'
import type { TrainingJob } from '@/api/jobs'
import { formatKrw, formatMinutes } from './format'
import { ELIGIBILITY_LABEL, PRIORITY_LABEL, priceDataTypeLabel } from './messages'
import styles from './ExecutionPlanReview.module.css'

/**
 * POST /jobs 응답 전체가 이 화면의 유일한 데이터 원본이다.
 * 클라이언트는 추천 순위·비용·시간을 재계산하지 않는다.
 */
export function ExecutionPlanReview({ job }: { job: TrainingJob }) {
  const { scenario, constraint, executionPlan } = job
  const { recommended, candidates } = executionPlan
  const [workloadOpen, setWorkloadOpen] = useState(false)
  const workloadId = useId()

  return (
    <div className={styles.review}>
      <section
        className={`${styles.card} ${styles.recommendedCard}`}
        aria-label="Agent 추천 실행안"
      >
        <div className={styles.cardHead}>
          <h2 className={styles.cardTitle}>Agent 추천 실행안</h2>
          <span className={styles.recommendBadge}>추천</span>
        </div>
        <div>
          <p className={styles.gpuName}>{recommended.gpuType}</p>
          <p className={styles.provider}>{recommended.provider}</p>
        </div>
        <dl className={styles.figures}>
          <div>
            <dt>예상 실행 시간</dt>
            <dd>{formatMinutes(recommended.estimatedRuntimeMinutes)}</dd>
          </div>
          <div>
            <dt>예상 GPU 비용</dt>
            <dd>{formatKrw(recommended.estimatedGpuCostKrw)}</dd>
          </div>
        </dl>
        <p className={styles.reason}>{recommended.reason}</p>
      </section>

      <section className={styles.card} aria-label="GPU 후보 비교">
        <h2 className={styles.cardTitle}>GPU 후보 비교</h2>
        <div className={styles.tableWrap}>
          <table className={styles.table}>
            <thead>
              <tr>
                <th scope="col">GPU</th>
                <th scope="col">예상 시간</th>
                <th scope="col">예상 GPU 비용</th>
                <th scope="col">예산 적합 여부</th>
                <th scope="col">추천 여부</th>
              </tr>
            </thead>
            <tbody>
              {candidates.map((candidate) => {
                const eligible = candidate.eligibility === 'ELIGIBLE'
                return (
                  <tr key={candidate.profileId}>
                    <th scope="row">{candidate.gpuType}</th>
                    <td className={styles.numeric}>
                      {formatMinutes(candidate.estimatedRuntimeMinutes)}
                    </td>
                    <td className={styles.numeric}>
                      {formatKrw(candidate.estimatedGpuCostKrw)}
                    </td>
                    <td className={eligible ? styles.statusOk : styles.statusWarn}>
                      {ELIGIBILITY_LABEL[candidate.eligibility]}
                    </td>
                    <td>
                      {candidate.profileId === recommended.profileId ? '추천' : '선택 안 함'}
                    </td>
                  </tr>
                )
              })}
            </tbody>
          </table>
        </div>
      </section>

      <section className={styles.card} aria-label="실행 계약 정보">
        <div className={styles.cardHead}>
          <h2 className={styles.cardTitle}>실행 계약 정보</h2>
          <span className={styles.priceTag}>
            {priceDataTypeLabel(executionPlan.priceDataType)}
          </span>
        </div>
        <dl className={styles.facts}>
          <div>
            <dt>고정 학습 작업</dt>
            <dd>{scenario.name}</dd>
          </div>
          <div>
            <dt>필요 VRAM</dt>
            <dd>{scenario.requiredVramGb}GB</dd>
          </div>
          <div>
            <dt>최대 예산</dt>
            <dd>{formatKrw(constraint.maxBudgetKrw)}</dd>
          </div>
          <div>
            <dt>우선순위</dt>
            <dd>{PRIORITY_LABEL[constraint.priority]}</dd>
          </div>
          <div>
            <dt>최대 실행 시간</dt>
            <dd>{scenario.maxRuntimeMinutes}분</dd>
          </div>
        </dl>
        <p className={styles.disclaimer}>{executionPlan.estimateDisclaimer}</p>

        <button
          className={styles.disclosureToggle}
          type="button"
          aria-expanded={workloadOpen}
          aria-controls={workloadId}
          onClick={() => setWorkloadOpen((open) => !open)}
        >
          고정 워크로드 정보
        </button>
        <div className={styles.disclosureBody} id={workloadId} hidden={!workloadOpen}>
          <span>{scenario.repositoryUrl}</span>
          <span>{scenario.executionCommand}</span>
        </div>
      </section>
    </div>
  )
}
