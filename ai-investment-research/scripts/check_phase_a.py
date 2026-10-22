#!/usr/bin/env python3
"""階段 A 結構驗收（僅用標準庫，未安裝任何依賴也能執行）。

檢查：必要檔案、提示詞段落、migration 結構、.env.example 與 .gitignore、
範例 JSON 與 schema/快照的一致性、疑似密鑰掃描、Python 語法。
用法：python scripts/check_phase_a.py   （全部通過 exit 0，否則 exit 1）
"""

from __future__ import annotations

import ast
import json
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]

ROLES = ["macro", "fundamental", "technical", "bull", "bear", "adjudicator"]
PROMPT_HEADINGS = ["## 角色定位", "## 輸入", "## 分析要求", "## 禁止事項", "## 輸出重點"]
TABLES = [
    "instruments", "watchlist", "price_bars", "financial_statements",
    "data_fetch_log", "research_runs", "debate_messages", "predictions",
]
# 這兩張表的 source / fetched_at / data_status 必須 NOT NULL
STRICT_EXTERNAL_TABLES = ["price_bars", "financial_statements"]
ENV_REQUIRED_KEYS = [
    "APP_ENV", "LOG_LEVEL", "CORS_ORIGINS", "DATABASE_URL", "SUPABASE_URL",
    "SUPABASE_SERVICE_ROLE_KEY", "LLM_PROVIDER", "LLM_MODEL", "LLM_API_KEY",
    "LLM_MAX_TOKENS", "LLM_DAILY_CALL_LIMIT", "NEXT_PUBLIC_API_BASE_URL",
]
REQUIRED_PATHS = [
    "README.md", "pyproject.toml", ".env.example", ".gitignore", "docker-compose.yml",
    ".github/workflows/ci.yml",
    "database/migrations/001_init.sql", "database/tests/constraints.sql",
    "backend/config.py", "backend/api/main.py",
    "backend/agents/schemas.py", "backend/agents/provider.py",
    "backend/agents/prompt_loader.py", "backend/agents/runner.py",
    "backend/data_sources/__init__.py", "backend/indicators/__init__.py",
    "backend/valuation/__init__.py", "backend/debate/__init__.py", "backend/backtest/__init__.py",
    "backend/tests/conftest.py",
    "prompts/_shared.md", "prompts/examples/snapshot.synthetic.json",
    "frontend/package.json", "frontend/tsconfig.json", "frontend/app/layout.tsx",
    "frontend/app/page.tsx", "frontend/lib/api.ts", "frontend/components/StatusBadge.tsx",
]
REQUIRED_PATHS += [f"prompts/{r}.md" for r in ROLES]
REQUIRED_PATHS += [f"prompts/examples/{r}.example.json" for r in ROLES]

SECRET_PATTERNS = [
    re.compile(r"sk-[A-Za-z0-9_-]{20,}"),
    re.compile(r"eyJ[A-Za-z0-9_-]{20,}\.[A-Za-z0-9_-]{10,}"),
    re.compile(r"AIza[0-9A-Za-z_-]{30,}"),
    re.compile(r"-----BEGIN [A-Z ]*PRIVATE KEY-----"),
    re.compile(r"postgres(?:ql)?://[^:\s/]+:(?!localdev\b|postgres\b)[^@\s]{6,}@"),
]
SKIP_DIRS = {".git", "node_modules", ".next", ".venv", "__pycache__", ".pytest_cache", ".ruff_cache", "coverage", "build"}
SCAN_SUFFIXES = {".py", ".ts", ".tsx", ".md", ".json", ".yml", ".yaml", ".sql", ".toml", ".mjs", ".css", ".example"}


def _text(rel: str) -> str:
    return (ROOT / rel).read_text(encoding="utf-8")


def _walk(root: Path):
    for path in root.rglob("*"):
        if any(part in SKIP_DIRS for part in path.relative_to(ROOT).parts):
            continue
        if path.is_file():
            yield path


def check_structure() -> list[str]:
    return [f"缺少檔案：{p}" for p in REQUIRED_PATHS if not (ROOT / p).is_file()]


def check_prompts() -> list[str]:
    problems = []
    for role in ROLES:
        path = ROOT / "prompts" / f"{role}.md"
        if not path.is_file():
            continue
        text = path.read_text(encoding="utf-8")
        problems += [f"prompts/{role}.md 缺少段落 {h}" for h in PROMPT_HEADINGS if h not in text]
    return problems


def check_migration() -> list[str]:
    path = ROOT / "database/migrations/001_init.sql"
    if not path.is_file():
        return ["缺少 migration"]
    sql = path.read_text(encoding="utf-8")
    problems = []
    tables = dict(re.findall(r"CREATE TABLE IF NOT EXISTS (\w+) \((.*?)\n\);", sql, re.S))
    for t in TABLES:
        if t not in tables:
            problems.append(f"migration 缺少資料表 {t}")
        if f"ALTER TABLE {t}" not in sql or not re.search(
            rf"ALTER TABLE {t}\s+ENABLE ROW LEVEL SECURITY;", sql
        ):
            problems.append(f"資料表 {t} 未啟用 RLS")
    for t in STRICT_EXTERNAL_TABLES:
        body = tables.get(t, "")
        for col, typ in (("source", "text"), ("fetched_at", "timestamptz"), ("data_status", "text")):
            if not re.search(rf"^\s+{col}\s+{typ} NOT NULL", body, re.M):
                problems.append(f"{t}.{col} 必須為 NOT NULL")
    for col in ("source", "fetched_at", "data_status"):
        if not re.search(rf"^\s+{col}\s", tables.get("instruments", ""), re.M):
            problems.append(f"instruments 缺少欄位 {col}")
    if "cardinality(seen_roles) = 0" not in tables.get("debate_messages", ""):
        problems.append("debate_messages 缺少 bull/bear 獨立性 CHECK（cardinality(seen_roles) = 0）")
    if "status IN ('ok', 'partial', 'error', 'skipped')" not in tables.get("data_fetch_log", ""):
        problems.append("data_fetch_log 缺少 status 約束")
    if re.search(r"\b(DROP\s+TABLE|TRUNCATE|DELETE\s+FROM)\b", sql, re.I):
        problems.append("migration 不得包含 DROP TABLE / TRUNCATE / DELETE FROM")
    return problems


def check_env_and_gitignore() -> list[str]:
    problems = []
    env_path = ROOT / ".env.example"
    if env_path.is_file():
        values = {}
        for line in env_path.read_text(encoding="utf-8").splitlines():
            line = line.strip()
            if line and not line.startswith("#") and "=" in line:
                k, v = line.split("=", 1)
                values[k.strip()] = v.strip()
        problems += [f".env.example 缺少變數 {k}" for k in ENV_REQUIRED_KEYS if k not in values]
        for k, v in values.items():
            if re.search(r"(_KEY|SECRET|PASSWORD|_TOKEN)$", k) and v:
                problems.append(f".env.example 的 {k} 不可有值（密鑰只能留空）")
        if values.get("LLM_PROVIDER") != "mock":
            problems.append(".env.example 的 LLM_PROVIDER 預設必須是 mock（避免意外產生用量）")
    gi_path = ROOT / ".gitignore"
    if gi_path.is_file():
        lines = {l.strip() for l in gi_path.read_text(encoding="utf-8").splitlines()}
        for needed in (".env", "node_modules/", ".next/", ".venv/", "!.env.example"):
            if needed not in lines:
                problems.append(f".gitignore 缺少 {needed}")
    return problems


def _model_fields(schema_src: str, class_name: str) -> tuple[set[str], set[str]]:
    tree = ast.parse(schema_src)
    for node in tree.body:
        if isinstance(node, ast.ClassDef) and node.name == class_name:
            allowed, required = set(), set()
            for stmt in node.body:
                if isinstance(stmt, ast.AnnAssign) and isinstance(stmt.target, ast.Name):
                    name = stmt.target.id
                    allowed.add(name)
                    value = stmt.value
                    if value is None:
                        required.add(name)
                    elif (
                        isinstance(value, ast.Call)
                        and getattr(value.func, "id", None) == "Field"
                        and not value.args
                        and not any(k.arg in ("default", "default_factory") for k in value.keywords)
                    ):
                        required.add(name)
            return allowed, required
    raise KeyError(class_name)


def _collect_evidence_ids(node) -> list[str]:
    found = []
    if isinstance(node, dict):
        for k, v in node.items():
            if k == "evidence_ids" and isinstance(v, list):
                found += v
            else:
                found += _collect_evidence_ids(v)
    elif isinstance(node, list):
        for v in node:
            found += _collect_evidence_ids(v)
    return found


def check_examples() -> list[str]:
    ex = ROOT / "prompts" / "examples"
    schema_path = ROOT / "backend/agents/schemas.py"
    if not (ex / "snapshot.synthetic.json").is_file() or not schema_path.is_file():
        return ["範例或 schema 檔案缺失"]
    problems = []
    try:
        snapshot = json.loads((ex / "snapshot.synthetic.json").read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        return [f"snapshot.synthetic.json 不是合法 JSON：{exc}"]
    if snapshot.get("is_synthetic") is not True:
        problems.append("snapshot.synthetic.json 必須標示 is_synthetic: true")
    items = {i["id"]: i for i in snapshot["items"]}
    if len(items) != len(snapshot["items"]):
        problems.append("快照項目 id 重複")
    for i in snapshot["items"]:
        has_value = i.get("value") is not None
        if i["status"] in ("error", "missing") and has_value:
            problems.append(f"{i['id']} 狀態為 {i['status']} 卻帶有數值")
        if i["status"] not in ("error", "missing") and not has_value:
            problems.append(f"{i['id']} 狀態為 {i['status']} 卻沒有數值")
    if not any(i["status"] == "error" for i in snapshot["items"]):
        problems.append("快照應包含至少一個 error 狀態項目，用於測試")

    src = schema_path.read_text(encoding="utf-8")
    for role in ROLES:
        path = ex / f"{role}.example.json"
        if not path.is_file():
            continue
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
        except json.JSONDecodeError as exc:
            problems.append(f"{path.name} 不是合法 JSON：{exc}")
            continue
        cls = "AdjudicationOutput" if role == "adjudicator" else "AnalystOutput"
        allowed, required = _model_fields(src, cls)
        problems += [f"{path.name} 有 schema 未定義的欄位 {k}" for k in data if k not in allowed]
        problems += [f"{path.name} 缺少必填欄位 {k}" for k in sorted(required - set(data))]
        if data.get("symbol") != snapshot["symbol"] or data.get("snapshot_id") != snapshot["snapshot_id"]:
            problems.append(f"{path.name} 的 symbol/snapshot_id 與快照不一致")
        for eid in _collect_evidence_ids(data):
            item = items.get(eid)
            if item is None:
                problems.append(f"{path.name} 引用不存在的快照項目 {eid}")
            elif item["status"] in ("error", "missing"):
                problems.append(f"{path.name} 引用狀態為 {item['status']} 的項目 {eid}")
        for field in ("price_levels", "scenarios"):
            for n, obj in enumerate(data.get(field, [])):
                numeric = [items[e] for e in obj["evidence_ids"] if e in items]
                if not any(isinstance(i["value"], (int, float)) for i in numeric):
                    problems.append(f"{path.name} {field}[{n}] 沒有數值型證據")
                if len(obj.get("calculation", "")) < 10:
                    problems.append(f"{path.name} {field}[{n}] 缺少計算依據")
        if role in ("bull", "bear") and (data.get("phase") != "initial" or data.get("seen_roles")):
            problems.append(f"{path.name} 初始範例的 seen_roles 必須為空")
    return problems


def check_no_secrets() -> list[str]:
    problems = []
    for path in _walk(ROOT):
        if path.name == ".env" or path.name.startswith(".env.") and path.name != ".env.example":
            problems.append(f"不應存在的環境檔：{path.relative_to(ROOT)}")
            continue
        if path.suffix not in SCAN_SUFFIXES and path.name != ".env.example":
            continue
        try:
            content = path.read_text(encoding="utf-8")
        except (UnicodeDecodeError, OSError):
            continue
        for pattern in SECRET_PATTERNS:
            if pattern.search(content):
                problems.append(f"疑似密鑰：{path.relative_to(ROOT)}（符合 {pattern.pattern[:24]}…）")
    return problems


def check_python_compiles() -> list[str]:
    problems = []
    for path in _walk(ROOT):
        if path.suffix == ".py":
            try:
                ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
            except SyntaxError as exc:
                problems.append(f"語法錯誤：{path.relative_to(ROOT)}:{exc.lineno}：{exc.msg}")
    return problems


CHECKS = [
    ("structure", check_structure),
    ("prompts", check_prompts),
    ("migration", check_migration),
    ("env_and_gitignore", check_env_and_gitignore),
    ("examples", check_examples),
    ("no_secrets", check_no_secrets),
    ("python_compiles", check_python_compiles),
]


def main() -> int:
    failed = 0
    for name, func in CHECKS:
        problems = func()
        print(f"[{'FAIL' if problems else 'PASS'}] {name}")
        for p in problems:
            print(f"    - {p}")
        failed += bool(problems)
    print(f"\n{len(CHECKS) - failed}/{len(CHECKS)} checks passed")
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())
