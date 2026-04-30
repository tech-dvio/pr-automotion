const KEY = 'pr_admin_token'

export function getToken(): string | null {
  return sessionStorage.getItem(KEY)
}

export function setToken(token: string): void {
  sessionStorage.setItem(KEY, token)
}

export function clearToken(): void {
  sessionStorage.removeItem(KEY)
}

export function isAuthenticated(): boolean {
  return !!getToken()
}
