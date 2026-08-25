import { useState } from 'react'
import { useSession } from '@/hooks/useSession'
import { useCreateJob } from '@/hooks/useCreateJob'
import { useCancelJob, useJob, useStartJob } from '@/hooks/useJob'
import { ConstraintForm } from '@/features/training/ConstraintForm'
import { ExecutionPlanReview } from '@/features/training/ExecutionPlanReview'
import { ApprovalPanel } from '@/features/training/ApprovalPanel'
import { JobTracker } from '@/features/training/JobTracker'
import { toUserMessage } from '@/features/training/messages'
import styles from './App.module.css'

function SessionStatus() {
  const session = useSession()

  const { dotClass, textClass, label } = session.isSuccess
    ? { dotClass: styles.statusReady, textClass: styles.sessionReady, label: '익명 세션' }
    : session.isError
      ? {
          dotClass: styles.statusFailed,
          textClass: styles.sessionFailed,
          label: '세션을 시작하지 못했어요',
        }
      : { dotClass: styles.statusPending, textClass: styles.sessionReady, label: '세션 준비 중' }

  return (
    <p className={`${styles.sessionStatus} ${textClass}`} aria-live="polite">
      <span className={`${styles.statusDot} ${dotClass}`} aria-hidden="true" />
      {label}
    </p>
  )
}

export function App() {
  const session = useSession()
  const [jobId, setJobId] = useState<string | null>(null)

  const createJob = useCreateJob((created) => setJobId(created.id))
  const startJob = useStartJob()
  const cancelJob = useCancelJob()

  // 서버 Job이 화면의 source of truth다. mutation 응답으로 상태를 추정하지 않는다.
  const job = useJob(jobId).data ?? null

  const allowance = session.data?.executionAllowance
  const canStart = !allowance || allowance.used < allowance.limit

  if (job && job.status !== 'DRAFT') {
    return (
      <Shell>
        <h1 className={styles.pageTitle}>실행 상태</h1>
        <div className={styles.content}>
          {cancelJob.isError && (
            <p className={styles.formAlert} role="alert">
              {toUserMessage(cancelJob.error)}
            </p>
          )}
          <JobTracker
            job={job}
            isCancelling={cancelJob.isPending}
            onCancel={() => cancelJob.mutate(job.id)}
          />
        </div>
      </Shell>
    )
  }

  if (job) {
    return (
      <Shell>
        <h1 className={styles.pageTitle}>Agent가 실행안을 비교했어요</h1>
        <p className={styles.pageLead}>
          아래 실행 계약은 Agent가 고정한 값입니다. GPU를 직접 바꾸지 않습니다.
        </p>
        <div className={styles.content}>
          {startJob.isError && (
            <p className={styles.formAlert} role="alert">
              {toUserMessage(startJob.error)}
            </p>
          )}
          <ExecutionPlanReview job={job} />
          <div className={styles.panelGap}>
            <ApprovalPanel
              job={job}
              canStart={canStart}
              isStarting={startJob.isPending}
              onApprove={() => startJob.mutate(job.id)}
              onEditConstraints={() => setJobId(null)}
            />
          </div>
        </div>
      </Shell>
    )
  }

  return (
    <Shell>
      <h1 className={styles.pageTitle}>예산과 우선순위만 정하면 됩니다</h1>
      <p className={styles.pageLead}>
        Agent가 검증된 GPU 후보를 비교해 실행안을 추천합니다. GPU 콘솔, SSH, CUDA 설정은
        다루지 않습니다.
      </p>
      <div className={styles.content}>
        {createJob.isError && (
          <p className={styles.formAlert} role="alert">
            {toUserMessage(createJob.error)}
          </p>
        )}
        <ConstraintForm
          isSessionReady={session.isSuccess}
          isSubmitting={createJob.isPending}
          onSubmit={createJob.mutate}
        />
      </div>
    </Shell>
  )
}

function Shell({ children }: { children: React.ReactNode }) {
  return (
    <div className={styles.app}>
      <header className={styles.header}>
        <span className={styles.wordmark}>UNWORK</span>
        <SessionStatus />
      </header>
      <main className={styles.main}>{children}</main>
    </div>
  )
}
