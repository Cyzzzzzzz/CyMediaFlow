type ApiEnvelope<T> = { data: T; request_id: string };
export class ApiError extends Error {
  constructor(message: string, public readonly status: number) { super(message); }
}
export async function apiRequest<T>(path: string, init?: RequestInit): Promise<T> {
  const response = await fetch(path, { ...init, headers: { "Content-Type": "application/json", ...init?.headers } });
  const payload = (await response.json()) as ApiEnvelope<T> & { error?: { message?: string } };
  if (!response.ok) throw new ApiError(payload.error?.message ?? "请求失败", response.status);
  return payload.data;
}
