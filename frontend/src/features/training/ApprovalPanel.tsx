import { useState } from 'react'
import { Dialog } from '@/components/ui/Dialog'
import type { TrainingJob } from '@/api/jobs'
import { formatKrw, formatMinutes } from './format'
import { EXECUTION_LIMIT_NOTICE } from './messages'
import { Button } from '@/components/ui/Button'
import styles from './ApprovalPanel.module.css'

interface ApprovalPanelProps {
  job: TrainingJob
  canStart: boolean
  isStarting: boolean
  /** 성공·실패 어느 쪽이든 settle될 때까지 기다린다. dialog를 닫을 시점을 알아야 한다. */
  onApprove: () => Promise<unknown>
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
        <Button
          variant="primary"
          disabled={!canStart || isStarting}
          onClick={() => setDialogOpen(true)}
        >
          실행 승인
        </Button>
        <Button onClick={onEditConstraints}>입력 수정</Button>
      </div>

      {isDialogOpen && (
        <Dialog
          title="실행 승인"
          onClose={() => setDialogOpen(false)}
          actions={
            <>
              <Button onClick={() => setDialogOpen(false)}>취소</Button>
              <Button
                variant="primary"
                disabled={isStarting}
                onClick={async () => {
                  try {
                    await onApprove()
                  } catch {
                    // 오류 문구는 화면 상단 alert가 보여 준다.
                  } finally {
                    // dialog는 fixed overlay라 열린 채로 두면 그 alert를 덮는다.
                    setDialogOpen(false)
                  }
                }}
              >
                승인하고 실행 시작
              </Button>
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
