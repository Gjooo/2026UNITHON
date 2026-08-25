import type { TrainingJob } from '@/api/jobs'
import styles from './JobTracker.module.css'

const TITLE: Partial<Record<TrainingJob['status'], string>> = {
  PROVISIONING: '실행 환경을 준비하고 있어요',
}

export function JobTracker({ job }: { job: TrainingJob }) {
  return (
    <section className={styles.tracker} aria-label="실행 상태">
      <h2 className={styles.title} aria-live="polite">
        {TITLE[job.status] ?? '실행 상태를 확인하고 있어요'}
      </h2>
      <p className={styles.gpu}>
        Agent가 선택한 GPU · {job.executionPlan.recommended.gpuType}
      </p>
    </section>
  )
}
