import { useState } from 'react'
import { Dialog } from '@/components/ui/Dialog'
import type { TrainingJob } from '@/api/jobs'
import { formatKrw, formatMinutes } from './format'
import styles from './ApprovalPanel.module.css'

export const EXECUTION_LIMIT_NOTICE =
  '이 브라우저에서는 실제 실행을 한 번만 할 수 있습니다.'

interface ApprovalPanelProps {
  job: TrainingJob
  canStart: boolean
  isStarting: boolean
  onApprove: () => void
  onEditConstraints: () => void
}

export function ApprovalPanel({
  job,
  canStart,
  isStarting,
  onApprove,
  onEditConstraints,
}: ApprovalPanelProps) {
  const [isDialogOpen, setDialogOpen] = useState(false)
  const plan = job.executionPlan.recommended

  return (
    <section className={styles.panel} aria-label="실행 승인">
      <p className={styles.notice}>
        승인하면 Agent가 선택한 실행 환경을 만들고 비용이 발생할 수 있습니다. GPU는 직접
        고르지 않습니다.
      </p>

      {!canStart && <p className={styles.limitNotice}>{EXECUTION_LIMIT_NOTICE}</p>}

      <div className={styles.actions}>
        <button
          className={styles.approve}
          type="button"
          disabled={!canStart || isStarting}
          onClick={() => setDialogOpen(true)}
        >
          실행 승인
        </button>
        <button className={styles.secondary} type="button" onClick={onEditConstraints}>
          입력 수정
        </button>
      </div>

      {isDialogOpen && (
        <Dialog
          title="실행 승인"
          onClose={() => setDialogOpen(false)}
          actions={
            <>
              <button
                className={styles.secondary}
                type="button"
                onClick={() => setDialogOpen(false)}
              >
                취소
              </button>
              <button
                className={styles.approve}
                type="button"
                disabled={isStarting}
                onClick={onApprove}
              >
                승인하고 실행 시작
              </button>
            </>
          }
        >
          <div>
            <p className={styles.dialogGpu}>{plan.gpuType}</p>
            <p className={styles.notice}>{plan.provider}</p>
          </div>
          <dl className={styles.dialogFigures}>
            <div>
              <dt>예상 실행 시간</dt>
              <dd>{formatMinutes(plan.estimatedRuntimeMinutes)}</dd>
            </div>
            <div>
              <dt>예상 GPU 비용</dt>
              <dd>{formatKrw(plan.estimatedGpuCostKrw)}</dd>
            </div>
          </dl>
          <ul className={styles.dialogWarnings}>
            <li>예산은 실제 청구액을 제한하지 않습니다. 비교를 위한 추정 기준입니다.</li>
            <li>{EXECUTION_LIMIT_NOTICE}</li>
          </ul>
        </Dialog>
      )}
    </section>
  )
}
