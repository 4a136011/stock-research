export type HealthResponse = {
  status: "ok";
  version: string;
  app_env: string;
  llm_provider: string;
  database_configured: boolean;
  llm_key_configured: boolean;
};

/** 所有 API 呼叫都回傳明確的成功或錯誤狀態；失敗時絕不回傳替代或虛構資料。 */
export type ApiResult<T> =
  | { ok: true; data: T; fetchedAt: string }
  | { ok: false; error: string; fetchedAt: string };

export function apiBaseUrl(): string {
  return process.env.NEXT_PUBLIC_API_BASE_URL ?? "http://localhost:8000";
}

export async function getHealth(
  fetchImpl: typeof fetch = fetch,
): Promise<ApiResult<HealthResponse>> {
  const fetchedAt = new Date().toISOString();
  try {
    const res = await fetchImpl(`${apiBaseUrl()}/health`, { cache: "no-store" });
    if (!res.ok) {
      return { ok: false, error: `後端回應錯誤（HTTP ${res.status}）`, fetchedAt };
    }
    const data = (await res.json()) as HealthResponse;
    return { ok: true, data, fetchedAt };
  } catch (e) {
    const detail = e instanceof Error ? e.message : String(e);
    return { ok: false, error: `無法連線後端：${detail}`, fetchedAt };
  }
}
