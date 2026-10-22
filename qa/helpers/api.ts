import { expect, request, type APIRequestContext, type APIResponse } from '@playwright/test'

export interface ApiErrorEnvelope {
  error: {
    code: string
    message: string
    fields: Record<string, string>
    details: Record<string, unknown>
  }
  meta: { request_id: string }
}

export const createApiContext = async (): Promise<APIRequestContext> =>
  request.newContext({
    baseURL: process.env.QA_API_BASE_URL ?? 'http://127.0.0.1:8000/api/v1',
    extraHTTPHeaders: { Accept: 'application/json' },
  })

export const expectApiError = async (
  response: APIResponse,
  expectedStatus: number,
  expectedCode: string,
): Promise<ApiErrorEnvelope> => {
  expect(response.status()).toBe(expectedStatus)
  const body = (await response.json()) as ApiErrorEnvelope
  expect(body.error.code).toBe(expectedCode)
  expect(body.meta.request_id).toBeTruthy()
  return body
}
