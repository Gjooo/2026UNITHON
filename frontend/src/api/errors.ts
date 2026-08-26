/** 백엔드 공통 오류 응답: { "error": { "code", "message" } } */
export interface ApiErrorBody {
  error: { code: string; message: string }
}

export class ApiError extends Error {
  readonly code: string
  readonly status: number

  constructor(code: string, message: string, status: number) {
    super(message)
    this.name = 'ApiError'
    this.code = code
    this.status = status
  }
}

export class NetworkError extends Error {
  constructor(cause: unknown) {
    super('네트워크 요청에 실패했습니다.')
    this.name = 'NetworkError'
    this.cause = cause
  }
}

export async function toApiError(response: Response): Promise<ApiError> {
  let code = 'UNKNOWN_ERROR'
  let message = '요청을 처리하지 못했습니다.'
  try {
    const body = (await response.json()) as Partial<ApiErrorBody>
    if (body?.error?.code) code = body.error.code
    if (body?.error?.message) message = body.error.message
  } catch {
    // 본문이 없거나 JSON이 아니면 기본값을 유지한다.
  }
  return new ApiError(code, message, response.status)
}
