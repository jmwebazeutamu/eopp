import axios, { AxiosError, type InternalAxiosRequestConfig } from "axios";

const ACCESS_KEY = "yep.access";
const REFRESH_KEY = "yep.refresh";

export const tokens = {
  get access() {
    return localStorage.getItem(ACCESS_KEY);
  },
  get refresh() {
    return localStorage.getItem(REFRESH_KEY);
  },
  set(access: string, refresh?: string) {
    localStorage.setItem(ACCESS_KEY, access);
    if (refresh) localStorage.setItem(REFRESH_KEY, refresh);
  },
  clear() {
    localStorage.removeItem(ACCESS_KEY);
    localStorage.removeItem(REFRESH_KEY);
  },
};

export const api = axios.create({ baseURL: "/api/v1" });

api.interceptors.request.use((config) => {
  const token = tokens.access;
  if (token) config.headers.Authorization = `Bearer ${token}`;
  return config;
});

/**
 * Refresh-on-401, with a single in-flight refresh.
 *
 * Case screens fire several requests at once. Without sharing one promise, each
 * 401 would start its own refresh, and because the backend rotates refresh
 * tokens (ROTATE_REFRESH_TOKENS), the later ones would present a token the
 * first refresh had already consumed and log the user out mid-session.
 */
let refreshInFlight: Promise<string> | null = null;

function refreshAccessToken(): Promise<string> {
  if (!refreshInFlight) {
    const refresh = tokens.refresh;
    if (!refresh) return Promise.reject(new Error("No refresh token"));

    refreshInFlight = axios
      .post<{ access: string; refresh?: string }>("/api/v1/users/token/refresh/", { refresh })
      .then((response) => {
        tokens.set(response.data.access, response.data.refresh);
        return response.data.access;
      })
      .finally(() => {
        refreshInFlight = null;
      });
  }
  return refreshInFlight;
}

api.interceptors.response.use(
  (response) => response,
  async (error: AxiosError) => {
    const original = error.config as InternalAxiosRequestConfig & { _retried?: boolean };
    const isAuthEndpoint = original?.url?.includes("/token/");

    if (error.response?.status === 401 && original && !original._retried && !isAuthEndpoint) {
      original._retried = true;
      try {
        const access = await refreshAccessToken();
        original.headers.Authorization = `Bearer ${access}`;
        return api(original);
      } catch {
        tokens.clear();
        window.location.href = "/login";
      }
    }
    return Promise.reject(error);
  },
);

/** Pull a usable message out of a DRF error body. */
export function errorMessage(error: unknown, fallback = "Something went wrong."): string {
  if (axios.isAxiosError(error)) {
    const data = error.response?.data as Record<string, unknown> | string | undefined;
    if (typeof data === "string") return data;
    if (data && typeof data === "object") {
      const detail = data.detail;
      if (typeof detail === "string") return detail.replace(/^detail:\s*/i, "");
      if (Array.isArray(detail)) return detail.map(String).join(" ").replace(/^detail:\s*/i, "");
      const [field, messages] = Object.entries(data)[0] ?? [];
      if (field && messages) {
        const text = Array.isArray(messages) ? messages.join(" ") : String(messages);
        return text.replace(new RegExp(`^${field}:\\s*`, "i"), "").replace(/^detail:\s*/i, "");
      }
    }
    return error.message;
  }
  return fallback;
}

/** DRF 400/422 field errors in the shape Ant Form expects. */
export function formErrors(error: unknown): Array<{ name: string; errors: string[] }> {
  if (!axios.isAxiosError(error) || !error.response?.data || typeof error.response.data !== "object") return [];
  return Object.entries(error.response.data as Record<string, unknown>)
    .filter(([field]) => !["detail", "non_field_errors"].includes(field))
    .map(([name, value]) => ({ name, errors: (Array.isArray(value) ? value : [value]).map(String) }));
}
