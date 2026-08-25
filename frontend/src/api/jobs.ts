import { apiFetch } from './client'

export type Priority = 'CHEAPEST' | 'BALANCED' | 'FASTEST'
export type Eligibility = 'ELIGIBLE' | 'OVER_BUDGET'
export type JobStatus =
  | 'DRAFT'
  | 'PROVISIONING'
  | 'RUNNING'
  | 'TERMINATING'
  | 'COMPLETED'
  | 'FAILED'
  | 'CANCELLED'

/** 고정 workload. 값은 서버 설정으로 바뀌므로 클라이언트 상수로 굳히지 않는다. */
export interface Scenario {
  name: string
  repositoryUrl: string
  executionCommand: string
  requiredVramGb: number
  maxRuntimeMinutes: number
}

export interface PlanCandidate {
  profileId: string
  provider: string
  gpuType: string
  estimatedRuntimeMinutes: number
  estimatedGpuCostKrw: number
  eligibility: Eligibility
}

export interface RecommendedPlan {
  profileId: string
  provider: string
  gpuType: string
  estimatedRuntimeMinutes: number
  estimatedGpuCostKrw: number
  reason: string
}

export interface ExecutionPlan {
  priceDataType: string
  estimateDisclaimer: string
  selectionPolicyVersion: string
  candidates: PlanCandidate[]
  recommended: RecommendedPlan
}

export interface TrainingJob {
  id: string
  scenario: Scenario
  constraint: { maxBudgetKrw: number; priority: Priority }
  executionPlan: ExecutionPlan
  status: JobStatus
  failureMessage: string | null
  exitCode: number | null
  completionLog: string | null
  startedAt: string | null
  finishedAt: string | null
  podTerminatedAt: string | null
}

export interface CreateJobInput {
  maxBudgetKrw: number
  priority: Priority
}

/** 제약을 보내고 Agent가 고정한 추천 실행 계약을 받는다. */
export function createJob(input: CreateJobInput, signal?: AbortSignal): Promise<TrainingJob> {
  return apiFetch<TrainingJob>('/jobs', {
    method: 'POST',
    body: JSON.stringify(input),
    signal,
  })
}
