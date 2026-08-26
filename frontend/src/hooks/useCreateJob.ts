import { useMutation, useQueryClient } from '@tanstack/react-query'
import { createJob, type CreateJobInput, type TrainingJob } from '@/api/jobs'
import { jobKey } from './useJob'

export function useCreateJob(onCreated: (job: TrainingJob) => void) {
  const queryClient = useQueryClient()

  return useMutation({
    mutationFn: (input: CreateJobInput) => createJob(input),
    onSuccess: (job) => {
      // POST /jobs 응답이 검토 화면의 유일한 데이터 원본이다.
      queryClient.setQueryData(jobKey(job.id), job)
      // 비교만 한 작업은 저장하지 않는다. 비용이 없고 다시 만들면 되므로
      // 복구 대상이 아니다. 저장하면 다음 방문에 소개 화면을 건너뛰게 된다.
      onCreated(job)
    },
  })
}
