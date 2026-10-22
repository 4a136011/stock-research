import StatusBadge from "@/components/StatusBadge";
import { getHealth } from "@/lib/api";

export const dynamic = "force-dynamic";

export default async function Home() {
  const result = await getHealth();

  return (
    <main className="mx-auto max-w-3xl p-8">
      <h1 className="text-2xl font-semibold">AI 投資研究</h1>
      <p className="mt-2 text-sm text-gray-600">
        階段 A：專案骨架。觀察清單與個股研究頁將於後續階段加入。
      </p>

      <section className="mt-6 rounded border bg-white p-4">
        <div className="flex items-center gap-2">
          <h2 className="font-medium">後端連線狀態</h2>
          <StatusBadge status={result.ok ? "ok" : "error"} />
        </div>

        {result.ok ? (
          <dl className="mt-3 grid grid-cols-2 gap-1 text-sm">
            <dt className="text-gray-500">版本</dt>
            <dd>{result.data.version}</dd>
            <dt className="text-gray-500">環境</dt>
            <dd>{result.data.app_env}</dd>
            <dt className="text-gray-500">AI provider</dt>
            <dd>{result.data.llm_provider}</dd>
            <dt className="text-gray-500">資料庫已設定</dt>
            <dd>{result.data.database_configured ? "是" : "否"}</dd>
            <dt className="text-gray-500">AI 金鑰已設定</dt>
            <dd>{result.data.llm_key_configured ? "是" : "否"}</dd>
          </dl>
        ) : (
          <p className="mt-3 text-sm text-red-700">{result.error}</p>
        )}

        <p className="mt-3 text-xs text-gray-400">檢查時間：{result.fetchedAt}</p>
      </section>
    </main>
  );
}
