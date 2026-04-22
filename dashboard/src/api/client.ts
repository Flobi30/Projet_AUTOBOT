const API_BASE_URL = import.meta.env.VITE_DASHBOARD_API_BASE_URL || '';

let runtimeApiToken: string | null = import.meta.env.VITE_DASHBOARD_API_TOKEN || null;

export const apiAuth = {
  setToken(token: string | null) {
    runtimeApiToken = token && token.trim().length > 0 ? token : null;
  },
  clearToken() {
    runtimeApiToken = null;
  },
  getToken() {
    return runtimeApiToken;
  },
};

const buildHeaders = (headers?: HeadersInit): Headers => {
  const mergedHeaders = new Headers(headers);
  const token = apiAuth.getToken();
  if (token) {
    mergedHeaders.set('Authorization', `Bearer ${token}`);
  }
  return mergedHeaders;
};

export const apiFetch = (path: string, init: RequestInit = {}) => {
  const url = `${API_BASE_URL}${path}`;
  return fetch(url, {
    ...init,
    credentials: 'include',
    headers: buildHeaders(init.headers),
  });
};
