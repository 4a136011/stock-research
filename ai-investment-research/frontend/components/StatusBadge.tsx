export type DataStatus = "ok" | "stale" | "partial" | "error" | "missing";

const LABELS: Record<DataStatus, string> = {
  ok: "資料正常",
  stale: "資料過期",
  partial: "資料不完整",
  error: "取得失敗",
  missing: "無資料",
};

const STYLES: Record<DataStatus, string> = {
  ok: "bg-green-100 text-green-800",
  stale: "bg-yellow-100 text-yellow-800",
  partial: "bg-orange-100 text-orange-800",
  error: "bg-red-100 text-red-800",
  missing: "bg-gray-200 text-gray-700",
};

export default function StatusBadge({ status }: { status: DataStatus }) {
  return (
    <span
      data-status={status}
      className={`inline-block rounded px-2 py-0.5 text-xs font-medium ${STYLES[status]}`}
    >
      {LABELS[status]}
    </span>
  );
}
