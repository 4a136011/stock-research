# 範例資料（全部為合成）

- `snapshot.synthetic.json`：虛構代號 9999 的研究快照，`is_synthetic: true`，來源標為 `fixture:synthetic`。
  **數值皆為假設用途，不是真實行情、EPS 或財報。** 其中 S13 刻意設為 `error` 狀態（無數值），用來測試「不可引用失敗資料」。
- `*.example.json`：六個角色對上述快照的範例輸出，各欄位的價位都附公式與快照項目。
- 執行器預設拒絕 `is_synthetic: true` 的快照；只有測試以 `allow_synthetic=True` 明確放行。
