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