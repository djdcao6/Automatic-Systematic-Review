const TOKEN_STORAGE_KEY = "asr_token";

export function storeToken(token: string): void {
  window.localStorage.setItem(TOKEN_STORAGE_KEY, token);
}

export function getToken(): string | null {
  return window.localStorage.getItem(TOKEN_STORAGE_KEY);
}

export function clearToken(): void {
  window.localStorage.removeItem(TOKEN_STORAGE_KEY);
}
