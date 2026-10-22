-- 約束測試：每個「應被拒絕」的寫入都必須觸發對應錯誤，否則腳本失敗。
-- 執行：psql "$DATABASE_URL" -v ON_ERROR_STOP=1 -f database/tests/constraints.sql
-- 全程在交易內並於最後 ROLLBACK，不留下任何資料。

BEGIN;

INSERT INTO instruments (market, symbol) VALUES ('TW', '9999');
INSERT INTO research_runs (instrument_id)
    SELECT id FROM instruments WHERE market = 'TW' AND symbol = '9999';

DO $$
DECLARE
    rid uuid;
    iid uuid;
BEGIN
    SELECT id INTO rid FROM research_runs LIMIT 1;
    SELECT id INTO iid FROM instruments WHERE market = 'TW' AND symbol = '9999';

    -- 1. bull 初始分析宣稱看過 bear → 必須被拒
    BEGIN
        INSERT INTO debate_messages (run_id, seq, role, phase, seen_roles, content, validation_status)
        VALUES (rid, 1, 'bull', 'initial', ARRAY['bear'], '{}'::jsonb, 'valid');
        RAISE EXCEPTION 'FAIL: bull initial with seen_roles was accepted';
    EXCEPTION WHEN check_violation THEN NULL;
    END;

    -- 2. bear 初始分析宣稱看過 macro → 同樣必須被拒（初始階段不得看過任何輸出）
    BEGIN
        INSERT INTO debate_messages (run_id, seq, role, phase, seen_roles, content, validation_status)
        VALUES (rid, 2, 'bear', 'initial', ARRAY['macro'], '{}'::jsonb, 'valid');
        RAISE EXCEPTION 'FAIL: bear initial with seen_roles was accepted';
    EXCEPTION WHEN check_violation THEN NULL;
    END;

    -- 3. 合法的 bull 初始分析（seen_roles 為空）→ 必須成功
    INSERT INTO debate_messages (run_id, seq, role, phase, seen_roles, content, validation_status)
    VALUES (rid, 3, 'bull', 'initial', '{}', '{}'::jsonb, 'valid');

    -- 4. adjudicator 與 initial 階段不相容
    BEGIN
        INSERT INTO debate_messages (run_id, seq, role, phase, content, validation_status)
        VALUES (rid, 4, 'adjudicator', 'initial', '{}'::jsonb, 'valid');
        RAISE EXCEPTION 'FAIL: adjudicator in initial phase was accepted';
    EXCEPTION WHEN check_violation THEN NULL;
    END;

    -- 5. 無效輸出必須附錯誤訊息
    BEGIN
        INSERT INTO debate_messages (run_id, seq, role, phase, raw_response, validation_status)
        VALUES (rid, 5, 'macro', 'initial', 'garbage', 'invalid');
        RAISE EXCEPTION 'FAIL: invalid message without validation_error was accepted';
    EXCEPTION WHEN check_violation THEN NULL;
    END;

    -- 6. 行情 high < low → 必須被拒
    BEGIN
        INSERT INTO price_bars (instrument_id, trade_date, open, high, low, close, source, fetched_at, data_status)
        VALUES (iid, DATE '2026-10-21', 100, 90, 95, 100, 'test', now(), 'ok');
        RAISE EXCEPTION 'FAIL: price bar with high < low was accepted';
    EXCEPTION WHEN check_violation THEN NULL;
    END;

    -- 7. 行情缺少來源 → 必須被拒
    BEGIN
        INSERT INTO price_bars (instrument_id, trade_date, open, high, low, close, fetched_at, data_status)
        VALUES (iid, DATE '2026-10-21', 100, 101, 99, 100, now(), 'ok');
        RAISE EXCEPTION 'FAIL: price bar without source was accepted';
    EXCEPTION WHEN not_null_violation THEN NULL;
    END;

    -- 8. 行情資料狀態不得為 error（失敗只記在 data_fetch_log）
    BEGIN
        INSERT INTO price_bars (instrument_id, trade_date, open, high, low, close, source, fetched_at, data_status)
        VALUES (iid, DATE '2026-10-21', 100, 101, 99, 100, 'test', now(), 'error');
        RAISE EXCEPTION 'FAIL: price bar with data_status=error was accepted';
    EXCEPTION WHEN check_violation THEN NULL;
    END;

    -- 9. 有名稱的標的必須帶來源、時間與狀態
    BEGIN
        INSERT INTO instruments (market, symbol, name) VALUES ('TW', '9998', '無來源名稱');
        RAISE EXCEPTION 'FAIL: instrument name without source was accepted';
    EXCEPTION WHEN check_violation THEN NULL;
    END;

    -- 10. 失敗的抓取紀錄必須有 error_type
    BEGIN
        INSERT INTO data_fetch_log (source, status, started_at) VALUES ('test', 'error', now());
        RAISE EXCEPTION 'FAIL: error fetch log without error_type was accepted';
    EXCEPTION WHEN check_violation THEN NULL;
    END;

    -- 11. 失敗的研究執行必須有 error_type
    BEGIN
        INSERT INTO research_runs (instrument_id, status) VALUES (iid, 'failed');
        RAISE EXCEPTION 'FAIL: failed run without error_type was accepted';
    EXCEPTION WHEN check_violation THEN NULL;
    END;

    -- 12. 預測參考價必須為正
    BEGIN
        INSERT INTO predictions (run_id, instrument_id, horizon_days, verdict, reference_price,
                                 reference_price_source, reference_price_as_of)
        VALUES (rid, iid, 20, 'watch', 0, 'test', now());
        RAISE EXCEPTION 'FAIL: prediction with reference_price=0 was accepted';
    EXCEPTION WHEN check_violation THEN NULL;
    END;

    RAISE NOTICE 'constraints OK';
END
$$;

ROLLBACK;
