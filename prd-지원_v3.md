# PRD v0 - Training Agent

- 문서 경로: `/docs/01-product/prd-v0.md`
- 버전: v0
- 상태: Problem-Solution Fit 검증용 MVP 초안
- 작성 기준: Task 1 Problem Framing, Task 2 User Flow / Domain, Task 3 Requirements / Business Rules, Task 4 MVP Boundary 통합

## 1. Product Summary

### 한 줄 정의

실행 가능한 AI 학습 코드와 예산을 입력하면, 시스템이 실행 환경을 결정하고 사용자의 승인을 받은 뒤 실제 GPU에서 학습을 실행해 결과를 보존하고 GPU 자원을 정리하는 Training Agent.

### 해결하려는 일

이 제품은 GPU를 더 쉽게 빌려주는 서비스가 아니다. AI 개발자가 모델을 학습하기 위해 별도로 수행하던 GPU 선택, 서버 구성, 환경 구축, 실행 감시, 비용 감시, 자원 종료 업무를 제거하는 것을 목표로 한다.

### 사용자에게 남기는 일

- 무엇을 학습할지 결정
- 실행할 코드와 명령 제공
- 최대 예산 결정
- 실행 계획 승인
- 코드 자체의 오류 수정
- 학습 결과 평가

### 시스템이 맡는 일

- Workload 분석
- Runtime Requirement 도출
- 실행 가능한 Compute Resource 결정
- 예상 실행시간과 비용 산정
- GPU 자원 생성
- 실행 환경 구성
- Training 실행과 상태 관리
- 비용 Guardrail 적용
- 결과 Artifact 보존
- 성공, 실패, 취소 시 GPU 자원 정리

---

## 2. Problem

### 2.1 Target User

#### Primary Target

Colab이나 로컬 환경으로는 원하는 AI 학습을 완료하기 어려워 외부 GPU가 필요해졌지만, 클라우드 GPU 인프라 운영에는 익숙하지 않은 AI 개발자.

MVP에서는 다음 조건을 만족하는 사용자로 더 좁힌다.

- 실행 가능한 PyTorch 또는 Hugging Face 학습 코드가 있다.
- Colab 또는 로컬 환경에서 VRAM, 실행시간, 세션 유지 등의 한계를 경험했다.
- 외부 GPU가 필요하지만 서버 운영 자체를 배우는 것이 목적은 아니다.
- GPU 종류, 서버 설정, CUDA 환경, 비용 관리에 충분한 경험이 없다.

#### Initial User Segment

첫 번째 외부 GPU 실행이 필요한 AI 전공 학부생, 대학원 연구자, 주니어 AI 개발자, 개인 프로젝트 개발자.

### 2.2 Situation

대표적인 문제 발생 상황은 다음과 같다.

```text
로컬 또는 Colab에서 모델 개발
↓
VRAM 부족, 세션 종료, 실행시간 제한
↓
더 큰 GPU가 필요함
↓
외부 GPU 사용 필요
↓
GPU와 서버 인프라를 직접 알아봐야 함
```

사용자의 실제 상태는 다음 문장으로 요약할 수 있다.

> 코드는 준비됐는데 어디서 어떻게 돌려야 할지 모르겠다.

### 2.3 Pain

#### Pain A. 의사결정 부담

사용자는 자신의 학습 작업에 어떤 GPU와 실행 환경이 필요한지 직접 판단해야 한다.

- 필요한 VRAM은 얼마인가
- 어떤 GPU가 적절한가
- 어느 Provider를 써야 하는가
- 더 비싼 GPU가 실제 총비용에서는 더 저렴한가

문제는 선택지가 없다는 것이 아니라, 선택 기준을 알기 어렵다는 것이다.

#### Pain B. 환경 구축 부담

GPU 자원을 확보한 뒤에도 학습을 시작하기 위해 별도의 환경 구성이 필요하다.

- Python 버전
- CUDA 호환성
- Dependency 설치
- 모델 및 데이터 접근
- 실행 명령 구성
- Repository 배포

#### Pain C. 비용 불확실성

사용자는 시간당 GPU 가격보다 이번 학습이 최종적으로 얼마가 들지 알고 싶어 한다.

실제 비용은 GPU 단가뿐 아니라 실행시간, 재시도, 실패, 자원 종료 시점에 영향을 받는다.

#### Pain D. 지속적인 관리 부담

학습을 시작한 뒤에도 사용자는 다음을 계속 신경 써야 한다.

- 정상 실행 여부
- 오류 발생 여부
- 현재 비용
- 학습 종료 여부
- 결과 저장 여부
- GPU가 계속 실행 중인지 여부

즉 설정 노동뿐 아니라 확인, 감시, 기억이라는 인지 노동이 지속된다.

### 2.4 Existing Alternatives

#### Colab 유지

- batch size 축소
- 더 작은 모델 사용
- 세션이 끊기면 재실행
- 유료 Colab 사용

장점은 익숙함이다. 단점은 원하는 실험을 환경에 맞춰 타협해야 할 수 있다는 점이다.

#### 로컬 GPU 확장

- 개인 GPU 구매
- 연구실 또는 회사 GPU 사용

장점은 통제 가능성이다. 단점은 초기 비용과 접근성이다.

#### GPU Cloud 직접 사용

- AWS
- RunPod
- Vast.ai
- 기타 GPU Provider

외부 GPU 접근성은 높지만, 사용자가 GPU 선택, 서버 생성, 환경 구성, 실행 감시, 종료를 직접 수행해야 할 수 있다.

#### 주변 인프라 경험자에게 요청

선배, 동료, 연구실 구성원, 인프라 담당자에게 도움을 요청한다. 문제 해결이 타인의 시간과 가용성에 의존한다.

---

## 3. Product Hypothesis

### Core Hypothesis

> 실행 가능한 AI 학습 코드를 가진 사용자가 코드, 실행 명령, 예산만 제공하고 GPU 인프라 운영을 직접 하지 않아도 학습 결과를 얻을 수 있다면, 외부 GPU 사용의 진입 장벽과 지속적인 운영 부담을 의미 있게 줄일 수 있다.

### Behavioral Hypothesis

사용자는 GPU 자체를 관리하고 싶은 것이 아니라 학습 결과를 얻고 싶어 한다. 따라서 지원 범위 안에서 시스템이 GPU 선택과 환경 구성을 대신해도 직접 통제보다 편의성과 예측 가능성을 더 높게 평가할 것이다.

### Business Hypothesis

반복적으로 GPU 학습을 수행하는 개인 또는 소규모 AI 팀은 GPU 자원 가격뿐 아니라 인프라 운영에 들어가는 시간과 실패 위험에도 경제적 가치를 부여할 가능성이 있다.

MVP에서는 지불 의사보다 먼저 핵심 업무 제거 가능성을 검증한다.

---

## 4. Goals

### G1. GPU 인프라 직접 조작 제거

지원되는 Training Job에 대해 사용자가 Provider 콘솔, SSH, CUDA 설치, 인스턴스 종료를 직접 수행하지 않고 결과까지 도달할 수 있어야 한다.

### G2. 비용 발생 전 사용자 통제권 확보

실제 GPU 비용이 발생하기 전에 예상 실행 계획과 예상 비용을 보여주고 사용자 승인을 받아야 한다.

### G3. End-to-End Training Job 완료

승인된 Job에 대해 GPU 생성, 환경 준비, Training 실행, Artifact 보존, 자원 정리까지 하나의 생애주기로 관리해야 한다.

### G4. 실패해도 자원이 방치되지 않는 안전성 확보

학습 성공뿐 아니라 실패와 사용자 취소 상황에서도 GPU 자원이 정리되어야 한다.

### G5. Job 단위 비용 가시성 확보

사용자는 GPU 시간당 가격이 아니라 자신의 Training Job 기준 예상 비용과 실제 비용을 확인할 수 있어야 한다.

---

## 5. Non-goals

MVP에서는 다음 문제를 해결하지 않는다.

- 모든 AI Repository 실행 지원
- 모든 GPU Provider 비교
- 세계 최저가 GPU 탐색 보장
- 완벽한 Training 시간 예측
- 완벽한 비용 예측
- 사용자 코드 자동 수정
- 학습 결과 품질 보장
- Hyperparameter 자동 최적화
- 분산학습
- Multi GPU
- Notebook IDE 제공
- MLOps 전체 기능 제공
- 모델 배포
- Team Workspace와 조직 권한 관리
- Spot 중단 자동 복구
- Provider 장애 시 자동 Migration

---

## 6. User Personas

### Persona A. First Cloud GPU Developer

#### Profile

- PyTorch 또는 Hugging Face 사용 가능
- 로컬 또는 Colab에서 모델 실험 경험 있음
- 외부 GPU 사용 경험은 없거나 매우 적음
- 서버 운영을 본업으로 생각하지 않음

#### Trigger

- Colab OOM
- 세션 종료
- 장시간 Training 실패
- 더 큰 모델 또는 파인튜닝 필요

#### Job to be Done

> 내 학습 코드를 서버 공부 없이 예산 안에서 실행하고 결과를 받고 싶다.

#### Current Friction

- GPU 선택 기준을 모름
- Provider 비교가 어려움
- CUDA와 Dependency 설정 부담
- 비용 폭탄 우려
- 학습 종료 후 서버 종료를 계속 신경 써야 함

#### Desired Outcome

학습 목적, 예산, 결과 평가에만 집중하고 인프라 운영은 별도 업무로 수행하지 않는 상태.

### Persona B. Small AI Team Developer

MVP의 직접 타깃은 아니지만 향후 유료 고객 후보로 본다.

- AI 개발자 3명 이상
- 별도 인프라 담당자 없음
- GPU 실험이 반복적으로 발생
- 팀 차원의 비용 통제 필요

MVP에서는 Team 기능을 구현하지 않는다.

---

## 7. Core User Journeys

### Journey 1. Happy Path

```text
Trigger
기존 환경에서 학습 불가능
↓
Entry
외부 GPU 필요
↓
Input
Repository URL
Execution Command
Budget
↓
Core Action
Training Job 생성
↓
System Processing
Workload 분석
Runtime Requirement 도출
Execution Plan 생성
↓
Result Preview
추천 GPU
예상 실행시간
예상 GPU 비용
예상 총비용
↓
Human Decision
실행 승인
↓
Execution
GPU Provisioning
환경 구성
Training 실행
비용과 상태 관리
↓
Finalization
Artifact 보존
최종 비용 확정
GPU 종료
↓
Completion
Training 결과
실제 비용
GPU 종료 확인
```

### Journey 2. Analysis Failure

```text
Job 생성
↓
Workload 분석
↓
필수 정보 판단 불가
↓
AnalysisFailed
↓
실패 원인 표시
↓
사용자 입력 수정
↓
재분석
```

### Journey 3. Execution Failure

```text
Job 실행
↓
Training 실패
↓
로그와 실패 원인 보존
↓
GPU 종료
↓
Failed 상태 표시
```

MVP에서는 자동 Retry를 필수로 구현하지 않는다.

### Journey 4. User Cancellation

```text
Running
↓
사용자 Cancel
↓
Training 중단 요청
↓
필요한 로그 보존
↓
GPU 종료
↓
Cancelled
```

---

## 8. Functional Requirements

### FR-1. Training Job 생성

사용자는 학습 작업을 정의해 Training Job을 생성할 수 있어야 한다.

#### Required Input

- Public GitHub Repository URL
- Execution Command
- Maximum Budget

#### Requirement

- Job 생성만으로 외부 GPU 비용이 발생하지 않아야 한다.
- 사용자가 GPU 종류, Region, CUDA Version, Provider를 필수 입력하지 않아야 한다.
- 제품 MVP는 지원 조건을 만족하는 Public GitHub Repository를 대상으로 한다.
- 실제 Demo 실행은 사전 검증된 Repository allowlist로 제한한다.
- 생성 직후 Job 상태는 `Draft`다.

#### Acceptance Criteria

Given 사용자가 접근 가능한 Public Repository, 유효한 실행 명령, 0보다 큰 예산을 입력했다.

When Job 생성을 요청한다.

Then Training Job이 생성되고 상태는 `Draft`이며 외부 GPU 비용은 발생하지 않는다.

### FR-2. Workload 분석

시스템은 Job을 분석해 실행에 필요한 Runtime Requirement를 생성해야 한다.

#### Minimum Analysis Scope

- Framework 식별
- Dependency 확인
- 실행 진입점 확인
- 예상 VRAM 범위
- 실행 가능 여부

#### Requirement

분석 결과의 주요 값은 가능한 경우 `Known`, `Estimated`, `Unknown`으로 구분한다.

필수 요구사항을 판단할 수 없으면 Execution Plan을 생성하지 않는다.

분석 실패 후 사용자가 입력을 수정하면 같은 Job에서 재분석한다. 이전 실패 원인은 보존하되 최신 분석 결과만 현재 Plan 생성에 사용한다.

#### Acceptance Criteria

Given 유효한 지원 대상 Repository와 실행 명령이 존재한다.

When Workload 분석을 수행한다.

Then Runtime Requirement를 생성하거나 실행 계획 생성이 불가능한 이유를 명확히 반환한다.

### FR-3. Execution Plan 생성

시스템은 Runtime Requirement와 Budget을 기준으로 실행 계획을 생성해야 한다.

#### Plan Output

- 선택된 GPU
- Provider
- 예상 실행시간
- 예상 GPU 비용
- 예상 서비스 비용
- 예상 총비용

#### Requirement

- Runtime Requirement를 충족해야 한다.
- 예상 총비용은 Maximum Budget 이하여야 한다.
- 시간당 가격만이 아니라 해당 Job을 완료하는 예상 총비용을 기준으로 평가해야 한다.
- 실행 필수 값이 `Unknown`이면 승인 가능한 Plan을 생성하지 않는다.

#### Acceptance Criteria

Given Runtime Requirement와 Budget이 존재한다.

When 실행 후보를 평가한다.

Then 조건을 만족하는 Execution Plan을 생성하거나 `NoFeasiblePlan`을 반환한다.

### FR-4. 실행 승인

사용자는 실제 비용이 발생하기 전에 Execution Plan을 승인해야 한다.

#### Requirement

승인 화면에는 최소 다음 정보가 표시되어야 한다.

- 선택 GPU
- 예상 실행시간
- 예상 GPU 비용
- 서비스 비용
- 예상 총비용
- Maximum Budget

승인 전에는 외부 Compute Resource를 생성하지 않는다.

동일 Plan에 대한 중복 승인 요청은 하나의 Active Execution Attempt만 생성해야 한다.

승인 직전에 Provider 가격과 Availability를 재검증한다. 재검증 결과 기존 Plan을 실행할 수 없으면 Plan을 폐기하고 새 Plan을 생성한다.

승인 이후 Repository URL, Execution Command, Maximum Budget은 변경할 수 없다.

#### Acceptance Criteria

Given Ready 상태의 승인되지 않은 Job이 있다.

When Owner가 Plan을 승인한다.

Then 정확히 하나의 Execution Attempt가 생성되고 GPU Provisioning이 시작된다.

### FR-5. GPU Provisioning 및 환경 구성

시스템은 승인된 Plan에 따라 GPU 자원을 생성하고 Training 실행 환경을 준비해야 한다.

#### MVP Scope

- 단일 Provider
- 단일 GPU
- Public Repository Clone
- Demo에서는 사전 검증된 Repository allowlist
- requirements.txt 기반 Dependency 설치
- Python Training Script 실행
- 최소 권한·비-root·Job별 격리가 보장되는 Remote Runtime

#### Acceptance Criteria

Given 승인된 Execution Plan이 있다.

When Provisioning이 시작된다.

Then 사용자가 Provider 콘솔이나 SSH를 직접 조작하지 않아도 Repository와 Dependency가 준비된 실행 환경이 생성된다.

### FR-6. Training 실행과 비용 Guardrail

시스템은 Training 실행 상태와 비용을 관리해야 한다.

#### Minimum Tracked Data

- Execution Status
- Elapsed Time
- Current Cost 또는 비용 추정치
- Major Error

#### Requirement

- 사용자가 브라우저를 닫아도 Job은 계속 관리되어야 한다.
- Job Budget은 전체 Job 기준 누적 비용 한도로 취급한다.
- Budget 90% 도달 시 사용자에게 경고하고 비용 관찰을 강화한다.
- Budget 초과가 예상되면 Training 중단과 Resource 종료 절차를 시작한다.
- Provider 기술 오차 분류 기준은 `1,000원 또는 Maximum Budget의 10% 중 큰 값`이다.
- Technical Variance와 시스템 통제 실패에 따른 Budget Violation을 분리해 기록한다.

#### Acceptance Criteria

Given 승인된 Job이 Running 상태다.

When 사용자가 애플리케이션을 종료하거나 브라우저를 닫는다.

Then 시스템은 Training 실행 상태와 비용 통제를 계속 수행한다.

### FR-7. Artifact 보존과 GPU 종료

Training 실행이 끝나면 결과를 보존하고 GPU 자원을 정리해야 한다.

#### Minimum Artifact

- Training Output
- Training Log

지원 Workload에 따라 Model 또는 Checkpoint를 결과로 포함할 수 있다.

#### Completion Requirement

Job은 다음 조건이 모두 충족된 뒤 `Completed`가 된다.

1. Training Process 종료
2. 필수 Artifact 보존 확인
3. 최종 비용 기록
4. GPU 종료 확인

Job 상태는 Training Process 종료 후 `Finalizing`이 되며, 위 조건을 모두 충족한 뒤에만 `Completed`가 된다.

내부 Resource 상태는 Job 상태와 별도로 관리한다.

```text
NotCreated
→ Provisioning
→ TerminationRequested
→ TerminationConfirming
→ TerminationConfirmed
```

Provider API Timeout 후 Resource 존재 여부를 확인할 수 없으면 내부 `ProviderReconciliationRequired` 상태로 전환하고 새 Resource를 생성하지 않는다.

#### Acceptance Criteria

Given Training Process가 정상 종료됐다.

When Finalization을 수행한다.

Then 필수 Artifact가 보존되고 GPU 종료가 확인된 이후에만 Job을 `Completed`로 표시한다.

### FR-8. Cancel

Owner는 Running Job을 취소할 수 있어야 한다.

#### Requirement

Cancel 요청 시 Job은 `CancelRequested`가 되고 Training 중단과 GPU 종료가 이어져야 한다.

Cancel 요청 후에도 GPU 종료가 확인되지 않으면 시스템은 종료 요청을 재시도해야 한다.

`TerminationConfirming`과 `ProviderReconciliationRequired`는 내부 운영 상태이며, 사용자에게는 각각 “자원 정리 확인 중”, “실행 상태 확인 중”으로 표시한다.

#### Acceptance Criteria

Given Running 상태의 Job이 있다.

When Owner가 Cancel을 요청한다.

Then 시스템은 Training 중단과 GPU 종료를 요청하고, 종료 확인 후 Job을 `Cancelled`로 표시한다.

### FR-9. 실패 분류와 재실행

시스템은 실패 원인과 재실행 경로를 구분해야 한다.

#### Requirement

- 입력 오류는 기존 Job을 변경하지 않고 새 Job 생성으로 해결한다.
- 시스템·Provider 오류는 기존 Job의 새 Execution Attempt로 재실행할 수 있다.
- Training 자동 Retry는 제공하지 않는다.
- Resource Cleanup은 멱등적으로 수행하고 종료 확인까지 Background Retry한다.
- Provider API Timeout 시 Runtime ID와 Provider 조회 API로 Reconciliation한 뒤에만 다음 동작을 결정한다.
- 부분 Log와 Artifact는 보존하고 Artifact별 상태를 기록한다.

### FR-10. 실행 안전성과 Credential 경계

사용자 Workload는 Application Host가 아닌 격리된 Remote Runtime에서 실행해야 한다.

#### Requirement

- Runtime은 최소 권한·비-root·Job별 격리 조건을 만족해야 한다.
- Host 파일시스템과 다른 Job 데이터에 접근할 수 없어야 한다.
- Provider Credential은 서버 운영 Secret으로만 관리하며 Training Process와 Log에 노출하지 않는다.
- 위 격리를 보장하지 못하는 Provider는 MVP에서 사용할 수 없다.

---

## 9. Business Rules

### BR-1. Primary Entity는 Training Job이다

GPU나 인스턴스가 사용자가 관리하는 핵심 객체가 아니다. 사용자는 Training Job을 생성하고 결과를 받는다.

### BR-2. 비용 발생 전 명시적 승인

분석과 Plan 생성 단계에서는 GPU 비용이 발생하지 않는다. 실제 GPU 자원 생성은 Owner의 승인 이후에만 가능하다.

### BR-3. Budget은 Job 단위 누적 한도다

하나의 Job에서 여러 Execution Attempt가 발생하는 경우 각 Attempt의 비용은 Job Budget에 누적된다.

예:

```text
Job Budget: 10,000원
Attempt 1 사용액: 3,000원
남은 Budget: 7,000원
```

입력 오류로 새 Job을 생성하는 경우에는 새 Job의 Budget을 사용한다. 시스템·Provider 오류로 기존 Job에 새 Attempt를 만드는 경우에는 기존 Job Budget에 누적한다.

### BR-4. Estimated Cost와 Actual Cost는 분리한다

Execution Plan의 비용은 예상값이며 실제 과금 결과와 동일하다고 보장하지 않는다.

### BR-5. Job과 Execution Attempt는 다른 개념이다

하나의 Training Job은 하나 이상의 Execution Attempt를 가질 수 있다.

### BR-6. Process 종료와 Job 완료는 다르다

Training Process가 종료되면 Job은 `Finalizing`이 된다. Artifact 보존, 최종 비용 기록, GPU 종료 확인이 끝나지 않았다면 Job은 `Completed`가 아니다.

### BR-7. 모르는 값을 아는 것처럼 처리하지 않는다

필수 정보가 불확실한 경우 시스템은 임의 실행보다 재분석, 보수적 Plan 또는 사용자 확인을 우선한다.

### BR-8. 사용자가 인프라를 직접 입력하지 않는 것이 기본 경로다

GPU, Region, CUDA Version, Instance Type 등은 기본 Job 생성 필수값이 아니다.

### BR-9. 하나의 승인된 Plan에는 하나의 Active Attempt만 존재한다

중복 클릭, 재전송, 네트워크 Retry로 GPU 자원이 중복 생성되어서는 안 된다.

### BR-10. 모든 종료 경로에서 자원 정리를 수행한다

- Success
- Failure
- User Cancel
- Budget Guardrail Trigger

어떤 경로에서도 GPU 자원을 의도적으로 방치하지 않는다.

### BR-11. Budget Guardrail과 Violation은 분리한다

Budget 90% 도달은 경고와 관찰 강화만 수행한다. 실제 비용이 Maximum Budget을 초과할 것으로 예상되면 Training 중단과 Resource 종료를 요청한다.

Provider 지연 또는 최소 과금 단위로 인한 초과는 `Technical Variance`로 분류하고, 허용 기준을 넘는 시스템 통제 실패는 `Budget Violation`으로 분류한다. 허용 기준은 `max(1,000원, Maximum Budget의 10%)`이다.

### BR-12. 입력 오류와 시스템 오류의 재실행을 구분한다

승인 이후 입력은 불변이다. 잘못된 Repository, Command, Dependency 등 사용자 입력 오류는 새 Job으로 해결한다. Provider 장애나 일시적 시스템 오류는 기존 Job의 새 Attempt로 재실행할 수 있다.

### BR-13. 사용자 상태와 내부 Resource 상태를 분리한다

`TerminationConfirming`, `ProviderReconciliationRequired`는 내부 운영 상태다. 사용자에게는 Provider Runtime ID나 Credential을 노출하지 않고 추상화된 처리 상태를 표시한다.

### BR-14. Resource 종료 확인 기한을 구분한다

종료 요청 후 5분 동안 Provider 상태 재조회와 종료 요청 Retry를 수행한다. 종료 확인이 30분을 초과하면 `Leak Suspected`로 기록한다. 실제 Resource 잔존 또는 과금이 확인된 경우에만 확정 Leak로 집계한다.

### BR-15. 데이터 보존과 삭제

Job, Log, Artifact는 30일 보존한다. MVP에서는 사용자 삭제 API와 장기 보존 정책을 제공하지 않으며, 물리 삭제 방식은 별도 저장소 설계에서 결정한다.

---

## 10. Edge Cases

### EC-1. Repository는 유효하지만 Training Workload가 아님

처리:

- Execution Plan 생성 금지
- `AnalysisFailed`
- 이유 표시

### EC-2. 실행 진입점이 여러 개임

처리:

- 시스템 임의 선택 금지
- 사용자에게 실행 명령 확인 요청

### EC-3. VRAM 요구량을 신뢰성 있게 추정할 수 없음

처리:

- Confidence를 낮게 표시
- 실행 후보를 보수적으로 제한하거나 추가 입력 요청

### EC-4. Plan 생성 후 GPU 가격 또는 Availability 변경

처리:

- 승인 직전 가격과 Availability 재검증
- Budget을 초과하거나 자원이 없으면 기존 Plan 실행 금지
- 새 Plan 생성

### EC-5. 사용자가 승인 버튼을 중복 클릭

처리:

- Idempotency 보장
- 하나의 Active Attempt만 생성

### EC-6. Provisioning 중 Provider 장애

처리:

- Training 코드 실패와 구분
- 가능한 범위에서 GPU 자원 생성 여부 확인
- 생성된 자원이 있다면 정리
- Provider API Timeout으로 확인할 수 없으면 Reconciliation을 먼저 수행하고 재생성하지 않음

### EC-7. Dependency 설치 실패

처리:

- 사용자 입력 오류로 분류되면 기존 Job을 변경하지 않고 새 Job 생성 안내
- 시스템·Provider 오류로 분류되면 기존 Job의 새 Attempt 허용
- 환경 구성 로그 보존
- GPU 종료

### EC-8. Training 중 OOM 또는 Python Error

처리:

- 실패 로그 보존
- GPU 종료
- 사용자에게 실패 원인 표시

### EC-9. Training 성공 후 Artifact 저장 실패

처리:

- `Completed` 처리 금지
- Finalization 실패로 기록
- GPU는 불필요한 비용 방지를 위해 정리

부분적으로 저장된 Log와 Artifact는 보존하고 각 Artifact의 상태를 기록한다.

### EC-10. GPU 종료 요청 성공 여부를 확인할 수 없음

처리:

- `TerminationRequested`, `TerminationConfirming`, `TerminationConfirmed`를 내부 상태로 구분
- 5분 동안 재조회와 종료 요청 Retry
- 30분 초과 시 `Leak Suspected`
- 확인 전에는 정상 완료로 표시하지 않음
- Provider 조회 자체가 불가능하면 `ProviderReconciliationRequired`

### EC-11. 사용자가 브라우저를 닫음

처리:

- 서버 측 Job Execution은 계속
- 클라이언트 세션이 실행 생애주기를 소유하지 않음

### EC-12. Budget 근접 상태에서 Provider 비용 데이터가 지연됨

처리:

- Budget 90% 도달 시 경고 및 관찰 강화
- Budget 초과 예상 시 종료 절차 시작
- `max(1,000원, Maximum Budget의 10%)` 이내는 Technical Variance로 분류
- 그 이상은 Budget Violation으로 기록

### EC-13. 운영자 수동 복구

처리:

- Provider API 장애 시 운영자가 Provider Console에서 Resource를 확인하거나 종료할 수 있음
- 정상 Happy Path에는 운영자 개입이 없어야 함
- 수동 복구 횟수와 원인은 Manual Recovery Count로 별도 기록

### EC-14. 실행 격리 기준 미충족

처리:

- Provider가 비-root 실행, Job별 격리, Host 및 다른 Job 데이터 접근 차단을 보장하지 못하면 실행하지 않음
- 운영자 승인으로 보안 기준을 우회하지 않음

---

## 11. MVP Scope

MVP 판단 질문은 하나로 고정한다.

> 이 기능이 없어도 사용자가 GPU 인프라를 직접 조작하지 않고 하나의 지원 Training Job을 끝낼 수 있는가?

YES라면 MVP 밖으로 이동한다.

### 11.1 MUST

핵심 가설 검증에 반드시 필요한 범위.

- Training Job 생성
- Public GitHub Repository 입력
- Demo allowlist 기반 지원 Workload 검증
- Execution Command 입력
- Maximum Budget 입력
- 최소 Workload 분석
- Runtime Requirement 생성
- Execution Plan 생성
- 선택 GPU 표시
- 예상 실행시간 표시
- 예상 GPU 비용과 총비용 표시
- 사용자 실행 승인
- 단일 Provider 실제 연동
- 단일 GPU Provisioning
- Repository 자동 Clone
- requirements.txt 기반 Dependency 설치
- Python Training Script 실행
- 실행 상태 관리
- Budget Guardrail
- 사용자 Cancel
- Training 성공 시 Artifact 보존
- 성공 시 GPU 자동 종료
- 실패 시 GPU 자동 종료
- 취소 시 GPU 자동 종료
- AnalysisFailed 후 같은 Job 재분석
- 입력 오류와 시스템·Provider 오류의 재실행 경로 구분
- Provider Reconciliation 및 Resource 종료 Retry
- 최소 실행 격리와 서버 측 Credential 경계
- 30일 Job·Log·Artifact 보존
- 실제 실행시간 표시
- 실제 비용 표시
- GPU 종료 확인 표시

### 11.2 SHOULD

있으면 제품 경험이 좋아지지만 핵심 가설 검증에는 불필요한 범위.

- Private GitHub Repository
- 여러 GPU 후보 비교 UI
- 상세 Progress UI
- 실시간 Log Viewer
- 더 정교한 GPU 성능 예측
- 더 정교한 Training 시간 예측
- 더 정교한 Job Cost 예측
- Checkpoint 저장
- Attempt History UI
- Execution Attempt History UI
- 완료 알림
- Dependency 오류 진단 강화

### 11.3 LATER

PMF 이후 검토할 범위.

- Multi Cloud
- AWS, RunPod, Vast.ai 등 여러 Provider 실시간 비교
- Spot GPU
- Provider 자동 Migration
- Checkpoint Resume
- Spot 중단 자동 복구
- Notebook 실행
- Notebook IDE
- Web Terminal
- SSH 지원
- Team Workspace
- Team Role과 Permission
- 조직 Budget
- Project Budget
- Billing과 Subscription
- Model Registry
- Experiment Tracking
- Dataset Versioning
- Hyperparameter Tuning
- Distributed Training
- Multi GPU
- 사용자 코드 자동 수정
- OOM 자동 해결
- Training 실패 자동 복구
- 모델 배포

---

## 12. Success Metrics

### 12.1 Primary Validation Metric

#### Infrastructure Direct Manipulation Count

지원되는 Happy Path에서 사용자가 직접 수행해야 하는 다음 인프라 조작 횟수.

- Provider 콘솔 접속
- GPU 직접 선택
- 인스턴스 직접 생성
- SSH 접속
- CUDA 직접 구성
- 서버 상태 직접 감시
- GPU 직접 종료

**MVP 목표: 0회**

### 12.2 End-to-End Completion Rate

지원 범위에 해당하고 사용자가 승인한 Training Job 중 다음 조건을 모두 만족한 비율.

- 실제 GPU 실행
- Training 종료
- Artifact 확보
- GPU 종료 확인

운영자 수동 복구가 발생한 Job은 기술적 완료 여부와 별도로 자동화 Happy Path 성공에서 제외한다.

초기 기술 검증 목표는 별도 테스트셋으로 측정한다.

### 12.3 Resource Leak Rate

성공, 실패, 취소 후 Resource 종료 확인 기한을 넘겨 실제 Resource 잔존 또는 과금이 확인된 비율.

30분 초과 미확인은 `Leak Suspected`로 별도 기록하며 확정 Leak와 구분한다.

**MVP 목표: 0건**

### 12.4 Budget Guardrail Violation

Maximum Budget을 초과한 Job 중 Technical Variance 허용 범위를 넘은 Job 수.

목표는 0건이다. Technical Variance는 별도 분류한다. 허용 기준은 `max(1,000원, Maximum Budget의 10%)`이다.

### 12.5 User Intervention Count

Job 생성과 승인 이후 Completion 또는 Failure까지 필요한 사용자 개입 횟수.

포함:

- Job Input 1회
- Execution Approval 1회
- User Cancel
- 사용자 오류 수정

제외:

- 상태 조회
- 브라우저 재접속
- 운영자 수동 복구

Happy Path 목표:

- Job Input 1회
- Execution Approval 1회
- 추가 인프라 개입 0회

### 12.6 Manual Recovery Count

Provider Console에서 운영자가 Resource를 직접 확인·종료해야 한 횟수다.

정상 Happy Path 목표는 0회이며, Completion Rate와 별도로 집계한다.

### 12.7 Qualitative Validation

초기 사용자 테스트에서 다음을 확인한다.

- 기존 방식보다 다시 사용할 의향이 있는가
- GPU 선택을 시스템에 맡기는 것이 불안하지 않은가
- 가장 큰 제거 가치는 환경 구축, 비용 통제, 종료 관리 중 무엇인가
- 직접 GPU Cloud를 사용하는 것보다 추가 비용을 지불할 의향이 있는가

---

## 13. Constraints

### Product Constraints

MVP는 지원 범위를 의도적으로 좁힌다.

- 단일 사용자
- 단일 Provider
- 단일 GPU
- 제품 MVP는 지원 조건을 만족하는 Public GitHub Repository
- 실제 Demo는 사전 검증된 Repository allowlist
- Python Training Script
- PyTorch 또는 Hugging Face 중심
- requirements.txt 기반 Dependency
- 지원 가능한 제한된 Workload

### Technical Constraints

- 모든 Repository 구조를 자동 해석할 수 없을 수 있음
- VRAM 요구량과 실행시간은 정확한 확정값이 아니라 추정값일 수 있음
- Provider API의 Availability와 가격은 변동 가능
- Provider 과금 데이터에는 지연이 존재할 수 있음
- 일부 Model 또는 Dataset은 별도 인증이 필요할 수 있음

### Security Constraints

MVP에서 Secret 처리 범위를 최소화한다.

- Provider Credential은 서버 운영 Secret으로만 관리하고 Client에 전달하지 않는다.
- Credential은 Training Process와 Log에 노출하지 않는다.
- 사용자 Workload는 Application Host가 아닌 격리된 Remote Runtime에서 실행한다.
- Runtime은 최소 권한·비-root·Job별 격리·Host 및 다른 Job 데이터 접근 차단을 만족해야 한다.
- 위 격리를 보장하지 못하는 Provider는 MVP에서 제외한다.
- 로그 수집기는 실제 주입된 Secret 값과 설정된 Secret 패턴을 마스킹한다.
- Secret 탐지는 완전하지 않으며 Private Dataset·사용자 Credential 입력은 MVP에서 지원하지 않는다.

### Data Retention Constraints

- Job, Log, Artifact는 30일 보존한다.
- MVP에서는 사용자 삭제 API를 제공하지 않는다.
- Soft Delete, Hard Delete, Cascade, 물리 삭제 실행 주체는 저장소 설계에서 별도 결정한다.

### Hackathon Constraints

- 정교한 최적화보다 End-to-End 실제 실행을 우선한다.
- GPU 선택 알고리즘은 휴리스틱으로 시작할 수 있다.
- 비용 및 시간 예측은 단순 모델로 시작할 수 있다.
- 실제 GPU 생성, 실제 Training 실행, 실제 Artifact 생성, 실제 GPU 종료는 가능하면 Mock하지 않는다.

---

## 14. Risks

### RISK-1. 기존 GPU Cloud가 이미 충분히 쉬움

RunPod 등 기존 서비스가 초기 사용자의 문제를 충분히 해결하고 있다면 Pain의 강도가 약할 수 있다.

검증 필요:

- 현재 실제 사용자의 GPU Cloud 이용 단계
- 서버 설정에 소요되는 실제 시간
- 반복 사용 후 Pain이 얼마나 감소하는지

### RISK-2. 사용자가 GPU 선택권을 포기하지 않음

숙련 사용자는 시스템 자동 선택보다 직접 GPU를 고르고 싶어 할 수 있다.

MVP는 초보 사용자에 집중하고, Advanced Mode는 후순위로 둔다.

### RISK-3. Workload 분석 정확도 부족

Repository만으로 VRAM, Runtime, Dataset 규모를 충분히 판단하기 어려울 수 있다.

과도한 자동 판단보다 지원 범위 제한과 불확실성 표시가 필요하다.

### RISK-4. 비용 예측 오류

실행시간과 Provider 가격 변동으로 실제 비용이 예상값과 다를 수 있다.

예상값과 실제값을 분리하고 Budget Guardrail을 별도로 적용한다.

### RISK-5. 환경 호환성 폭발

CUDA, Python, Dependency, Custom Extension 조합을 모두 지원하려 하면 MVP 범위가 빠르게 확장된다.

지원 환경을 명시적으로 제한한다.

### RISK-6. Resource Leak

GPU 종료 실패는 사용자의 비용 신뢰를 직접 훼손한다.

자원 종료를 Completion 조건에 포함하고 Background Retry를 둔다.

### RISK-7. 낮은 반복 사용성

첫 번째 GPU 사용 때만 Pain이 크고 이후 사용자가 익숙해지면 지속 사용 가치가 약해질 수 있다.

반복 실험 사용자와 소규모 AI 팀에서 문제 빈도를 별도로 검증해야 한다.

### RISK-8. 사용자와 구매자가 다름

개인 개발자는 Pain이 강해도 지불 여력이 낮을 수 있다.

초기 사용자는 개인 개발자, 장기 유료 고객은 소규모 AI 팀이 될 가능성을 검증한다.

---

## 15. Assumptions

### User Assumptions

- A1. Colab 밖의 GPU가 필요한 AI 개발자 중 의미 있는 비율이 인프라 운영을 불편하게 느낀다.
- A2. 사용자는 GPU 선택 자체보다 학습 결과를 얻는 것을 더 중요하게 생각한다.
- A3. 외부 GPU를 처음 사용하거나 자주 바꾸는 사용자에게 환경 구축 부담이 반복된다.
- A4. 비용 폭탄에 대한 불안은 외부 GPU 사용의 장벽이다.

### Behavior Assumptions

- A5. 사용자는 GPU Provider와 GPU 종류를 직접 비교하는 데 시간을 사용한다.
- A6. 외부 GPU 실행 중 상태와 비용을 반복 확인한다.
- A7. Training 종료 후 자원 종료 여부를 별도로 신경 쓴다.
- A8. 이러한 업무가 충분히 고통스럽다면 기존 방식에서 새로운 실행 흐름으로 전환할 의향이 있다.

### Product Assumptions

- A9. 제한된 지원 범위에서는 Repository와 실행 명령을 기반으로 Runtime Requirement를 충분히 도출할 수 있다.
- A10. 단일 Provider만으로도 GPU 인프라 직접 조작 제거라는 핵심 가설을 검증할 수 있다.
- A11. 사용자는 예상 비용이 완벽하지 않아도 비용 상한과 실제 비용 가시성이 있으면 충분한 통제감을 느낄 수 있다.

### Business Assumptions

- A12. 반복적인 GPU Training을 수행하는 사용자는 GPU 가격 외에 운영 시간 절감에도 경제적 가치를 부여한다.
- A13. 개인 개발자를 진입점으로 확보하고 소규모 AI 팀을 장기 유료 고객으로 전환할 수 있는 가능성이 있다.

---

## 16. Open Questions

1차 PRD Grill에서 확정된 항목은 Decision Log에 기록하고 아래 목록에서 Resolved 처리한다. 이 절에는 아직 구현 또는 검증이 필요한 질문만 남긴다.

### Problem Validation

1. 사용자가 실제로 가장 힘들어하는 것은 환경 구축, 비용 통제, 종료 관리 중 무엇인가?
2. 이 Pain은 첫 번째 외부 GPU 사용 때만 큰가, 반복 실험에서도 지속되는가?
3. 기존 GPU Cloud 서비스로 문제를 충분히 해결하고 있지 않은가?

### Product

4. Golden Path allowlist에 포함할 첫 Training Workload는 무엇인가?
5. VRAM Requirement를 어떤 휴리스틱으로 추정할 것인가?
6. 실행시간 추정을 얼마나 정교하게 해야 승인에 필요한 신뢰를 확보할 수 있는가?
7. 한 개 Provider 안에서 지원할 GPU 후보를 몇 개로 제한할 것인가?
8. Artifact 저장 위치는 어디로 할 것인가?

### Cost and BM

9. MVP의 서비스 비용은 실제 과금할 것인가, 예상값만 표시할 것인가?
10. 장기 BM은 Job 수수료, 월 구독, Team 요금제 중 무엇을 우선 검증할 것인가?
11. 사용자는 GPU 실비 외에 인프라 운영 제거에 얼마까지 추가 지불할 의향이 있는가?

### Technical

12. 실제 데모용 Provider는 어디를 선택할 것인가?
13. Provider의 GPU 생성, 상태 조회, 종료 API를 해커톤 시간 안에 안정적으로 연동할 수 있는가?
14. 사용자의 Training Process와 제어 프로세스를 어떻게 분리해 브라우저 종료와 무관하게 실행할 것인가?
15. Provider별 Polling 주기와 API Timeout 설정은 무엇인가?
16. Artifact 보존 위치와 30일 후 물리 삭제 실행 주체는 무엇인가?

---

# Appendix A. Domain Model v0

## Core Entities

```text
User
Training Job
Workload
Runtime Requirement
Constraint
Execution Plan
Compute Resource
Execution Attempt
Artifact
```

## Supporting Entities

```text
Provider
Cost
Job Event
Credential
```

## Core Relationship

```text
User
└─ creates
   └─ Training Job
      ├─ contains → Workload
      ├─ has → Constraint
      └─ derives → Runtime Requirement
                     └─ produces → Execution Plan
                                    ├─ selects → Compute Resource
                                    └─ creates → Execution Attempt
                                                   ├─ incurs → Cost
                                                   └─ produces → Artifact
```

---

# Appendix B. State Model v0

## Training Job State

```text
Draft
↓
Analyzing
↓
Ready
↓
Running
↓
Finalizing
↓
Completed
```

Exception and intermediate states:

```text
AnalysisFailed
CancelRequested
Failed
Cancelled
```

`CancelRequested`는 Training 중단과 Resource 종료 확인 후 `Cancelled`로 전환된다. Resource 종료 미확인이나 Provider Reconciliation은 내부 Resource 상태로 관리하며 사용자-facing Job 상태와 분리한다.

## Execution Attempt State

```text
Pending
↓
Provisioning
↓
Preparing
↓
Running
↓
Finalizing
↓
Succeeded
```

Failure can occur from Provisioning, Preparing, Running, Finalizing.

Attempt는 Training 결과와 Resource Termination 결과를 별도로 기록한다. 입력 오류는 새 Job으로, 시스템·Provider 오류는 기존 Job의 새 Attempt로 재실행한다.

---

# Appendix C. MVP Validation Scenario

## Given

사용자가 MVP 지원 범위에 해당하는 Hugging Face 또는 PyTorch Training Repository를 가지고 있다.

## When

사용자가 다음 세 가지를 입력하고 Execution Plan을 승인한다.

```text
Repository URL
Execution Command
Maximum Budget
```

## Then

사용자는 Provider 콘솔에 접속하거나 SSH를 사용하거나 CUDA 환경을 직접 구성하지 않고 다음 결과에 도달한다.

```text
실제 GPU에서 Training 완료
+
Artifact 확보
+
예산 Guardrail 적용
+
GPU 종료 확인
```

## MVP Success Definition

> 지원되는 Happy Path에서 사용자의 GPU 인프라 직접 조작 횟수는 0회다.

이 정의를 만족하지 않는 기능은 우선순위가 높아 보여도 MVP 핵심 가치 검증과 분리해 판단한다.
