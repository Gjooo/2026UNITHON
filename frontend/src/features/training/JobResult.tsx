import { useId, useState } from 'react'
import type { TrainingJob } from '@/api/jobs'
import { formatElapsed } from './format'
import { EXECUTION_LIMIT_NOTICE } from './ApprovalPanel'
import styles from './JobResult.module.css'

const TITLE: Record<string, string> = {
  COMPLETED: '학습이 완료됐어요',
  FAILED: '학습이 완료되지 않았어요',
  CANCELLED: '실행이 중단됐어요',
}

function formatTime(value: string | null): string {
  if (!value) return '기록 없음'
  return new Date(value).toLocaleString('ko-KR', { timeZone: 'Asia/Seoul' })
}

interface JobResultProps {
  job: TrainingJob
  canStartAnother: boolean
  onStartAnother: () => void
}

export function JobResult({ job, canStartAnother, onStartAnother }: JobResultProps) {
  const [detailOpen, setDetailOpen] = useState(false)
  const detailId = useId()
  const succeeded = job.status === 'COMPLETED'
  const titleClass = succeeded
    ? styles.titleOk
    : job.status === 'FAILED'
      ? styles.titleFailed
      : styles.titleCancelled

  const runtime = job.finishedAt ? formatElapsed(job.startedAt, Date.parse(job.finishedAt)) : '기록 없음'

  return (
    <section className={styles.result} aria-label="실행 결과">
      <div className={styles.head}>
        <h2 className={`${styles.title} ${titleClass}`}>{TITLE[job.status]}</h2>
        {job.podTerminatedAt ? (
          <p className={styles.teardown}>
            <span aria-hidden="true">✓</span> 실행 환경 자동 종료 완료
          </p>
        ) : (
          <p className={styles.teardownPending}>
            <span aria-hidden="true">!</span> 실행 환경 종료를 아직 확인하지 못했습니다
          </p>
        )}
      </div>

      {job.failureMessage && <p className={styles.failureMessage}>{job.failureMessage}</p>}

      {succeeded && job.completionLog && <pre className={styles.log}>{job.completionLog}</pre>}

      <dl className={styles.facts}>
        <div>
          <dt>선택된 GPU</dt>
          <dd>{job.executionPlan.recommended.gpuType}</dd>
        </div>
        <div>
          <dt>실행 시간</dt>
          <dd>{runtime}</dd>
        </div>
        <div>
          <dt>{succeeded ? '종료 코드' : '완료 시각'}</dt>
          <dd>{succeeded ? String(job.exitCode) : formatTime(job.finishedAt)}</dd>
        </div>
      </dl>

      {!succeeded && (job.exitCode !== null || job.completionLog) && (
        <>
          <button
            className={styles.disclosureToggle}
            type="button"
            aria-expanded={detailOpen}
            aria-controls={detailId}
            onClick={() => setDetailOpen((open) => !open)}
          >
            세부 정보
          </button>
          <div className={styles.detail} id={detailId} hidden={!detailOpen}>
            {job.exitCode !== null && (
              <dl className={styles.facts}>
                <div>
                  <dt>종료 코드</dt>
                  <dd>{String(job.exitCode)}</dd>
                </div>
                <div>
                  <dt>시작 시각</dt>
                  <dd>{formatTime(job.startedAt)}</dd>
                </div>
              </dl>
            )}
            {job.completionLog && job.completionLog !== job.failureMessage && (
              <pre className={styles.log}>{job.completionLog}</pre>
            )}
          </div>
        </>
      )}

      {canStartAnother ? (
        <button className={styles.restart} type="button" onClick={onStartAnother}>
          새 실행안 만들기
        </button>
      ) : (
        <>
          <p className={styles.limitNotice}>
            {EXECUTION_LIMIT_NOTICE} 비용이 들지 않는 비교는 계속할 수 있습니다.
          </p>
          {/* 실행을 다 썼다고 결과 화면에 가둬 두지 않는다. */}
          <button className={styles.compareAgain} type="button" onClick={onStartAnother}>
            다시 비교
          </button>
        </>
      )}
    </section>
  )
}
