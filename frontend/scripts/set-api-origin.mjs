/**
 * vercel.json의 백엔드 주소를 바꾼다.
 *
 * 브라우저는 항상 배포 도메인 하나만 보게 하고 Vercel이 서버 측에서 백엔드로
 * 넘긴다. 세션 쿠키가 `SameSite=Lax`라 origin이 갈리면 전송되지 않기 때문에,
 * 이 reverse proxy는 선택이 아니라 동작 조건이다.
 */
import fs from 'node:fs'
import path from 'node:path'
import { fileURLToPath } from 'node:url'

const target = process.argv[2]
if (!target) {
  console.error(
    [
      '',
      '  사용법: node scripts/set-api-origin.mjs <백엔드 공개 주소>',
      '    node scripts/set-api-origin.mjs https://unwork-api.example.com',
      '',
      '  https여야 합니다. 배포 도메인이 https이므로 백엔드 쿠키의 Secure 속성이',
      '  http 주소로는 전송되지 않습니다.',
      '',
    ].join('\n'),
  )
  process.exit(1)
}

let origin
try {
  origin = new URL(target)
} catch {
  console.error(`주소를 해석하지 못했습니다: ${target}`)
  process.exit(1)
}
if (origin.protocol !== 'https:') {
  console.error(`https가 아닙니다: ${target}\nSecure 쿠키가 전송되지 않아 세션이 매 요청 끊깁니다.`)
  process.exit(1)
}

const here = path.dirname(fileURLToPath(import.meta.url))
const file = path.join(here, '..', 'vercel.json')
const config = JSON.parse(fs.readFileSync(file, 'utf8'))
const rewrite = config.rewrites.find((r) => r.source === '/api/:path*')
rewrite.destination = `${origin.origin}/api/:path*`
fs.writeFileSync(file, JSON.stringify(config, null, 2) + '\n')

console.log(`vercel.json → ${rewrite.destination}`)
