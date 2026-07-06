# CHECKLIST SET CHIẾN LƯỢC CKCS (swing ngày) — làm theo thứ tự

> Nhãn trong ngoặc là chữ HIỆN TRÊN UI. Set ở PAPER trước, chạy vài phiên rồi mới REAL.

## 0. Chuẩn bị
- [ ] Nút **MODE** → để **PAPER** (test trước, không cần OTP).
- [ ] Dropdown thị trường → **CK Cơ Sở**.
- [ ] **⚙ ADVANCED → Cache & Mã → WATCHLIST CKCS** → nhập mã (vd `CTG,BID,MBB`) → Lưu.

## 1. ⚙ SANDBOX — INDICATOR + KHUNG + VOTING (phần cốt lõi)

### 1a. Khung thời gian ("CẤU HÌNH KHUNG THỜI GIAN")
- [ ] **G0 = 1d** · **G1 = 1h** · G2/G3 để mặc định (sẽ IGNORE, không dùng).

### 1b. Bật 4 indicator, gán group, trigger (mỗi indicator 1 dòng)
Với mỗi cái: tick **active** · tick **group** · dropdown **macro_role = NONE** · dropdown **trigger = STRICT_CLOSE** · điền param:

| Indicator | active | group | trigger | param |
|---|---|---|---|---|
| **EMA** | ✓ | **G0** | STRICT_CLOSE | period **50** |
| **MACD** | ✓ | **G0 + G1** (tick cả 2) | STRICT_CLOSE | 12 / 26 / 9 |
| **Volume** | ✓ | **G0** | STRICT_CLOSE | period 20 · mult 1.1 |
| **ADX** | ✓ | **G0** | STRICT_CLOSE | period 14 · **strong = 20** |

- [ ] **Tắt hết** indicator khác (Supertrend, RSI, BB, Stochastic, PSAR, Simple Breakout, Fibo, Pivot...).
- [ ] Bật **Swing Point** (group **G0**) — không cần vote, để nuôi SL. *(nếu ngại thì bỏ, SL vẫn tính từ swing G0.)*

### 1c. Chế độ phân xử + votes
- [ ] **"Chế độ phân xử (Master Mode)" = VETO**.
- [ ] **"Force ANY Mode (Scalping)" = BẬT** (bỏ macro, vote phẳng).
- [ ] Min Votes: kệ (chỉ dùng cho VOTING).

### 1d. Master Rule từng group ("Master Rule (VETO)")
- [ ] **G0 → FIX** · Max Opposite = 0 · Max None = **2** (≥2 indicator đồng thuận, 0 ngược).
- [ ] **G1 → PASS** · Max Opposite = 0 · Max None = 1 (H1 đừng ra ngược là OK).
- [ ] **G2 → IGNORE** · **G3 → IGNORE**.

### 1e. SL group của bot
- [ ] **"BOT BASE SL GROUP" = G0** (SL theo đáy sóng NGÀY).

## 2. ⚙ SANDBOX — E/E + SL/TP mode
- [ ] **E/E: TẮT** lần đầu — mục "1. ENTRY MODE" **không chọn tactic nào** (hoặc để preview). Bot vào theo signal, SL theo swing G0.
- [ ] "4. TP MODE" → để **RR** (TP theo R). *(E/E off thì TP lấy từ preset RR bên dưới.)*

## 3. PRESET (nút ⚙ PRESET) — vốn/risk
- [ ] **Risk Per Trade = 1.0 %** *(0.3% quá nhỏ cho SL ngày — không đủ 1 lô).*
- [ ] **Take Profit (RR) = 1.5** (hoặc 2.0).
- [ ] Stop Loss (%) = để mặc định (fallback; bot dùng swing G0 là chính).
- [ ] Manual SL Rule: Mode = **SwingPoint/Structure**, Group = **G0**.

## 4. ⚙ BOT — SAFEGUARD + kiểu lệnh
- [ ] **Lỗ tối đa/ngày = 3%** · **Vị thế mở tối đa = 3–4** · **Lệnh tối đa/ngày = 5** · **Chuỗi thua = 3** · **Cooldown = 5–10 phút**.
- [ ] **Cap %NAV/mã CKCS = 20** (đã có ô, giữ 20).
- [ ] **Kiểu khớp bot = NORMAL**.
- [ ] **Kiểu lệnh vào = LO** ← để bot đặt limit (không đuổi giá market). *(muốn chắc khớp thì để MARKET.)*
- [ ] **Ép lô tối thiểu CKCS**: tùy (bật nếu muốn vào dù lô nhỏ). Strict Min Lot: TẮT.
- [ ] **KHÔNG bật DCA/PCA** (nút DEF: DCA/PCA để tắt — không nhồi lệnh).

## 5. Panel chính — TSL (quản lệnh/exit)
- [ ] Bật các nút TSL: **BE + STEP + SWING** (BE=hòa vốn, STEP=trail theo R, SWING=trail theo sóng).
- [ ] E/E buttons (R/RETEST/STRUCT/FIB/PULL/EE): **để TẮT** (khớp với mục 2).

## 6. Test PAPER
- [ ] Bật công tắc **BOT CƠ SỞ (CKCS)** (popup ⚙BOT) — PAPER không hỏi OTP.
- [ ] Xem log: bot quét mã, ra tín hiệu khi nến ngày đóng, vào lệnh LO đúng kiểu.
- [ ] Chạy 3–5 phiên, chỉnh param nếu cần.

## 7. Đánh THẬT (khi đã tin bộ config)
- [ ] Nút **MODE → REAL** → **KHỞI ĐỘNG LẠI APP** (bắt buộc).
- [ ] **⚙ ADVANCED → Gửi OTP email → nhập mã → Xác thực** (đèn TOKEN: OK).
- [ ] Bật **BOT CƠ SỞ (CKCS)**, vào **giờ giao dịch** → bot tự đánh theo bộ trên.
- [ ] Hoặc test tay: chọn mã → 100 cp → EXECUTE BUY → kiểm danh mục + khóa T+2.

---

## Tóm cấu hình (1 chỗ nhìn)
```
INDICATOR:  EMA(50) + MACD(12/26/9) + Volume(20,1.1) + ADX(14,strong20)  [G0=D1]
            + MACD confirm [G1=H1]
VOTING:     VETO · Force ANY ON · STRICT_CLOSE · G0=FIX(none≤2) G1=PASS G2/G3=IGNORE
SL:         BOT BASE SL = G0 (swing ngày) · E/E OFF
TP:         RR 1.5–2R · TSL = BE+STEP+SWING
VỐN:        Risk 1%/lệnh · NAV cap 20%/mã · cash cap (tự) · MAX_OPEN 3-4 · trades/ngày 5
LỆNH:       Kiểu lệnh vào = LO · DCA/PCA OFF
```
```
```
