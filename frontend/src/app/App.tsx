import { useEffect, useRef, useState, type ReactNode } from 'react'
import { ApiError } from '@/api/errors'
import { useSession } from '@/hooks/useSession'
import { useCreateJob } from '@/hooks/useCreateJob'
import { isTerminal, useCancelJob, useJob, useStartJob } from '@/hooks/useJob'
import { ConstraintForm } from '@/features/training/ConstraintForm'
import { ExecutionPlanReview } from '@/features/training/ExecutionPlanReview'
import { ApprovalPanel } from '@/features/training/ApprovalPanel'
import { JobTracker } from '@/features/training/JobTracker'
import { JobResult } from '@/features/training/JobResult'
import { clearActiveJobId, readActiveJobId } from '@/features/training/activeJob'
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
  const [jobId, setJobId] = useState<string | null>(() => readActiveJobId())
  const [recoveryNotice, setRecoveryNotice] = useState<string | null>(null)

  const createJob = useCreateJob((created) => {
    setRecoveryNotice(null)
    setJobId(created.id)
  })
  const startJob = useStartJob()
  const cancelJob = useCancelJob()

  // 서버 Job이 화면의 source of truth다. mutation 응답으로 상태를 추정하지 않는다.
  const jobQuery = useJob(jobId)
  const job = jobQuery.data ?? null

  const allowance = session.data?.executionAllowance
  const canStart = !allowance || allowance.used < allowance.limit

  // 소유권이 없거나 세션이 끝난 Job은 저장값을 지우고 새 흐름으로 돌아간다.
  const jobError = jobQuery.error
  useEffect(() => {
    if (!(jobError instanceof ApiError)) return
    if (jobError.status !== 401 && jobError.status !== 404) return
    clearActiveJobId()
    setJobId(null)
    setRecoveryNotice(toUserMessage(jobError))
  }, [jobError])

  function startAnother() {
    clearActiveJobId()
    setRecoveryNotice(null)
    setJobId(null)
  }

  if (job && isTerminal(job.status)) {
    return (
      <Screen title="실행 결과">
        <JobResult job={job} canStartAnother={canStart} onStartAnother={startAnother} />
      </Screen>
    )
  }

  if (job && job.status !== 'DRAFT') {
    return (
      <Screen title="실행 상태">
        <Alert error={cancelJob.error} />
        {jobQuery.isError && <p className={styles.connectionNotice}>연결을 다시 확인하는 중</p>}
        <JobTracker
          job={job}
          isCancelling={cancelJob.isPending}
          onCancel={() => cancelJob.mutate(job.id)}
        />
      </Screen>
    )
  }

  if (job) {
    return (
      <Screen
        title="Agent가 실행안을 비교했어요"
        lead="아래 실행 계약은 Agent가 고정한 값입니다. GPU를 직접 바꾸지 않습니다."
      >
        <Alert error={startJob.error} />
        <ExecutionPlanReview job={job} />
        <div className={styles.panelGap}>
          <ApprovalPanel
            job={job}
            canStart={canStart}
            isStarting={startJob.isPending}
            onApprove={() => startJob.mutateAsync(job.id)}
            onEditConstraints={() => setJobId(null)}
          />
        </div>
      </Screen>
    )
  }

  return (
    <Screen
      title="예산과 우선순위만 정하면 됩니다"
      lead="Agent가 검증된 GPU 후보를 비교해 실행안을 추천합니다. GPU 콘솔, SSH, CUDA 설정은 다루지 않습니다."
    >
      {recoveryNotice && (
        <p className={styles.formAlert} role="alert">
          {recoveryNotice}
        </p>
      )}
      <Alert error={createJob.error} />
      <ConstraintForm
        isSessionReady={session.isSuccess}
        isSubmitting={createJob.isPending}
        onSubmit={createJob.mutate}
      />
    </Screen>
  )
}

/**
 * 흐름을 바꾸는 오류는 toast가 아니라 화면 상단에 고정해 읽을 시간을 준다.
 *
 * 다만 상단에 두기만 하면 페이지가 길 때 사용자가 못 본다. 승인 버튼은 아래에
 * 있고 오류는 위에 나타나므로, 누른 자리에서는 아무 일도 없는 것처럼 보인다.
 * 나타날 때 시야로 가져오고 focus를 옮겨 화면 낭독기에도 전달한다.
 */
function Alert({ error }: { error: unknown }) {
  const ref = useRef<HTMLParagraphElement>(null)

  useEffect(() => {
    if (!error) return
    ref.current?.scrollIntoView?.({ block: 'center' })
    ref.current?.focus()
  }, [error])

  if (!error) return null
  return (
    <p className={styles.formAlert} ref={ref} role="alert" tabIndex={-1}>
      {toUserMessage(error)}
    </p>
  )
}

function Screen({
  title,
  lead,
  children,
}: {
  title: string
  lead?: string
  children: ReactNode
}) {
  return (
    <div className={styles.app}>
      <header className={styles.header}>
        <span className={styles.wordmark}>UNWORK</span>
        <SessionStatus />
      </header>
      <main className={styles.main}>
        <h1 className={styles.pageTitle}>{title}</h1>
        {lead && <p className={styles.pageLead}>{lead}</p>}
        <div className={styles.content}>{children}</div>
      </main>
    </div>
  )
}
