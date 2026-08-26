import { Button } from '@/components/ui/Button'
import styles from './Landing.module.css'

const BURDENS = [
  {
    title: '실행 환경 판단',
    body: '필요한 VRAM과 GPU를 정하고, 공급자별 사양·가격·가용성을 직접 비교해야 합니다.',
  },
  {
    title: '환경 구축',
    body: 'Repository 배포, Python과 CUDA 버전, 의존성, 모델·데이터 접근을 맞춰야 합니다.',
  },
  {
    title: '비용 통제',
    body: '작업 전체가 얼마나 들지 가늠하고, 예상보다 오래 걸리거나 실패할 때 비용을 관리해야 합니다.',
  },
  {
    title: '감시와 정리',
    body: '정상 실행인지, 오류인지, 결과가 남았는지, 서버가 꺼졌는지를 계속 확인해야 합니다.',
  },
]

const STEPS = [
  {
    title: '제약을 정한다',
    body: '얼마까지 쓸지, 무엇을 우선할지만 정합니다. GPU 종류나 Region은 묻지 않습니다.',
  },
  {
    title: 'Agent가 비교한다',
    body: '검증된 GPU 후보의 예상 시간과 작업 완료 비용을 비교하고 선택 근거와 함께 제시합니다.',
  },
  {
    title: '실행 계약을 승인한다',
    body: '비용이 발생하기 전에 선택 GPU·예상 시간·예상 비용·중단 조건을 확인하고 승인합니다.',
  },
  {
    title: 'Agent가 끝까지 처리한다',
    body: '환경 생성, 학습 실행, 상태 감시, 결과 보관, 자원 종료 확인까지 하나의 작업으로 다룹니다.',
  },
]

const DIFFERENTIATORS = [
  {
    title: '시간당 단가가 아니라 작업 완료 비용',
    body: '시간당 단가가 아니라 예상 실행 시간까지 반영한 작업 완료 비용으로 실행안을 비교합니다. 단가가 싼 GPU가 오래 걸려 더 비싸질 수 있습니다.',
  },
  {
    title: '인프라 조작을 실행 계약으로',
    body: 'GPU 종류, Region, CUDA 버전, VM 옵션, SSH 접속을 입력하지 않습니다. 학습 목적과 제약을 계약으로 표현하면 나머지는 Agent가 합니다.',
  },
  {
    title: '실행의 전체 생애주기',
    body: 'Agent의 일은 서버를 만드는 데서 끝나지 않습니다. 성공·실패·중단 어느 경로에서도 결과를 보존하고 자원 종료를 확인합니다.',
  },
  {
    title: '판단은 사람에게 남긴다',
    body: '예산과 완료 기준, 실행안 승인, 추가 비용을 감수할지는 사용자가 정합니다. 자동화가 대체하는 것은 판단이 아니라 인프라 운영입니다.',
  },
]

const ROLES = [
  ['학습 목표와 완료 조건을 정한다', '실행 요구사항을 분석한다'],
  ['예산과 최대 실행시간을 정한다', 'GPU 후보를 비교하고 실행안을 만든다'],
  ['실행 계약을 승인한다', '환경을 만들고 학습을 실행한다'],
  ['예외 상황에서 계속할지 정한다', '상태와 비용을 감시하고 자원 종료를 확인한다'],
]

export function Landing({ onStart }: { onStart: () => void }) {
  return (
    <div className={styles.page}>
      <header className={styles.nav}>
        <span className={styles.wordmark}>Guupy</span>
        <span className={styles.navSpacer} />
        <Button variant="primary" onClick={onStart}>
          시작하기
        </Button>
      </header>

      <section className={styles.section}>
        <div className={styles.hero}>
          <div>
            <h1 className={styles.display}>GPU를 다루지 않고 학습을 끝냅니다</h1>
            <p className={styles.lead}>
              예산과 완료 기준만 정하면, Agent가 실행 환경을 비교해 고르고 학습을 실행한 뒤
              결과를 전달하고 자원까지 정리합니다. GPU 콘솔도, SSH도, CUDA 설정도 열지
              않습니다.
            </p>
            <div className={styles.heroActions}>
              <Button variant="primary" onClick={onStart}>
                시작하기
              </Button>
              <span className={styles.heroNote}>
                실행 전까지 비용이 발생하지 않습니다
              </span>
            </div>
          </div>
          <PlanMockup />
        </div>
      </section>

      <div className={styles.band}>
        <section className={styles.section}>
          <h2 className={styles.sectionTitle}>학습은 코드 문제인데, 일은 운영으로 옵니다</h2>
          <p className={styles.sectionLead}>
            Colab의 VRAM과 실행시간 한계를 넘으면 외부 GPU를 써야 합니다. 그 순간부터
            모델 개발과 다른 종류의 일이 따라붙습니다.
          </p>
          <div className={styles.grid4}>
            {BURDENS.map((item) => (
              <div className={styles.card} key={item.title}>
                <p className={styles.cardTitle}>{item.title}</p>
                <p className={styles.cardBody}>{item.body}</p>
              </div>
            ))}
          </div>
        </section>
      </div>

      <section className={styles.section} aria-label="역할">
        <h2 className={styles.sectionTitle}>사람은 판단하고, Agent는 실행합니다</h2>
        <p className={styles.sectionLead}>
          자동화가 가져가는 것은 판단이 아니라 인프라 운영입니다.
        </p>
        <table className={styles.roles}>
          <thead>
            <tr>
              <th scope="col">사람의 판단</th>
              <th scope="col">Agent의 실행</th>
            </tr>
          </thead>
          <tbody>
            {ROLES.map(([human, agent]) => (
              <tr key={human}>
                <th scope="row">{human}</th>
                <td>{agent}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </section>

      <div className={styles.band}>
        <section className={styles.section}>
          <h2 className={styles.sectionTitle}>어떻게 동작하나</h2>
          <div className={styles.grid4}>
            {STEPS.map((step, index) => (
              <div className={styles.card} key={step.title}>
                <p className={styles.stepIndex}>0{index + 1}</p>
                <p className={styles.cardTitle}>{step.title}</p>
                <p className={styles.cardBody}>{step.body}</p>
              </div>
            ))}
          </div>
        </section>
      </div>

      <section className={styles.section}>
        <h2 className={styles.sectionTitle}>다른 점</h2>
        <div className={styles.grid2}>
          {DIFFERENTIATORS.map((item) => (
            <div className={styles.card} key={item.title}>
              <p className={styles.cardTitle}>{item.title}</p>
              <p className={styles.cardBody}>{item.body}</p>
            </div>
          ))}
        </div>
      </section>

      <div className={styles.band}>
        <section className={styles.section} aria-label="요금">
          <h2 className={styles.sectionTitle}>선택할 수 있는 월정액 Plan</h2>
          <p className={styles.sectionLead}>
            혼자 한 번 돌려 보는지, 매주 반복하는지, 팀의 GPU 예산을 관리해야 하는지에
            따라 고르면 됩니다.
          </p>

          <div className={styles.plans}>
            <div className={styles.plan}>
              <div>
                <p className={styles.planName}>Free</p>
                <p className={styles.planFor}>개인 연구자</p>
              </div>
              <p className={styles.planBilling}>무료 · 제한된 Job</p>
              <p className={styles.planValue}>
                첫 외부 GPU 학습을 비용 부담 없이 끝까지 완주해 봅니다. 실행안 비교와
                승인, 자원 종료 확인까지 그대로 경험합니다.
              </p>
            </div>

            <div className={styles.plan}>
              <div>
                <p className={styles.planName}>Pro</p>
                <p className={styles.planFor}>반복 학습을 하는 개인</p>
              </div>
              <p className={styles.planBilling}>월 구독 · 초과 Job 사용량</p>
              <p className={styles.planValue}>
                실행 이력과 비용 기록이 쌓입니다. 같은 학습을 다시 돌리고, 지난 실행이
                얼마였는지 찾아볼 수 있습니다.
              </p>
            </div>

            <div className={`${styles.plan} ${styles.planFeatured}`}>
              <div>
                <p className={styles.planName}>Lab</p>
                <p className={styles.planFor}>3~15명 규모 대학 연구실</p>
              </div>
              <p className={styles.planBilling}>연구실 단위 월 구독 · 사용량</p>
              <p className={styles.planValue}>
                연구실 GPU 예산을 정하고, 금액 기준으로 실행을 승인하고, 누가 무엇을
                얼마에 돌렸는지 남깁니다. 전담 인프라 담당자 없이 팀의 비용을
                통제합니다.
              </p>
            </div>
          </div>

          <p className={styles.fine}>
            구체 요금은 연구실 Pilot과 지불의향 검증 후 확정합니다.
          </p>

          <div className={styles.splitNote}>
            <div className={styles.splitItem}>
              <span className={styles.splitLabel}>GPU 사용료</span>
              <span className={styles.splitTo}>연결한 본인 공급자 계정에 직접</span>
            </div>
            <div className={styles.splitItem}>
              <span className={styles.splitLabel}>Guupy 이용료</span>
              <span className={styles.splitTo}>선택한 Plan의 월정액</span>
            </div>
          </div>
        </section>
      </div>

      <section className={styles.section}>
        <h2 className={styles.sectionTitle}>학습부터 정리까지 맡겨 보세요</h2>
        <p className={styles.sectionLead}>
          실행안을 비교하는 데는 비용이 들지 않습니다. 승인하기 전까지 아무것도 만들어지지
          않습니다.
        </p>
        <div className={styles.heroActions}>
          <Button variant="primary" onClick={onStart}>
            시작하기
          </Button>
        </div>
      </section>

      <footer className={styles.footer}>Guupy — 학습 실행 Agent</footer>
    </div>
  )
}

/** 제품 화면이 이 브랜드의 논거다. 실제 실행안 비교 화면의 구조를 그대로 옮겼다. */
function PlanMockup() {
  return (
    <div className={styles.mockup} aria-hidden="true">
      <div className={styles.mockupBar}>
        <span className={styles.mockupDot} />
        <span className={styles.mockupDot} />
        <span className={styles.mockupDot} />
      </div>
      <div className={styles.mockupBody}>
        <div className={styles.mockupHead}>
          <span className={styles.mockupLabel}>Agent 추천 실행안</span>
          <span className={styles.mockupBadge}>추천</span>
        </div>
        <div>
          <p className={styles.mockupGpu}>NVIDIA L40S</p>
          <p className={styles.mockupProvider}>Runpod</p>
        </div>
        <dl className={styles.mockupFigures}>
          <div>
            <dt>예상 실행 시간</dt>
            <dd>약 7분</dd>
          </div>
          <div>
            <dt>예상 GPU 비용</dt>
            <dd>₩650</dd>
          </div>
        </dl>
        <table className={styles.mockupTable}>
          <thead>
            <tr>
              <th scope="col">GPU</th>
              <th scope="col" className={styles.numeric}>예상 시간</th>
              <th scope="col" className={styles.numeric}>예상 비용</th>
              <th scope="col">예산</th>
            </tr>
          </thead>
          <tbody>
            {[
              ['NVIDIA RTX 4090', '약 10분', '₩450'],
              ['NVIDIA L40S', '약 7분', '₩650'],
              ['NVIDIA A100 40GB', '약 5분', '₩900'],
            ].map(([gpu, time, cost]) => (
              <tr key={gpu}>
                <td>{gpu}</td>
                <td className={styles.numeric}>{time}</td>
                <td className={styles.numeric}>{cost}</td>
                <td className={styles.ok}>예산 내</td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </div>
  )
}
