import type { ApiSuccess } from '../types/api'
import type {
  AccountProfile,
  LoginRequest,
  LogoutStatus,
  UpdateAccountProfileRequest,
} from '../types/auth-account'
import { apiClient, ApiClientError } from './api-client'

const unwrap = <T>(response: ApiSuccess<T>): T => response.data

export const login = async (request: LoginRequest): Promise<AccountProfile> => unwrap(
  await apiClient<ApiSuccess<AccountProfile>>('/auth/login', {
    method: 'POST',
    body: JSON.stringify({
      email: request.email.trim().toLowerCase(),
      password: request.password,
    }),
  }),
)

export const getAccountProfile = async (): Promise<AccountProfile> => unwrap(
  await apiClient<ApiSuccess<AccountProfile>>('/account/profile'),
)

export const updateAccountProfile = async (
  request: UpdateAccountProfileRequest,
): Promise<AccountProfile> => unwrap(
  await apiClient<ApiSuccess<AccountProfile>>('/account/profile', {
    method: 'PATCH',
    body: JSON.stringify({
      full_name: request.full_name.trim(),
      phone: request.phone?.trim() || null,
    }),
  }),
)

export const logout = async (): Promise<void> => {
  await apiClient<ApiSuccess<LogoutStatus>>('/auth/logout', { method: 'POST' })
}

const stableMessages: Record<string, string> = {
  AUTH_REQUIRED: 'Phiên đăng nhập không còn hiệu lực. Vui lòng đăng nhập lại.',
  INVALID_CREDENTIALS: 'Email hoặc mật khẩu không đúng.',
  RATE_LIMITED: 'Bạn thao tác quá nhanh. Vui lòng thử lại sau.',
  VALIDATION_ERROR: 'Thông tin chưa hợp lệ. Vui lòng kiểm tra lại.',
}

export const accountErrorMessage = (error: unknown): string => {
  if (!(error instanceof ApiClientError)) {
    return 'Đã có lỗi xảy ra. Vui lòng thử lại.'
  }
  if (error.status === 0) {
    return 'Không thể kết nối đến máy chủ. Vui lòng thử lại.'
  }

  const code = error.payload?.error.code
  if (code && stableMessages[code]) return stableMessages[code]
  if (error.status === 401) return stableMessages.AUTH_REQUIRED
  if (error.status === 422) return stableMessages.VALIDATION_ERROR
  if (error.status >= 500) return 'Máy chủ đang bận. Vui lòng thử lại sau.'
  return 'Không thể hoàn tất yêu cầu. Vui lòng thử lại.'
}

export const isAuthenticationRequired = (error: unknown): boolean => (
  error instanceof ApiClientError
  && error.status === 401
  && error.payload?.error.code !== 'INVALID_CREDENTIALS'
)
