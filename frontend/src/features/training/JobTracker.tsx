import { useEffect, useState } from 'react'
import { Dialog } from '@/components/ui/Dialog'
import type { JobStatus, TrainingJob } from '@/api/jobs'
import { isInFlight } from '@/hooks/useJob'
import { formatElapsed } from './format'
import styles from './JobTracker.module.css'

const TITLE: Record<JobStatus, string> = {
  DRAFT: '실행 승인을 기다리고 있어요',
  PROVISIONING: '실행 환경을 준비하고 있어요',
  RUNNING: '학습을 실행하고 있어요',
  TERMINATING: '실행 환경 종료를 확인하고 있어요',
  COMPLETED: '학습이 완료됐어요',
  FAILED: '학습이 완료되지 않았어요',
  CANCELLED: '실행이 중단됐어요',
}

const STEPS = ['실행 환경 준비', '학습 실행', '종료 확인'] as const

/**
 * 실측상 환경 준비가 가장 오래 걸린다(이미지 내려받기·모델 로딩).
 * 안내가 없으면 사용자가 멈춘 것으로 읽는다.
 */
const HINT: Partial<Record<JobStatus, string>> = {
  PROVISIONING:
    'GPU를 확보하고 학습 이미지를 내려받는 중입니다. 이 단계가 가장 오래 걸리며 몇 분 정도 걸릴 수 있어요.',
}

/** 상태별로 어느 단계까지 왔는지. 최종 상태는 모든 단계가 끝난 것으로 본다. */
const ACTIVE_STEP: Record<JobStatus, number> = {
  DRAFT: -1,
  PROVISIONING: 0,
  RUNNING: 1,
  TERMINATING: 2,
  COMPLETED: 3,
  FAILED: 3,
  CANCELLED: 3,
}

const CANCELLABLE: ReadonlySet<JobStatus> = new Set<JobStatus>(['PROVISIONING', 'RUNNING'])

function useNow(enabled: boolean): number {
  const [now, setNow] = useState(() => Date.now())

  useEffect(() => {
    if (!enabled) return
    const timer = window.setInterval(() => setNow(Date.now()), 1000)
    return () => window.clearInterval(timer)
  }, [enabled])

  return now
}

interface JobTrackerProps {
  job: TrainingJob
  isCancelling: boolean
  onCancel: () => void
}

export function JobTracker({ job, isCancelling, onCancel }: JobTrackerProps) {
  const [isDialogOpen, setDialogOpen] = useState(false)
  const inFlight = isInFlight(job.status)
  const now = useNow(inFlight)
  const activeStep = ACTIVE_STEP[job.status]

  return (
    <section className={styles.tracker} aria-label="실행 상태">
      <div className={styles.head}>
        <h2 className={styles.title} aria-live="polite">
          {TITLE[job.status]}
        </h2>
        <p className={styles.gpu}>
          Agent가 선택한 GPU · {job.executionPlan.recommended.gpuType} ·{' '}
          {job.executionPlan.recommended.provider}
        </p>
        {HINT[job.status] && <p className={styles.hint}>{HINT[job.status]}</p>}
      </div>

      <ol className={styles.steps}>
        {STEPS.map((step, index) => {
          const state =
            index < activeStep ? '완료' : index === activeStep ? '진행 중' : '대기'
          const markerClass =
            index < activeStep
              ? styles.markerDone
              : index === activeStep
                ? styles.markerActive
                : styles.markerPending
          return (
            <li className={styles.step} key={step}>
              <span className={`${styles.marker} ${markerClass}`} aria-hidden="true" />
              <span>
                <span className={styles.stepLabel}>{step}</span>
                <span className={styles.stepState}>{state}</span>
              </span>
            </li>
          )
        })}
      </ol>

      <dl className={styles.figures}>
        <div>
          <dt>경과 시간</dt>
          <dd data-testid="elapsed">{formatElapsed(job.startedAt, now)}</dd>
          <p className={styles.cap}>최대 {job.scenario.maxRuntimeMinutes}분</p>
        </div>
      </dl>

      {CANCELLABLE.has(job.status) && (
        <button
          className={styles.cancel}
          type="button"
          disabled={isCancelling}
          onClick={() => setDialogOpen(true)}
        >
          실행 중단
        </button>
      )}

      {isDialogOpen && (
        <Dialog
          title="실행을 중단할까요?"
          onClose={() => setDialogOpen(false)}
          actions={
            <>
              <button
                className={styles.dialogSecondary}
                type="button"
                onClick={() => setDialogOpen(false)}
              >
                계속 실행
              </button>
              <button
                className={styles.dialogDanger}
                type="button"
                disabled={isCancelling}
                onClick={() => {
                  setDialogOpen(false)
                  onCancel()
                }}
              >
                중단하기
              </button>
            </>
          }
        >
          <p>
            지금까지 진행한 학습은 사라지고 결과를 받을 수 없습니다. 중단해도 이미 사용한
            시간에 대한 비용은 발생할 수 있습니다.
          </p>
        </Dialog>
      )}
    </section>
  )
}
