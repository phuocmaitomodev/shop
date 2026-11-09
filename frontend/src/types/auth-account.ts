export type AccountRole = 'customer' | 'admin'

export interface AccountProfile {
  id: string
  email: string
  full_name: string
  phone: string | null
  role: AccountRole
  is_active: boolean
}

export interface LoginRequest {
  email: string
  password: string
}

export interface UpdateAccountProfileRequest {
  full_name: string
  phone: string | null
}

export interface LogoutStatus {
  status: 'logged_out'
}
