import { useMutation, useQueryClient } from '@tanstack/react-query'
import { createJob, type CreateJobInput, type TrainingJob } from '@/api/jobs'
import { writeActiveJobId } from '@/features/training/activeJob'
import { jobKey } from './useJob'

export function useCreateJob(onCreated: (job: TrainingJob) => void) {
  const queryClient = useQueryClient()

  return useMutation({
    mutationFn: (input: CreateJobInput) => createJob(input),
    onSuccess: (job) => {
      // POST /jobs 응답이 검토 화면의 유일한 데이터 원본이다.
      queryClient.setQueryData(jobKey(job.id), job)
      writeActiveJobId(job.id)
      onCreated(job)
    },
  })
}
