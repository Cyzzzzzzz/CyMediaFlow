type ApiEnvelope<T> = { data: T; request_id: string };
export class ApiError extends Error {
  constructor(message: string, public readonly status: number, public readonly code?: string, public readonly details?: Record<string, unknown>) { super(message); }
}
export async function apiRequest<T>(path: string, init?: RequestInit): Promise<T> {
  const response = await fetch(path, { ...init, headers: { "Content-Type": "application/json", ...init?.headers } });
  const payload = (await response.json()) as ApiEnvelope<T> & { error?: { code?: string; message?: string; details?: Record<string, unknown> } };
  if (!response.ok) throw new ApiError(payload.error?.message ?? "请求失败", response.status, payload.error?.code, payload.error?.details);
  return payload.data;
}
