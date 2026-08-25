import { useMutation, useQueryClient } from '@tanstack/react-query'
import { createJob, type CreateJobInput, type TrainingJob } from '@/api/jobs'

const ACTIVE_JOB_KEY = 'unwork.activeJobId'

export function useCreateJob(onCreated: (job: TrainingJob) => void) {
  const queryClient = useQueryClient()

  return useMutation({
    mutationFn: (input: CreateJobInput) => createJob(input),
    onSuccess: (job) => {
      // POST /jobs 응답이 검토 화면의 유일한 데이터 원본이다.
      queryClient.setQueryData(['job', job.id], job)
      try {
        window.localStorage.setItem(ACTIVE_JOB_KEY, job.id)
      } catch {
        // Storage를 못 쓰는 브라우저에서도 현재 흐름은 계속된다.
      }
      onCreated(job)
    },
  })
}
