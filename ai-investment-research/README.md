# AI Investment Research MVP

個人使用的 AI 投資研究網站（台股、美股、國際總經），核心功能是六位 AI 分析師的多空辯論與有條件的研究結論。

**目前進度：階段 A（專案骨架、資料庫 schema、提示詞與測試結構）。**
行情抓取、技術指標、估值、真實 AI 呼叫、報告頁與排程尚未開始，見「交付階段」。

## 專案結構

```
backend/            Python + FastAPI（api / agents / data_sources / indicators / valuation / debate / backtest / tests）
frontend/           Next.js + TypeScript + Tailwind
database/           migrations（PostgreSQL / Supabase）與約束測試
prompts/            六個角色提示詞、_shared.md 共用規則、examples/ 合成範例
scripts/            check_phase_a.py：僅用標準庫的結構驗收
.github/workflows/  CI（後端、資料庫、前端）；排程於階段 F 加入
```

## 前置需求

Python 3.11+、Node 20+（建議 22）、Docker（僅用於本機 PostgreSQL，可選）、`psql`（套用 migration 與約束測試用）。

## 本機啟動

### 1. 後端

```bash
python -m venv .venv
source .venv/bin/activate          # Windows PowerShell：.venv\Scripts\Activate.ps1
pip install -e ".[dev]"
cp .env.example .env               # 預設 LLM_PROVIDER=mock，不會呼叫任何外部 API
uvicorn backend.api.main:app --reload --port 8000
```

驗證：`curl http://localhost:8000/health` 應回傳 `{"status":"ok", ...}`，且不含任何密鑰內容。

### 2. 資料庫（本機，不涉及雲端）

```bash
docker compose up -d db
export DATABASE_URL="postgresql://postgres:localdev@localhost:5432/ai_research"
psql "$DATABASE_URL" -v ON_ERROR_STOP=1 -f database/migrations/001_init.sql   # 可重複執行
psql "$DATABASE_URL" -v ON_ERROR_STOP=1 -f database/tests/constraints.sql     # 應印出 constraints OK
```

首次建立 volume 時，compose 會自動套用 `database/migrations/*.sql`；之後新增的 migration 請手動以 `psql` 套用。

### 3. 前端

```bash
cd frontend
echo "NEXT_PUBLIC_API_BASE_URL=http://localhost:8000" > .env.local
npm install
npm run dev                        # http://localhost:3000
```

首頁會顯示後端連線狀態；停掉後端後重新整理，應顯示「取得失敗」與錯誤訊息，而不是舊資料或假資料。

## 環境變數

| 變數 | 必要 | 說明 |
|---|---|---|
| `APP_ENV` | 否 | `development` / `test` / `production` |
| `LOG_LEVEL` | 否 | 預設 `INFO` |
| `CORS_ORIGINS` | 否 | 逗號分隔，預設 `http://localhost:3000` |
| `DATABASE_URL` | 階段 B 起 | PostgreSQL 連線字串 |
| `SUPABASE_URL` / `SUPABASE_SERVICE_ROLE_KEY` | 使用 Supabase 時 | service role 金鑰只能放後端環境變數，不可放前端或 `NEXT_PUBLIC_*` |
| `LLM_PROVIDER` | 否 | 預設 `mock`；真實 provider 於階段 D 加入 |
| `LLM_MODEL` / `LLM_API_KEY` | 階段 D 起 | 啟用真實 provider 時才需要 |
| `LLM_MAX_TOKENS` | 否 | 單次輸出上限，預設 2000 |
| `LLM_DAILY_CALL_LIMIT` | 否 | 每日 AI 呼叫次數上限（成本保護），階段 D 起強制執行 |
| `NEXT_PUBLIC_API_BASE_URL` | 前端 | 放在 `frontend/.env.local`，Next.js 不讀根目錄 `.env` |

`.env` 已被 `.gitignore` 排除；`.env.example` 只含變數名稱與安全預設值。

## 測試

```bash
python scripts/check_phase_a.py    # 結構驗收（不需安裝依賴）
pytest                             # 後端：schema、runner、提示詞、設定、/health、結構驗收
cd frontend && npm run typecheck && npm test
```

資料庫約束測試見上方「資料庫」。CI（`.github/workflows/ci.yml`）會自動跑後端、前端，並在 PostgreSQL 16 容器上套用 migration 兩次、跑約束測試。

## 六個角色與輸出 schema

| 角色 | 職責 |
|---|---|
| `macro` | 宏觀經濟與市場環境 |
| `fundamental` | 基本面、財報、產業競爭力與估值 |
| `technical` | 技術指標、趨勢、支撐壓力與訊號 |
| `bull` | 最強看多論點、催化劑、價格上修條件、潛在報酬 |
| `bear` | 挑戰多方假設、估值風險、利空情境、失效條件 |
| `adjudicator` | 檢查證據、處理分歧、比較情境，輸出有條件的結論 |

- 共用輸出 schema 在 `backend/agents/schemas.py`：論點、證據、假設、反證、風險、信心、失效條件、價位與資料缺口。完整 JSON Schema 會在執行時附進每個 system prompt，確保提示詞與驗證不會脫節。
- **獨立性**：`bull` / `bear` 的 initial 階段 `seen_roles` 必須為空。三層強制：提示詞要求、runner 在呼叫前阻擋並比對輸出宣稱、資料庫 `CHECK`。
- **證據**：輸出只能引用快照項目 id；不存在、或狀態為 `error` / `missing` 的項目都會被拒絕。
- **價位**：每個價位必須有 `calculation` 與至少一個數值型快照項目；沒有依據的價位無法通過驗證。
- **裁決**：不使用多數決；`watch`（觀望）與 `insufficient_evidence` 是合法結論，證據不足時不給情境價位。方向性結論必須附行動條件與失效條件。
- 範例在 `prompts/examples/`，**全為合成資料**（虛構代號 9999，`is_synthetic: true`）。執行器預設拒絕合成快照。

## 資料原則

所有外部資料保存 `source`、`fetched_at`、`data_status`。抓取失敗只寫入 `data_fetch_log`（`status='error'`）並在介面顯示錯誤狀態，資料表內不存放任何替代或虛構數值。資料來源優先使用免費、官方、合法可取得者（台股：TWSE / TPEx 開放資料；美股與總經：SEC EDGAR、FRED，待階段 B 之後依實際條款確認）。

## 部署說明

階段 A **不會建立任何雲端資源**，也不會產生 API 費用。預計流程如下，每一步都需你手動確認後才進行：

1. **資料庫**：建立 Supabase 專案（先用免費方案），於 SQL Editor 執行 `database/migrations/001_init.sql`。所有表已啟用 RLS 且無 policy，前端無法直接讀寫；後端以 service role 或資料庫連線存取。
2. **後端**：階段 F 前補上 Dockerfile 與部署設定（候選：Render / Fly.io / Cloud Run，皆可能產生費用）。環境變數在平台後台設定，不進 Git。
3. **前端**：Vercel（Hobby）。設定 `NEXT_PUBLIC_API_BASE_URL` 指向後端網址，並在後端 `CORS_ORIGINS` 加入前端網域。
4. **排程**：階段 F 以 GitHub Actions；金鑰存放於 repository secrets。
5. **AI 用量**：啟用真實 provider 前，先確認 `LLM_DAILY_CALL_LIMIT` 與供應商端的用量上限。

## 階段 A 驗收標準

1. `python scripts/check_phase_a.py` 全部 PASS。
2. `pytest` 全部通過。
3. `uvicorn` 啟動後 `/health` 回 200，內容不含密鑰。
4. `001_init.sql` 在空資料庫連續執行兩次不報錯，建立 8 張表（`\dt`）；`constraints.sql` 印出 `constraints OK`。
5. `cd frontend && npm run typecheck && npm test` 通過；`npm run dev` 的首頁在後端運行時顯示「資料正常」，停掉後端後顯示「取得失敗」。
6. `git grep -nE "sk-|service_role|BEGIN .*PRIVATE KEY"` 找不到真實密鑰；`git status` 不含 `.env`。

## 交付階段

| 階段 | 內容 | 狀態 |
|---|---|---|
| A | 專案骨架、資料庫 schema、提示詞、輸出 schema、測試結構 | 本次交付 |
| B | 單一股票行情與研究快照 | 未開始 |
| C | 技術指標與基本估值 | 未開始 |
| D | AI 分析師辯論（含真實 provider） | 未開始 |
| E | 網站報告頁（觀察清單、個股研究頁） | 未開始 |
| F | 排程、錯誤處理、預測追蹤 | 未開始 |
