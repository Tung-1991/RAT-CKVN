# AUDIT BOT SAFEGUARD RAT-CKVN

Ngày rà soát: 2026-06-17

Phạm vi: `bot_daemon.py`, `signals/signal_generator.py`, `core/data_engine.py`, `core/signal_listener.py`, `core/trade_manager.py`, `core/checklist_manager.py`, `config.py`. Báo cáo này chỉ audit/đề xuất, không thay đổi logic bot/safeguard.

## 1. Luồng

```text
config.BOT_ACTIVE_SYMBOLS
  -> bot_daemon._scan_signals()
  -> data_engine.fetch_data_v4()
  -> signal_generator.generate_signal_v4()
  -> live_signals.json: pending_signals + brain_heartbeat.contexts
  -> signal_listener._process_signal()
  -> trade_manager.execute_bot_trade()
  -> checklist/safeguard + T+2/long-only + Entry/Exit + lot/SL/TP
  -> DNSEConnector.place_order/send_order

Runtime:
  trade_manager.update_running_trades()
  -> TSL/BE/BE_CASH/REV_C/watermark/basket/ATC-exit close checks
  -> _close_with_t2_log() for settlement-aware close retry

DCA/PCA:
  bot_daemon._scan_dca_pca()
  -> mini-brain optional confirmation
  -> pending DCA/PCA signals
  -> signal_listener -> trade_manager.execute_bot_trade(signal_class=DCA/PCA)
```

Đầu vào chính:
- OHLC/indicator/context từ `core/data_engine.py:281`.
- Rule/vote từng group từ `signals/signal_generator.py:154`, pipeline final tại `signals/signal_generator.py:317`.
- Pending signal và heartbeat context từ `bot_daemon.py:137`, `bot_daemon.py:324`.

Đầu ra chính:
- `BUY`/`SELL`/`NONE` entry signal vào pending queue tại `bot_daemon.py:333`, `bot_daemon.py:338`, `bot_daemon.py:349`.
- Lệnh thật/paper qua `core/trade_manager.py:563` và connector.
- Close runtime qua `core/trade_manager.py:1526`.

## 2. Bảng Rule/Safeguard Hiện Có

| Rule | Ý nghĩa | Giá trị mặc định | Nơi đọc | Nơi áp dụng |
|---|---|---:|---|---|
| `MAX_DAILY_LOSS_PERCENT` | Chặn khi lỗ ngày vượt ngưỡng | `2.5` | `config.py:195`, `core/checklist_manager.py:186`, `core/trade_manager.py:386` | `core/checklist_manager.py:239`, `core/trade_manager.py:381` |
| `MAX_OPEN_POSITIONS` | Giới hạn số vị thế bot gốc đang mở | `3` | `config.py:201`, `core/checklist_manager.py:187` | `core/checklist_manager.py:414` |
| `MAX_TRADES_PER_DAY` | Giới hạn số lệnh/ngày | `30` | `config.py:202`, `core/checklist_manager.py:188`, `core/trade_manager.py:387` | `core/checklist_manager.py:140`, `core/trade_manager.py:381` |
| `MAX_LOSING_STREAK` | Chặn khi chuỗi thua vượt ngưỡng | `3` | `config.py:203`, `core/checklist_manager.py:189`, `core/trade_manager.py:388` | `core/checklist_manager.py:120`, `core/trade_manager.py:381` |
| `GLOBAL_COOLDOWN_HOURS` | Phạt nghỉ toàn hệ thống hoặc cách ly symbol | fallback `4.0` | `core/checklist_manager.py:193`, `core/trade_manager.py:390` | `core/checklist_manager.py:239`, `core/trade_manager.py:428` |
| `COOLDOWN_MINUTES` | Cooldown entry theo symbol sau fail/entry | `1` | `config.py:205`, `bot_daemon.py:75`, `core/checklist_manager.py:427` | `bot_daemon.py:80`, `core/checklist_manager.py:421`, `core/signal_listener.py:457` |
| `CHECK_PING` / `MAX_PING_MS` | Gate chất lượng kết nối | `True` / `150` | `config.py:208`, `core/checklist_manager.py:199` | `core/checklist_manager.py:24` |
| `CHECK_SPREAD` / `MAX_SPREAD_POINTS` | Gate spread/tick bất thường | `True` / `150` | `config.py:210`, `core/checklist_manager.py:201` | `core/checklist_manager.py:24` |
| `POST_CLOSE_COOLDOWN` | Nghỉ sau close/SL để tránh re-entry ngay | `0` | `config.py:219`, `core/checklist_manager.py:501` | `core/checklist_manager.py:489` |
| `BOT_ORDER_MODE` | Bot dùng NORMAL hoặc AUTO ATO/ATC | `NORMAL` | `config.py:197` | `core/trade_manager.py:563` |
| `BOT_ATC_EXIT` | Đóng vị thế bot ở phiên ATC cuối ngày | `False` | `config.py:200` | `core/trade_manager.py:1678` |
| `BOT_RISK_PERCENT` | Risk base cho lot sizing | `0.30` | `config.py:182`, `core/trade_manager.py:770` | `core/trade_manager.py:751` |
| `BOT_BASE_SL` | Nhóm ATR/swing làm nguồn SL | `G2` | `config.py:185`, `core/trade_manager.py:1058` | `core/trade_manager.py:692` |
| `BOT_USE_TP` | Có đặt TP cho bot hay không | `True` | `config.py:216` | `core/trade_manager.py:834` |
| `BOT_TP_RR_RATIO` | TP fallback theo R | `1.5` | `config.py:183`, `config.py:217`, `core/trade_manager.py:1492` | `core/trade_manager.py:834` |
| `STRICT_MIN_LOT` | Từ chối khi lot tính ra dưới minimum | `False` | `config.py:218` | `core/trade_manager.py:783` |
| `DCA_PCA_SCAN_INTERVAL` | Chu kỳ quét DCA/PCA của daemon | `2.0s` | `config.py:213`, `bot_daemon.py:263` | `bot_daemon.py:285` |
| `DCA_PCA_COOLDOWN_SECONDS` | Khoảng nghỉ giữa các lần nhồi | `300s` | `config.py:221` | `bot_daemon.py:430`, `bot_daemon.py:473` |
| `REV_CLOSE_ON_NONE` | Cho phép NONE trigger reverse close | `False` | `config.py:223`, `core/signal_listener.py:285`, `core/trade_manager.py:2143` | `core/signal_listener.py:261`, `core/trade_manager.py:2127` |
| `REV_CONFIRM_SECONDS` | Signal đảo chiều phải giữ đủ lâu | `300s` | `config.py:224`, `core/trade_manager.py:2161` | `core/trade_manager.py:2127` |
| `REV_CONFIRM_SCANS` | Số scan đảo chiều liên tiếp tối thiểu | `2` | `config.py:225`, `core/trade_manager.py:2162` | `core/trade_manager.py:2127` |
| `REV_CLOSE_MIN_PROFIT` | Chỉ REV khi đạt lãi tối thiểu | `0.0` | `config.py:226`, `core/trade_manager.py:501`, `core/signal_listener.py:317` | `core/trade_manager.py:472`, `core/signal_listener.py:261` |
| `REV_CLOSE_MAX_LOSS` | Không REV nếu lỗ vượt ngưỡng | `0.0` | `config.py:228`, `core/trade_manager.py:508`, `core/signal_listener.py:324` | `core/trade_manager.py:472`, `core/signal_listener.py:261` |
| `MAX_BASKET_DRAWDOWN_USD` | Cắt cả rổ khi drawdown vượt ngưỡng | `0.0` | `config.py:236` | `core/trade_manager.py:1882` |
| CKCS long-only | SELL cổ phiếu chỉ bán/đóng long đã về | N/A | `core/trade_manager.py:140` | `core/trade_manager.py:595`, `core/trade_manager.py:1024` |
| T+2 close retry | Close CKCS chưa về thì treo và retry | N/A | `core/trade_manager.py:148` | `core/trade_manager.py:1632`, `core/trade_manager.py:2233`, `core/trade_manager.py:2482` |
| Entry/Exit gate | WAIT/BLOCK entry trước khi đặt lệnh | theo settings | `core/trade_manager.py:656` | `core/trade_manager.py:563` |
| Missing ATR/swing | Từ chối vào lệnh khi thiếu dữ liệu risk | N/A | `core/data_engine.py:339`, `core/data_engine.py:344` | `core/trade_manager.py:692` |
| SL too tight | Từ chối SL quá gần | N/A | `core/trade_manager.py:701` | `core/trade_manager.py:563` |
| Signal VETO/FIX/PASS/IGNORE | Quy tắc vote multi-timeframe | theo brain settings | `signals/signal_generator.py:242` | `signals/signal_generator.py:317` |

## 3. Điểm Yếu / Rủi Ro / Mâu Thuẫn

1. Cao - Một số ngưỡng risk có nhiều nguồn mặc định song song.
   - Bằng chứng: default cũ ở `config.py:74`-`config.py:78`, cấu hình mới ở `config.py:194`, đọc ở `core/checklist_manager.py:186` và `core/trade_manager.py:386`.
   - Rủi ro: nếu UI/brain settings không đồng bộ, operator có thể nghĩ bot dùng một ngưỡng nhưng runtime dùng fallback khác. Cần xác minh luồng save/load ở popup settings.

2. Cao - Cooldown có nhiều tầng, dễ khó giải thích khi bị chặn.
   - Bằng chứng: daemon cooldown signal ở `bot_daemon.py:72`, checklist symbol cooldown ở `core/checklist_manager.py:421`, global/symbol brake ở `core/checklist_manager.py:239`, listener log cooldown ở `core/signal_listener.py:219`, trade manager brake ở `core/trade_manager.py:381`.
   - Rủi ro: một signal có thể bị bỏ qua ở daemon trước khi vào listener, hoặc bị listener/trade_manager chặn sau đó. Khi audit lệnh miss, cần log reason thống nhất hơn.

3. Trung - CKCS SELL long-only chỉ kiểm có volume đã về, còn sizing chi tiết dựa vào connector chặn tiếp.
   - Bằng chứng: guard trade manager ở `core/trade_manager.py:140`; connector kiểm `available < quantity` ở `core/dnse_connector.py:828`.
   - Rủi ro: trade manager vẫn có thể tính lot lớn hơn hàng đã về và để connector trả `STOCK_NOT_SETTLED_T2`. Hành vi an toàn, nhưng UX/log có thể gây hiểu nhầm là lỗi đặt lệnh thay vì thiếu hàng đã về.

4. Trung - `REV_CLOSE_ON_NONE` được xử lý ở cả listener và trade manager.
   - Bằng chứng: listener có nhánh NONE tại `core/signal_listener.py:285`; trade manager cũng xét NONE ở `core/trade_manager.py:2143`.
   - Rủi ro: quyền sở hữu close đã có comment phân tách, nhưng vẫn cần regression test khi bật `REV_CLOSE_ON_NONE` để tránh double close hoặc log trùng.

5. Trung - Mini-brain DCA/PCA dùng context heartbeat nếu có, nếu thiếu thì fetch nhanh trực tiếp.
   - Bằng chứng: `bot_daemon.py:386`-`bot_daemon.py:388`, mini-brain fetch timeframe ở `bot_daemon.py:434` và `bot_daemon.py:482`.
   - Rủi ro: trong lúc API chập chờn, DCA/PCA có thể bị skip im lặng vì thiếu ATR/context. An toàn cho tiền, nhưng khó audit vì không có event đủ chi tiết khi skip.

6. Trung - Log từ mini-brain reject vẫn ở INFO, dù có throttle.
   - Bằng chứng: `bot_daemon.py:465`, `bot_daemon.py:512`.
   - Rủi ro: khi nhiều symbol active, file system_events vẫn có thể nhiều dòng reject định kỳ. Console đã giảm spam sau phase log, nhưng file event vẫn cần theo dõi dung lượng.

7. Thấp - Signal generator ghi lỗi indicator bằng `logger.error`.
   - Bằng chứng: `signals/signal_generator.py:202`.
   - Rủi ro: nếu một indicator lỗi liên tục theo tick, error log có thể phình. Nên cân nhắc throttle theo indicator/symbol nếu lỗi tái diễn.

8. Thấp - `MAX_BASKET_DRAWDOWN_USD` mặc định tắt.
   - Bằng chứng: `config.py:236`, áp dụng ở `core/trade_manager.py:1882`.
   - Rủi ro: người dùng có thể tưởng basket guard đang bật vì UI có option, nhưng default `0.0` là tắt. Cần UI hiển thị rõ trạng thái.

## 4. Đề Xuất Cải Tiến Ưu Tiên

1. Ưu tiên Cao - Chuẩn hóa một bảng "effective safeguard" xuất ra UI/log.
   - Lý do: giảm nhầm lẫn giữa `config.py`, global brain settings và per-symbol overrides.
   - File dự kiến: `core/storage_manager.py`, `ui_popups.py`, `core/checklist_manager.py`.

2. Ưu tiên Cao - Thêm `SAFETY_TRACE` ngắn cho mỗi signal bị block.
   - Lý do: audit missed trade sẽ dễ hơn nếu biết signal bị chặn ở daemon, listener, checklist hay trade manager.
   - File dự kiến: `bot_daemon.py`, `core/signal_listener.py`, `core/trade_manager.py`, `ai_advisor/history.py`.

3. Ưu tiên Trung - Pre-cap CKCS SELL lot theo hàng đã về trước khi gửi connector.
   - Lý do: hành vi hiện tại an toàn nhưng để connector reject; pre-cap hoặc reason rõ hơn sẽ dễ hiểu hơn.
   - File dự kiến: `core/trade_manager.py`, test trade manager CKCS.

4. Ưu tiên Trung - Throttle lỗi indicator/fetch theo symbol+rule.
   - Lý do: tránh phình log khi một indicator lỗi lặp lại.
   - File dự kiến: `signals/signal_generator.py`, `core/data_engine.py`, `bot_daemon.py`.

5. Ưu tiên Trung - Regression test riêng cho `REV_CLOSE_ON_NONE=True`.
   - Lý do: logic NONE close có điểm chạm ở listener và trade manager.
   - File dự kiến: `tests/test_signal_listener.py`, `tests/test_trade_manager_t2.py`.

6. Ưu tiên Thấp - Event hóa mini-brain skip/reject ở mức debug/structured.
   - Lý do: giữ console im nhưng advisor vẫn có dữ liệu khi cần điều tra DCA/PCA.
   - File dự kiến: `bot_daemon.py`, `ai_advisor/history.py`.
