import { useState, type FormEvent } from 'react'
import { Button } from '@/components/ui/Button'
import styles from './ProviderConnection.module.css'

interface ProviderConnectionProps {
  isConnecting: boolean
  onConnect: (apiKey: string) => Promise<unknown>
}

/**
 * 키는 이 컴포넌트의 로컬 state로만 존재하고, 전송 뒤 즉시 지운다.
 * 브라우저 저장소에 남기지 않고 서버도 되돌려 주지 않는다.
 */
export function ProviderConnection({ isConnecting, onConnect }: ProviderConnectionProps) {
  const [apiKey, setApiKey] = useState('')

  async function handleSubmit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault()
    if (!apiKey.trim()) return
    try {
      await onConnect(apiKey.trim())
    } finally {
      // 성공하면 더 들고 있을 이유가 없고, 실패하면 거절된 값을 그대로 두지 않는다.
      setApiKey('')
    }
  }

  return (
    <form className={styles.card} onSubmit={handleSubmit} noValidate>
      <h2 className={styles.title}>Runpod 계정 연결</h2>
      <p className={styles.body}>
        학습은 연결하신 본인 Runpod 계정에서 실행되고, 비용도 그 계정으로 직접 발생합니다.
        Agent가 GPU를 고르고 실행·정리까지 대신하지만, 자원과 청구는 계속 사용자의
        것입니다.
      </p>

      <div>
        <label className={styles.label} htmlFor="runpod-api-key">
          Runpod API 키
        </label>
        <input
          className={styles.input}
          id="runpod-api-key"
          type="password"
          autoComplete="off"
          spellCheck={false}
          value={apiKey}
          onChange={(event) => setApiKey(event.target.value)}
          aria-describedby="runpod-api-key-help"
        />
        <p className={styles.help} id="runpod-api-key-help">
          Runpod 콘솔의 Settings → API Keys에서 발급합니다. 읽기·실행 권한이 필요합니다.
        </p>
      </div>

      <ul className={styles.facts}>
        <li className={styles.fact}>
          <span className={styles.factMark} aria-hidden="true">
            ✓
          </span>
          입력한 키는 브라우저에 저장하지 않고 서버로만 보냅니다.
        </li>
        <li className={styles.fact}>
          <span className={styles.factMark} aria-hidden="true">
            ✓
          </span>
          서버는 이 세션에만 보관하고 디스크에 쓰지 않습니다. 언제든 연결을 끊을 수
          있습니다.
        </li>
        <li className={styles.fact}>
          <span className={styles.factMark} aria-hidden="true">
            ✓
          </span>
          연결 즉시 키가 실제로 통하는지 확인합니다. 자원을 만들지 않는 조회만 합니다.
        </li>
      </ul>

      <Button variant="primary" type="submit" disabled={isConnecting || !apiKey.trim()}>
        연결하기
      </Button>
    </form>
  )
}
