import { useCallback, useState } from 'react'
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { cancelJob, getJob, startJob, type JobStatus, type TrainingJob } from '@/api/jobs'

export const POLL_INTERVAL_MS = 2500
export const MAX_POLL_INTERVAL_MS = 15_000

/** 연속 실패는 지수 backoff으로 늦춘다. 최종 상태를 임의로 추정하지 않는다. */
export function pollIntervalMs(consecutiveFailures: number): number {
  return Math.min(MAX_POLL_INTERVAL_MS, POLL_INTERVAL_MS * 2 ** consecutiveFailures)
}

const IN_FLIGHT: ReadonlySet<JobStatus> = new Set<JobStatus>([
  'PROVISIONING',
  'RUNNING',
  'TERMINATING',
])

/** TERMINATING은 최종 상태가 아니다. 자원 종료 확인까지 계속 폴링한다. */
export function isInFlight(status: JobStatus | undefined): boolean {
  return status !== undefined && IN_FLIGHT.has(status)
}

export function jobKey(jobId: string) {
  return ['job', jobId] as const
}

export function useJob(jobId: string | null) {
  // 연속 실패 수를 직접 센다. 라이브러리의 fetchFailureCount는 retry 경로에서
  // 한 번의 실패에도 두 번 증가해 간격 계산에 쓸 수 없다.
  const [consecutiveFailures, setConsecutiveFailures] = useState(0)

  const queryFn = useCallback(
    async ({ signal }: { signal: AbortSignal }) => {
      try {
        const job = await getJob(jobId as string, signal)
        setConsecutiveFailures(0)
        return job
      } catch (error) {
        setConsecutiveFailures((count) => count + 1)
        throw error
      }
    },
    [jobId],
  )

  return useQuery({
    queryKey: ['job', jobId],
    queryFn,
    enabled: jobId !== null,
    staleTime: Infinity,
    retry: false,
    refetchInterval: (query) =>
      isInFlight(query.state.data?.status) ? pollIntervalMs(consecutiveFailures) : false,
  })
}

/**
 * 서버가 알려 준 상태를 즉시 반영한 뒤 GET으로 다시 확인한다.
 * mutation 응답만으로 최종 상태를 추정하지 않는다.
 */
function useJobStatusMutation(request: (jobId: string) => Promise<{ status: JobStatus }>) {
  const queryClient = useQueryClient()

  return useMutation({
    // 인자를 하나만 넘긴다. 함수를 그대로 넘기면 두 번째 인자가 AbortSignal 자리로 들어간다.
    mutationFn: (jobId: string) => request(jobId),
    onSuccess: (response, jobId) => {
      queryClient.setQueryData<TrainingJob>(jobKey(jobId), (current) =>
        current ? { ...current, status: response.status } : current,
      )
      void queryClient.invalidateQueries({ queryKey: jobKey(jobId) })
    },
  })
}

export function useStartJob() {
  return useJobStatusMutation(startJob)
}

export function useCancelJob() {
  return useJobStatusMutation(cancelJob)
}
