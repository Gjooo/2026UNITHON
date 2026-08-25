# UNWORK 디자인 시스템

> 활성 디자인 가이드. UI를 구현하기 전 이 문서와 원본 레퍼런스 [DESIGN_Spotify.md](DESIGN_Spotify.md), [DESIGN_Supabase.md](DESIGN_Supabase.md)를 함께 읽는다.

## 1. 방향

UNWORK는 AI 학습 실행 Agent를 위한 다크 운영 제품이다. 사용자는 GPU 콘솔을 다루는 대신 Agent의 추천 실행 계약을 검토하고, 실행 상태와 종료 확인을 신뢰해야 한다.

- **Spotify에서 가져올 것**: near-black 작업 공간, 명확한 상태 대비, 제한된 녹색 CTA, 몰입형 실행 추적 화면.
- **Supabase에서 가져올 것**: 기술 제품의 정보 구조, 정돈된 form·table·code block, 절제된 테두리와 명료한 데이터 표시.
- **UNWORK의 결정**: 기본 canvas는 어둡게 유지하고, 계약·후보 비교는 Supabase처럼 읽기 쉽게 구성한다. 장식적 이미지·그라디언트·다색 브랜드 요소는 사용하지 않는다.

## 2. 핵심 원칙

1. **계약이 주인공이다.** GPU·비용·시간·상태를 가장 읽기 쉽게 보여 주며, 장식이 정보를 앞서지 않는다.
2. **녹색은 행동과 정상 상태에만 쓴다.** primary CTA, 추천됨, 정상 실행/완료 외에는 채우기 색으로 사용하지 않는다.
3. **사용자는 선택하지 않고 승인한다.** GPU 수동 선택, Provider 설정, SSH/CUDA/Pod 제어 UI를 만들지 않는다.
4. **종료 확인 전에는 완료가 아니다.** `TERMINATING`은 항상 별도 진행 상태로 보인다.
5. **기술적이되 콘솔이 아니다.** 로그·exit code만 mono로 제공하고, raw Provider ID·API key·Pod ID는 노출하지 않는다.

## 3. 디자인 토큰

```css
:root {
  --canvas: #121212;
  --surface: #181818;
  --surface-raised: #1f1f1f;
  --surface-code: #1c1c1c;
  --surface-hover: #272727;

  --text: #ffffff;
  --text-secondary: #b3b3b3;
  --text-tertiary: #9a9a9a;
  --on-primary: #171717;

  --primary: #3ecf8e;
  --primary-pressed: #24b47e;
  --info: #539df5;
  --warning: #ffa42b;
  --danger: #f3727f;

  --border: #4d4d4d;
  --border-strong: #7c7c7c;
  --shadow-raised: 0 8px 8px rgba(0, 0, 0, .3);
  --shadow-dialog: 0 8px 24px rgba(0, 0, 0, .5);

  --radius-control: 6px;
  --radius-card: 12px;
  --radius-dialog: 16px;
  --radius-pill: 9999px;

  --space-1: 4px;
  --space-2: 8px;
  --space-3: 12px;
  --space-4: 16px;
  --space-5: 24px;
  --space-6: 32px;
  --space-7: 64px;

  --font-sans: Inter, Pretendard, "Noto Sans KR", system-ui, sans-serif;
  --font-mono: ui-monospace, SFMono-Regular, Menlo, Monaco, Consolas, monospace;
}
```

`#3ecf8e` 하나만 primary green으로 사용한다. Supabase의 on-primary 원칙에 따라 녹색 버튼 위 텍스트는 흰색이 아니라 `#171717`이다.

## 4. 타이포그래피

| 용도 | 크기 / 굵기 / 행간 | 규칙 |
| --- | --- | --- |
| Page display | 36px / 500 / 1.15 | `letter-spacing: -0.72px`; 768px 미만은 28px |
| Section title | 24px / 700 / 1.2 | 계약·결과의 주요 제목 |
| Card heading | 18px / 600 / 1.3 | 추천 카드·상태 섹션 |
| Body | 16px / 400 / 1.5 | 기본 설명과 폼 label |
| Caption | 13px / 400 / 1.45 | 추정값 안내·부가 정보 |
| Button | 14px / 600 / 1 | 일반 버튼은 sentence case, 승인 CTA는 필요 시 uppercase + 1.4px tracking |
| Code | 14px / 400 / 1.5 | completion log·exit code에만 mono |

숫자·금액·시간은 tabular numeral을 우선 사용해 비교 표의 열이 흔들리지 않게 한다. 작은 muted text를 핵심 비용·상태 정보에 사용하지 않는다.

## 5. 컴포넌트 규칙

### Buttons

- **Primary approval**: `--primary`, `--on-primary`, full pill, 최소 44px 높이. 한 viewport에서 하나만 둔다.
- **Secondary**: `--surface-raised`, white text, 6px radius. 제약 수정, 다시 비교에 사용한다.
- **Destructive**: 투명 또는 dark surface + `--danger` outline. 중단은 항상 확인 dialog를 거친다.
- **Disabled**: opacity만으로 의미를 전달하지 않고, 이유 텍스트 또는 helper를 함께 제공한다.

### Inputs and priority cards

- 숫자 입력은 6px radius, 1px `--border`, 44px 이상 높이, focus-visible outline을 가진다.
- 우선순위는 radio semantics를 가진 세 장의 compact card로 만든다. 선택됨은 primary border와 check icon, 텍스트로 모두 표시한다.
- GPU selector, provider selector, hidden advanced form은 제공하지 않는다.

### Cards, tables, and code

- 추천 실행안은 `--surface-raised` 카드와 subtle shadow를 사용한다. 추천 badge에만 green을 쓴다.
- 후보 비교는 desktop table, mobile stacked card다. 항목 순서는 GPU → 예상 시간 → 예상 GPU 비용 → 예산 적합 여부 → 추천 여부로 고정한다.
- `OVER_BUDGET`은 warning icon·텍스트와 함께 보여 주며, 흐리게 숨기지 않는다.
- log·명령·exit code는 `--surface-code` mono block에 넣되, code block을 장식으로 쓰지 않는다.

### Dialogs and notices

- 승인·중단 확인은 `--surface`와 `--shadow-dialog`을 사용하는 16px dialog다.
- dialog에는 선택 GPU, 예상 시간·비용, 비용·중단의 결과를 평문으로 다시 보여 준다.
- info/warning/error notice는 blue/orange/red과 아이콘·제목·다음 행동을 함께 제공한다.

## 6. 화면 구성

### 제약 입력

- 화면 상단에는 `UNWORK`, `MVP · SD 1.5 LoRA` 배지, 익명 세션 상태만 둔다.
- 사용자는 최대 예산과 `저비용`·`균형`·`빠른 완료`만 입력한다.
- 고정 시나리오(Stable Diffusion 1.5 LoRA, 24GB VRAM, 최대 10분)는 읽기 전용으로 설명한다.

### 실행 계약 검토

- desktop: 12-column grid, 좌측 4 columns 제약 요약, 우측 8 columns 추천·비교.
- 가장 위에는 선택 GPU, Provider, 예상 시간, 예상 GPU 비용, 추천 근거를 둔다.
- `DEMO_SNAPSHOT`과 실제 비용을 보장하지 않는다는 문구는 계약 안에서 항상 보인다.
- GPU를 변경할 수 있는 버튼은 만들지 않는다. CTA는 `실행 승인`, secondary는 `제약 수정`이다.

### 실행 추적과 결과

- `PROVISIONING → RUNNING → TERMINATING → final` 단계 진행 UI를 사용한다.
- `TERMINATING`에서는 “Pod 자동 종료를 확인하고 있어요”를 표시하며 최종 결과 색·문구를 앞당기지 않는다.
- 완료 결과에는 completion log, exit code, 실행 시간, 선택 GPU, Pod 종료 확인을 제공한다.
- 실패/중단 결과에는 안전한 원인과 종료 결과를 제공한다. 비용 또는 재시도 가능성을 추정해 말하지 않는다.

## 7. 상태 색상

| 의미 | 색상 | 보조 표현 |
| --- | --- | --- |
| 추천 / 실행 중 / 완료 | `--primary` | check 또는 active 상태 icon과 텍스트 |
| 세션 / 데모 스냅샷 안내 | `--info` | info icon과 설명 |
| 예산 초과 / 종료 확인 대기 | `--warning` | warning icon과 다음 상태 설명 |
| 실패 / 중단 확인 | `--danger` | error icon과 action |

색상만으로 적합성·실행 결과를 구분하지 않는다. 모든 상태 badge는 icon 또는 label을 함께 가져야 한다.

## 8. 반응형과 접근성

| Viewport | 구성 |
| --- | --- |
| ≥ 1024px | 최대 1180px container, 계약 검토 4:8 column |
| 768–1023px | 모든 주요 섹션 단일 열, 표는 우선순위 유지 |
| < 768px | 후보 card stack, 승인·중단 CTA sticky bottom bar |

- 모든 interactive control은 44×44px 이상의 hit target을 가진다.
- radio card, dialog, error message는 키보드로 완전히 사용 가능해야 한다.
- dialog는 focus trap·Escape·trigger focus 복귀를 제공한다.
- polling state update는 `aria-live="polite"`로 요약만 알리고 focus를 빼앗지 않는다.
- WCAG AA 대비를 유지하며, hover-only 정보나 가로 스크롤 표에 의존하지 않는다.

## 9. Do / Don't

### Do

- dark canvas와 layer 차이로 깊이를 만든다.
- 정보가 많은 계약·비교 화면은 Supabase처럼 테이블과 hairline을 절제해 정리한다.
- 단일 emerald를 의도적으로, 기능적인 위치에만 사용한다.
- 로그·상태·비용의 정확한 문구를 우선하고 화려한 시각 효과를 피한다.

### Don't

- white/light canvas, atmospheric gradient, album art, 장식용 일러스트를 추가하지 않는다.
- 여러 accent color, green background section, white text on primary green을 사용하지 않는다.
- 모든 버튼을 pill로 만들지 않는다. pill은 승인 CTA·status badge에 한정한다.
- Spotify/Supabase 로고·상표·proprietary font를 제품 자산으로 사용하지 않는다.
- 완료 확인 전 `COMPLETED`, `FAILED`, `CANCELLED` 화면을 표시하지 않는다.
