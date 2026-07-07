# AUDIT INDICATOR: Exness (Forex/MT5) → CKVN (DNSE)

> Ngày audit: 2026-07-07. Phạm vi: `signals/*.py`, `core/data_engine.py` (`_apply_ta`, `_fetch_bars`, `_calc_atr`, `fetch_data_v4`).
> **Chỉ báo cáo + đề xuất — CHƯA sửa bất kỳ logic nào.** Mỗi finding bàn xong mới sửa, từng cái một (lego).

## Tóm tắt nhanh

| # | Vị trí | Vấn đề | Mức độ | Sửa ngay? |
|---|--------|--------|--------|-----------|
| 1 | `data_engine.py:189-193` | Cửa sổ thời gian fetch nến giả định thị trường 24h như forex → khung 1H/15m có thể **thiếu nến trầm trọng** → EMA50/SMA20 ra NaN → signal câm lặng trả 0 | 🔴 CAO | Cần xác minh runtime trước |
| 2 | `signals/volume.py` | Nến đang hình thành: volume mới chạy một phần phiên nhưng đem so SMA20 của nến đủ → khung D1 trong phiên gần như không bao giờ nổ tín hiệu | 🔴 CAO (với CKCS) | Bàn phương án |
| 3 | `signals/simple_breakout.py:16`, `signals/swing_point.py:24` | Fallback ATR `0.0005` là scale pip forex — vô nghĩa với giá CKVN | 🟡 TRUNG | Dễ, sửa sau khi duyệt |
| 4 | `data_engine.py:195-229` | Nến D1 bị cache bucket "đóng băng" trong phiên → indicator khung 1d chỉ tươi 1 lần/ngày | 🟡 TRUNG | Không phải bug — cần ghi rõ độ tươi vào dữ liệu lưu |
| 5 | RSI/Stochastic/Bollinger (mean-reversion) | Mua khi quá bán ổn ở forex (thoát lệnh tức thì); ở CKCS dính **T+2 + biên độ trần/sàn** → bắt dao rơi không thoát được | 🟡 TRUNG | Caveat vận hành, tune per-symbol |
| 6 | Candle patterns + khung intraday | Nến ATO/ATC là nến 1 giá; nghỉ trưa tạo khoảng trống chuỗi nến — forex 24h không có | 🟢 THẤP | Ghi nhận, chưa cần sửa |
| 7 | `data_engine.py:275` | `_calc_atr` trả `0.0001` tuyệt đối khi df rỗng — scale forex (các fallback khác đã theo % giá, ổn) | 🟢 THẤP | Nhánh chết, gần như không chạy tới |

---

## Finding 1 — Cửa sổ fetch nến giả định thị trường 24h 🔴

**Code** (`core/data_engine.py:189-193`):

```python
seconds_per_bar = multiplier_map.get(str(res).lower(), 900)
to_ts = int(time.time())
from_ts = to_ts - (num_bars * seconds_per_bar)
```

**Giả định gốc (Exness):** forex chạy 24/5 → lùi `100 nến × 3600s` là lấy được ~100 nến 1H thật.

**Thực tế CKVN:** phiên chỉ ~4.5–5.5h/ngày. Với `NUM_H1_BARS=100`, khung 1H lùi 100 giờ ≈ 4.2 ngày lịch → chỉ chứa **~20–25 nến 1H thật**. Hệ quả dây chuyền:

- `df.ta.ema(50)` với ~22 dòng → cột toàn NaN → `ema.py` đọc `iloc[-1]` = NaN → mọi so sánh False → **trả 0 im lặng, không lỗi, không log**.
- `volume.py` cần `len(df) >= 20` — thoát sớm hoặc SMA20 tính trên mẫu quá mỏng.
- Khung 15m: 100 × 900s ≈ 1 ngày lịch → ~18–22 nến/ngày giao dịch, tạm đủ cho period nhỏ nhưng hụt với EMA50.
- Khung 1d: 100 ngày lịch ≈ ~68 phiên → đủ cho SMA20, sát nút cho EMA50.

**Ảnh hưởng:** các indicator period dài trên khung 1H/15m có thể đang **chết im lặng cả với bot phái sinh hiện tại** chứ không riêng CKCS.

**Đề xuất (để bàn):**
1. Bước chẩn đoán trước (không đổi logic): log `len(df)` từng khung mỗi lần fetch để xác nhận số nến thật nhận về (DNSE có thể tự trả thêm nến ngoài window — phải đo mới biết).
2. Nếu xác nhận thiếu: nhân cửa sổ với hệ số phủ phiên cho khung intraday (`24h / ~5h ≈ ×4.5`) và hệ số lịch/phiên cho khung 1d (`×1.5` cho cuối tuần + nghỉ lễ). Chỉ đổi `from_ts`, không đổi gì khác.

## Finding 2 — Volume nến đang hình thành 🔴 (quan trọng nhất với CKCS)

**Code** (`signals/volume.py:12-16`): so `volume` nến hiện tại với `SMA20(volume) × multiplier (1.1)`.

**Giả định gốc (Exness):** volume là **tick volume** (số lần giá nhảy) — vốn đã ít ý nghĩa, so lệch cũng không ai để ý.

**Thực tế CKVN/DNSE:** cột `v` từ `/price/ohlc` (`data_engine.py:259`) là **volume khớp lệnh thật** — về bản chất tín hiệu này giờ *giá trị hơn hẳn* thời Exness (TT VN cực nhạy volume). NHƯNG:

- Trong phiên, nến D1 hiện tại mới tích được một phần volume của ngày → so với SMA20 của các nến **đủ ngày** → gần như không bao giờ vượt `×1.1` trước 14h → tín hiệu volume trên khung D1 **chỉ có thể nổ lúc cuối phiên hoặc không bao giờ**.
- Cộng hưởng Finding 4: nến D1 bị đóng băng cache trong phiên → con số volume intraday còn cũ hơn nữa.

**Đề xuất (để bàn, chọn 1):**
- **(a)** Pro-rate theo thời gian phiên đã trôi: `volume_dự_kiến = volume_hiện_tại / tỷ_lệ_phiên_đã_qua` rồi mới so SMA20 — nhạy sớm, đúng tinh thần "volume đột biến", nhưng nhiễu đầu phiên (ATO).
- **(b)** Chỉ đánh giá trên nến đã đóng (`iloc[-2]`) — sạch tuyệt đối, nhưng tín hiệu trễ 1 nến (D1 = trễ 1 ngày).
- **(c)** Giữ nguyên logic bot; riêng **kho lưu trữ snapshot** (Phần B) lưu kèm cờ `is_partial_bar` + volume pro-rate để AI advisor tự cân — không đụng logic signal. ← ít rủi ro nhất, làm trước được ngay.

## Finding 3 — Fallback ATR `0.0005` scale pip forex 🟡

**Code:** `signals/simple_breakout.py:16` và `signals/swing_point.py:24`:

```python
current_atr = context.get("atr_G2", 0.0005) if context else 0.0005
```

**Giả định gốc:** 0.0005 = 5 pip EURUSD — "mức mặc định an toàn" của forex.

**Thực tế CKVN:** giá CKPS ~1300 điểm (ATR thật cỡ 5–15), CKCS ~10–100 nghìn (ATR thật cỡ 0.2–2). Fallback 0.0005 ≈ **số 0**:
- `simple_breakout`: buffer ≈ 0 → thành breakout không đệm (thoái hóa nhẹ, không sai hướng).
- `swing_point`: vùng dung sai chạm hỗ trợ/kháng cự ≈ 0 → tín hiệu **gần như chết** khi rơi vào nhánh fallback.

**Giảm nhẹ:** daemon luôn truyền context có `atr_G2` thật (`fetch_data_v4` luôn tính) → nhánh fallback hiếm khi chạy. Nhưng là mìn chờ nổ khi module được gọi ở chỗ khác.

**Đề xuất:** đổi fallback thành tương đối theo giá: `df['close'].iloc[-1] * 0.001`, hoặc trả 0 (bỏ đệm) + log warning. Một dòng mỗi file.

## Finding 4 — Nến D1 đóng băng trong phiên 🟡

**Code** (`data_engine.py:195-229`): `effective_cache_ttl = max(TTL, seconds_per_bar)` + bucket theo `to_ts // seconds_per_bar` → nến 1d chỉ fetch lại khi sang bucket ngày mới hoặc sau khi đóng cửa (bucket = -1).

**Hệ quả:** mọi indicator khung 1d trong phiên là số của lần fetch đầu ngày; giá live phải lấy từ `current_price` (G2). Sau đóng cửa, fetch đầu tiên tự lấy số chốt phiên gồm ATC — **lượt ghi cuối ngày tự nhiên có số final, không cần hack**.

**Đề xuất:** không sửa cache (đang là tối ưu đúng). Kho snapshot phải lưu `is_partial_bar`/độ tươi + báo cáo gửi AI ghi rõ "số intraday là ước tính, số EOD là final".

## Finding 5 — Mean-reversion vs T+2 + biên độ trần/sàn 🟡

`rsi.py` (mua khi ≤30), `stochastic.py` (giao cắt vùng 20/80), `bollinger_bands.py` (chạm band dưới → mua) — chuẩn sách giáo khoa, ổn ở forex vì thoát lệnh tức thì.

Đặc thù CKCS: **T+2** (mua xong 2.5 ngày mới bán được) + **biên độ ±7% HOSE / ±10% HNX**: cổ phiếu sàn nhiều phiên liên tiếp thì RSI ghim đáy suốt — tín hiệu mua bắn liên tục trong khi dao vẫn đang rơi và không có cửa thoát. Ngược lại cổ phiếu trần thì RSI ghim 90+ bắn SELL (với CKCS không short được — tín hiệu SELL chỉ có nghĩa "chốt nếu đang giữ").

**Đề xuất:** không sửa code (logic indicator không sai). Xử lý bằng: (1) brain settings per-symbol cho nhóm CKCS (đúng task "tách CKPS/CKCS" đang pending), (2) prompt advisor dặn AI: tín hiệu mean-reversion ở CKCS phải đối chiếu thanh khoản + trạng thái trần/sàn trước khi khuyến nghị.

## Finding 6 — Nến ATO/ATC và nghỉ trưa 🟢

Nến phiên khớp lệnh định kỳ (ATO 9h00, ATC 14h30-14h45) là nến 1 giá (body ≈ 0, không bóng) → các pattern Hammer/ShootingStar (`_apply_ta:174-175` đòi bóng > 2×body) dễ nhiễu quanh các mốc này trên khung intraday. Nghỉ trưa 11h30-13h00 làm chuỗi nến intraday có "khoảng trống" mà rolling/EMA coi là liền mạch — forex 24h không có hiện tượng này. Khung D1 không ảnh hưởng.

**Đề xuất:** ghi nhận, chưa sửa. Nếu sau này cần: bỏ qua nến ATO/ATC khi xét pattern.

## Finding 7 — `_calc_atr` trả `0.0001` khi df rỗng 🟢

`data_engine.py:275`: hằng số tuyệt đối scale forex. Nhánh gần như chết vì `fetch_data_v4` đã abort khi df rỗng (dòng 323-324). Các fallback còn lại của `_calc_atr`/`_calc_swings` đã tính theo % giá (`price × 0.0005`, `±0.1%`) — scale-independent, **ổn**.

**Đề xuất:** sửa cùng lượt với Finding 3 cho sạch, không gấp.

---

## Những thứ đã rà và KHÔNG có vấn đề

- `adx.py`, `macd.py`, `ema.py`, `ema_cross.py`, `supertrend.py`, `psar.py`: thuần so sánh tương đối/cắt nhau, không phụ thuộc scale giá hay giờ phiên.
- `atr.py` (filter): so ATR khung hiện tại với ATR G1 × multiplier — cùng đơn vị, tự cân scale.
- `fibonacci.py`: tolerance 0.1% **tương đối theo giá** — scale-independent, ổn.
- `pivot_points` (`_apply_ta:150-157`): tính từ nến trước cùng khung — trên D1 đúng chuẩn floor pivot; trên intraday là "rolling pivot" (khác sách nhưng hành vi giữ nguyên từ Exness, không phải regression).
- `_calc_atr`/`_calc_swings` fallback theo % giá: ổn.
- Volume DNSE là volume khớp thật (`data['v']`) — nâng cấp so với tick volume Exness, nền tảng tốt cho phân tích volume của advisor.

## Đề xuất thứ tự xử lý (sau khi mày duyệt)

1. **Không chặn gì cả** → Phần B (kho snapshot) làm ngay theo Finding 2(c) + 4: lưu `is_partial_bar` + volume pro-rate tham khảo, logic signal giữ nguyên 100%.
2. Finding 1: thêm log chẩn đoán số nến/khung → chạy 1 phiên → có số thật rồi quyết có nhân hệ số cửa sổ không.
3. Finding 3 (+7): sửa fallback — mỗi file 1 dòng, an toàn.
4. Finding 2 (a/b): chỉ khi mày muốn tín hiệu volume của **bot** nhạy hơn; còn advisor thì 2(c) đã đủ.
5. Finding 5: gộp vào task "tách CKPS/CKCS" đang pending.
