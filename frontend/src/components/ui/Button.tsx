import type { ButtonHTMLAttributes } from 'react'
import styles from './Button.module.css'

type Variant = 'primary' | 'secondary' | 'danger' | 'dangerOutline'

interface ButtonProps extends ButtonHTMLAttributes<HTMLButtonElement> {
  variant?: Variant
}

/** DESIGN.md의 6px 기술적 radius. pill은 상태 tag에만 쓰고 버튼에는 쓰지 않는다. */
export function Button({ variant = 'secondary', className, type = 'button', ...rest }: ButtonProps) {
  return (
    <button
      className={[styles.button, styles[variant], className].filter(Boolean).join(' ')}
      type={type}
      {...rest}
    />
  )
}
