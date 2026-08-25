import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { cancelJob, getJob, startJob, type JobStatus, type TrainingJob } from '@/api/jobs'

export const POLL_INTERVAL_MS = 2500

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
  return useQuery({
    queryKey: ['job', jobId],
    queryFn: ({ signal }) => getJob(jobId as string, signal),
    enabled: jobId !== null,
    staleTime: Infinity,
    refetchInterval: (query) =>
      isInFlight(query.state.data?.status) ? POLL_INTERVAL_MS : false,
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
