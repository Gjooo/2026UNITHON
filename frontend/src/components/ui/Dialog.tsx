import { useEffect, useId, useRef, type ReactNode } from 'react'
import styles from './Dialog.module.css'

const FOCUSABLE =
  'a[href], button:not(:disabled), textarea:not(:disabled), input:not(:disabled), select:not(:disabled), [tabindex]:not([tabindex="-1"])'

interface DialogProps {
  title: string
  onClose: () => void
  children: ReactNode
  actions: ReactNode
}

/** focus trap, Escape 닫기, 최초 focus, 닫힌 뒤 trigger focus 복귀를 보장한다. */
export function Dialog({ title, onClose, children, actions }: DialogProps) {
  const dialogRef = useRef<HTMLDivElement>(null)
  const titleId = useId()

  useEffect(() => {
    const trigger = document.activeElement as HTMLElement | null
    const focusables = dialogRef.current?.querySelectorAll<HTMLElement>(FOCUSABLE)
    focusables?.[0]?.focus()

    // modal이 열린 동안 배경이 스크롤되면 안 된다.
    const previousOverflow = document.body.style.overflow
    document.body.style.overflow = 'hidden'

    return () => {
      document.body.style.overflow = previousOverflow
      trigger?.focus()
    }
  }, [])

  useEffect(() => {
    function onKeyDown(event: KeyboardEvent) {
      if (event.key === 'Escape') {
        event.stopPropagation()
        onClose()
        return
      }
      if (event.key !== 'Tab') return

      const items = Array.from(
        dialogRef.current?.querySelectorAll<HTMLElement>(FOCUSABLE) ?? [],
      )
      if (items.length === 0) return
      const first = items[0]
      const last = items[items.length - 1]
      const active = document.activeElement

      if (event.shiftKey && active === first) {
        event.preventDefault()
        last.focus()
      } else if (!event.shiftKey && active === last) {
        event.preventDefault()
        first.focus()
      }
    }

    document.addEventListener('keydown', onKeyDown, true)
    return () => document.removeEventListener('keydown', onKeyDown, true)
  }, [onClose])

  return (
    <div className={styles.backdrop}>
      <div
        className={styles.dialog}
        ref={dialogRef}
        role="dialog"
        aria-modal="true"
        aria-labelledby={titleId}
      >
        <h2 className={styles.title} id={titleId}>
          {title}
        </h2>
        {children}
        <div className={styles.actions}>{actions}</div>
      </div>
    </div>
  )
}
