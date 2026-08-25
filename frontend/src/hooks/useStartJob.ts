import { useMutation } from '@tanstack/react-query'
import { startJob, type JobMutationResponse } from '@/api/jobs'

export function useStartJob(onStarted: (response: JobMutationResponse) => void) {
  return useMutation({
    mutationFn: (jobId: string) => startJob(jobId),
    onSuccess: onStarted,
  })
}
