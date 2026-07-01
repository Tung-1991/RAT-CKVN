# PLAN: Tách luồng SETTING chiến lược CKCS vs CKPS (chạy 2 bot song song)

> Handoff cho chat mới. Đọc file này → vào plan mode → làm. Mục tiêu: bật 2 bot (Phái sinh + Cơ sở)
> CÙNG LÚC, mỗi nhóm đánh đúng khung/SL/risk của nó, KHÔNG đá nhau.

## 1. Vấn đề (vì sao cần)
Hiện **timeframe (G0–G3), SL mode/group, risk%** là **GLOBAL** trong `brain_settings.json` — mọi mã dùng chung.
- Để 15m (cho phái sinh) → bot CKCS cũng quét 15m → SAI (cổ phiếu T+2 phải đánh NGÀY).
- Để ngày (cho CKCS) → phái sinh đánh ngày → quá chậm.
→ Bật 2 bot cùng lúc = 1 nhóm trade trên khung/SL sai → lệnh rác. KHÔNG crash, nhưng đánh hỏng.

**Đích:** CKCS = khung NGÀY (G0) + SL swing + risk riêng (vd 1%); CKPS = 15m (G2) + SL tight + risk 0.3%.

## 2. Kiến trúc hiện tại (đã verify)
- **Merge settings theo mã:** `core/storage_manager.py` → `get_brain_settings_for_symbol(symbol)` merge
  3 lớp: `config.py` (mặc định) → `brain_settings.json` (chung) → `symbol_overrides.json` (riêng từng mã).
  Bot/data_engine/signal_generator đều gọi hàm này → nếu thêm lớp override CKCS ở ĐÂY, mọi nơi tự ăn.
- **Gate 2 bot ĐÃ XONG (symbol-aware):** `core/signal_listener.py::_auto_trade_for(symbol)` dùng
  `settlement.is_cash_stock(symbol)` → cờ `var_bot_ckps`/`var_bot_ckcs` (main.py). 2 công tắc + 2 đèn đã có.
- **ĐÃ CKCS-specific rồi (ĐỪNG làm lại):** NAV cap + cash cap (`STOCK_MAX_ORDER_NAV_PCT`), FORCE_MIN_LOT,
  lô 100/biên giá (`core/stock_rules.py`), T+2 (`core/settlement.py`), tất cả gate bằng `is_cash_stock()`.
- **Các key chiến lược GLOBAL cần tách:**
  - Timeframe: `G0_TIMEFRAME`(1d)/`G1`(1h)/`G2`(15m)/`G3`(15m) — `storage_manager` defaults ~dòng 870.
  - SL: `BOT_BASE_SL` (default "G2"=15m), `risk_tsl.base_sl`, SL mode (swing/percent/fib).
  - Risk: `BOT_RISK_PERCENT` (0.3), `risk_tsl.base_risk`, `mode_multipliers`.
  - TSL: `BOT_DEFAULT_TSL`. Entry/Exit: `entry_exit` config. Indicators: `indicators`/`indicator_groups` nếu muốn khác.

## 3. Thiết kế (CHỐT — override nhỏ additive, KHÔNG flip, KHÔNG 2 bộ đầy đủ)

**QUYẾT ĐỊNH (đã bàn với user):**
- **KHÔNG flip** global sang CKCS (flip = đụng cái luồng phái sinh đang đọc → rủi ro). Global GIỮ NGUYÊN = baseline phái sinh.
- **KHÔNG** làm 2 bộ config đầy đủ (over-engineer). CKCS chỉ khác phái sinh ở **timeframe + SL + risk** — phần còn lại (safeguard, lô, T+2, cap...) DÙNG CHUNG.
- Chỉ **thêm 1 khối `ckcs_overrides`** đè lên khi `is_cash_stock(symbol)`. Additive → luồng phái sinh KHÔNG đụng tới = an toàn nhất.

**3 lớp merge (rộng→hẹp, lớp sau đè lớp trước):**
```
1. config.py + brain global   (= baseline phái sinh, GIỮ NGUYÊN)
2. ckcs_overrides             ← áp cho MỌI cổ phiếu khi is_cash_stock (khung ngày G0 + SL swing + risk ~1%)
3. symbol_overrides[mã]       ← ĐÃ CÓ SẴN (nút ⚙ từng mã) — đè lên cả lớp CKCS
```
Thứ tự trong `get_brain_settings_for_symbol(symbol)`: config → brain(global) → **ckcs_overrides (nếu CKCS)** → symbol_overrides(mã).

→ CKCS chỉ override **3 nhóm key**: timeframe (G0-G3), SL (BOT_BASE_SL/risk_tsl.base_sl/SL mode), risk (BOT_RISK_PERCENT/risk_tsl.base_risk). Per-symbol vẫn đè được lên trên (linh hoạt mọi cấp, không phải làm gì thêm — symbol_overrides đã chạy).

**CHƯA cần làm ngay:** chỉ cần khi chạy 2 bot SONG SONG. Chạy 1 bot/lần (tắt cái kia) thì không cần. User mai chỉ đánh CKCS (phái sinh chưa đủ ký quỹ) → KHÔNG đụng vụ tách.

## 4. Cần làm
1. **storage_manager.py**: trong `get_brain_settings_for_symbol`, thêm bước áp `ckcs_overrides` khi is_cash_stock.
   Dùng deep-merge sẵn có (kiểm hàm merge dict trong file; nếu chưa có, viết helper thuần). Cache theo symbol vẫn ok.
2. **config.py**: thêm `CKCS_STRATEGY_DEFAULTS` (timeframe G0 trọng tâm, SL swing, risk 1%) làm seed cho ckcs_overrides.
3. **UI**: 1 chỗ chỉnh `ckcs_overrides` — đề xuất: trong popup ⚙BOT thêm **tab/khung "CHIẾN LƯỢC CKCS"**
   (timeframe, SL mode/group, risk%). Lưu vào `brain_settings.ckcs_overrides`. (Hoặc tách 2 tab CKPS/CKCS như user nói.)
   ⚠️ Theo memory: KHÔNG di chuyển widget trong layout `.pack()` dày — thêm khung/tab mới, đừng phá cái cũ.
4. **(tùy)** Daemon ghi active_symbols tách nhóm để 2 đèn phản ánh đúng (đã descope trước, làm nếu cần).

## 5. Bẫy / lưu ý
- **KHÔNG đụng luồng phái sinh** (đang chạy ổn): chỉ thêm nhánh khi is_cash_stock. Phái sinh không có ckcs_overrides → y nguyên.
- **Cache settings** (`storage_manager` có cache theo symbol/TTL) — đảm bảo invalidate khi lưu ckcs_overrides.
- **Đừng làm lại** mấy thứ CKCS đã có (NAV/cash cap, lô, T+2) — chỉ thêm TIMEFRAME/SL/RISK.
- Test trước: bật cả 2 bot, mã VN30F1M ăn G2/15m, mã FPT ăn G0/1d — xác nhận `get_brain_settings_for_symbol("FPT")`
  trả timeframe/SL khác `get_brain_settings_for_symbol("VN30F1M")`.

## 6. Verification
- Unit test mới (tests/): `get_brain_settings_for_symbol("FPT")` (với ckcs_overrides set) trả G0/risk-CKCS;
  `get_brain_settings_for_symbol("VN30F1M")` trả global (G2). Phái sinh KHÔNG bị ckcs_overrides ảnh hưởng.
- `./ckvnvenv/Scripts/python.exe -m pytest -q` — giữ pass (hiện 195).
- Chạy app: bật 2 bot, xem log scan — CKCS quét khung ngày, CKPS quét 15m, không lẫn.

## 7. Trạng thái nền (đã xong, để chat mới biết)
2 bot tách (công tắc+đèn+gate), dropdown NORMAL/ATO/ATC, NAV cap + cash cap CKCS, lô lẻ, danh mục đúng
nghiệp vụ (NAV−nợ, sức mua, cổ tức), cache 24/7 + 429, paper bỏ OTP, token đúng connector, auto-apply REAL,
persist token (opt-in). 195 test pass. CHƯA khớp lệnh thật lần nào (cần test mua 1 lô bank thật).
