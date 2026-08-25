import { useSession } from '@/hooks/useSession'
import { ConstraintForm } from '@/features/training/ConstraintForm'
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

  return (
    <div className={styles.app}>
      <header className={styles.header}>
        <span className={styles.wordmark}>UNWORK</span>
        <SessionStatus />
      </header>

      <main className={styles.main}>
        <h1 className={styles.pageTitle}>예산과 우선순위만 정하면 됩니다</h1>
        <p className={styles.pageLead}>
          Agent가 검증된 GPU 후보를 비교해 실행안을 추천합니다. GPU 콘솔, SSH, CUDA 설정은
          다루지 않습니다.
        </p>
        <div className={styles.content}>
          <ConstraintForm isSessionReady={session.isSuccess} />
        </div>
      </main>
    </div>
  )
}
