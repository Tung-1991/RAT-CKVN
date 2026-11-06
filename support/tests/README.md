# Kiểm thử CKPS

Chạy bằng `.venv\Scripts\python.exe -X utf8 -m pytest`; menu BAT mục 4 dành cho Update.
Fixture chặn HTTP/socket, tách runtime tạm. Không dùng tài khoản hay Telegram thật.

Kiểm thử quy đổi form RULE dùng đồng hồ điều khiển để không phụ thuộc tốc độ VPS.
Kịch bản vẫn cho giá quá hạn, xác nhận ARM giữ CHỜ dù đã có ký quỹ, rồi nhận giá mới
để mở khóa đúng nhóm cần quy đổi; giữ SL đang sửa và không tự lưu RULE/gửi lệnh.

`test_system_menu.py`: menu 1–6, mở app/Blackbox/Nạp preset không tự cài; Update chỉ Git pull fast-forward, xung đột/phân nhánh giữ mã local. Mọi tải/cài/chạy chương trình ngoài bị chặn hoặc giả lập.

`test_presets.py`: file preset đóng gói chỉ có RULE E/M/tín hiệu; chọn file, Hủy, validation đầy đủ, giữ tài khoản/vốn/kết nối/Telegram/sổ lệnh, khóa khi app/Blackbox mở, bản sao và rollback nếu ghi lỗi.

`test_bootstrap.py`: kiểm thử offline luồng tự chuẩn bị môi trường; dùng lại môi trường hợp lệ, máy chưa có Python, lỗi pip/kiểm tra gói, sai SHA256 và sai chữ ký dừng trước khi chạy Python/app. Mạng, giải nén và trình cài bên ngoài bị chặn hoặc thay bằng fixture trong PowerShell con.

`test_tick_exits.py`: các tick hợp lệ trong cùng lô giữ ý định SL/TP/E qua hồi giá, cùng timestamp, snapshot mới hơn, restart và lệnh đóng cũ giữ chỗ; BOT/quyền OFF không tạo ý định, bật lại không xử lý lại giao cắt khi OFF; UNKNOWN chỉ gửi một lần, tick cũ không được giá mới hợp thức hóa.

`test_app_separation.py`: Preview nhận đúng đối tượng Quote từ PaperMarket thật và xuất market-context, không gửi Telegram hoặc tạo lệnh. `test_signal_preview.py` kiểm tra lý do chờ/EMA/RSI công khai; số liệu cũ, khác mã hoặc có lỗi không được dùng và không tạo tín hiệu mới.

`test_full_protection_exits.py`: ARM/DYNAMIC Long/Short đóng toàn bộ 1/2/3/7 HĐ; cấu hình 33%/50% và LẶP cũ không chia lượt. Giữ ý định qua tick hồi cùng timestamp, lệnh đóng giữ chỗ/restart; UNKNOWN hoặc broker từ chối không POST lại, tắt nhánh dừng ý định, DYNAMIC không chờ ký quỹ chỉ vì bước LẶP không dùng.

`test_paper_sessions.py`: LO thường hết hạn cuối phiên và qua restart, tương thích bản ghi cũ; giờ nghỉ/giá đóng phiên không tạo fill, không đổi tiền/vị thế; lệnh đã nhận vẫn khớp trong ATC dù cổng gửi mở mới đang chặn.

`test_previous_close.py` / `test_quote_header_ui.py`: close đúng mã/G1/ngày, qua cuối tuần/ngày trống, cache và rollover không so nhầm, màu/điểm/% không sửa dữ liệu; GET chậm không chặn UI và bỏ phản hồi cũ. Native header vừa DPI 100–200%, không còn badge mã, hover ký quỹ chờ 500ms, hint giữ số tiền đầy đủ.

`test_scheduled_entries.py` / `test_scheduled_ticket.py`: LO xác nhận ngoài phiên lưu local, gửi theo đúng mã/giá/HĐ, sống qua restart; giữ chỗ/FIFO, hủy local, đổi vé phải xác nhận lại; phiên/ngày nghỉ/ATO/ATC, OTP REAL, giá cũ, hủy/đóng app trong GET, timeout không gửi lại; quá phiên/rollover hết hiệu lực, PAPER không khớp cache. Runtime và UI xác nhận/bảng/hủy chạy trên các đường thật, không gửi mạng.

`test_dashboard_refresh.py`: gộp snapshot chờ thành một lượt hiển thị mới nhất; dữ liệu không đổi không vẽ lại widget, giá thay đổi và giá cũ vẫn cập nhật ngay, không cấp quyền lệnh từ giá cũ.

`test_unified_price_rules.py`: SL/TP/ARM cùng % giá vào; quy đổi RULE PNL cũ giữ nguyên mốc Long/Short và trạng thái vị thế. Thiếu cơ sở giữ nguyên nhóm nguồn; ARM mới và Preview % giá/điểm/tiền không cần ký quỹ, DYNAMIC giữ công thức ATR.

`test_pnl_trailing.py`: tương thích ARM theo ký quỹ cơ sở/HĐ cũ; quy đổi từng nhóm không sửa nguồn/đổi nhãn số cũ, preset mới không chờ dữ liệu, Preview % giá/điểm/tiền và HĐ còn giữ; Long/Short, đóng toàn bộ 4 HĐ, vào thêm, nạp tiền, restart và thiếu ký quỹ không vô hiệu SL/TP. Dữ liệu LẶP cũ vẫn đọc được.

`test_preview_analysis.py`: Preview chỉ đọc tự chạy, Telegram luôn OFF; tham chiếu đóng phiên tự tính từ nến thật kể cả chưa có cache backend, dùng cho bản nháp RULE nhưng không làm giá mới/cấp LONG hoặc quyền giao dịch.

`test_connection_state.py`: DPAPI Windows cho API/phiên giao dịch và Bot token riêng; token không plaintext, đọc được sau restart tiến trình, đổi/quên DNSE không xóa Telegram; xóa token rồi LƯU không ảnh hưởng API. Mở lại form che token và không tự chạy backend.

`test_execution_safety.py`: SL/E với lệnh đóng đang chờ, khớp trong lúc hủy, timeout,
restart/BOT OFF, giữ chỗ, quyền quản lý và khối lượng broker bị thay đổi.
`test_stream_safety.py`: tick cũ/thiếu thời gian/tương lai/lùi thứ tự không làm sai MFE hoặc tự đóng ARM.
`test_ema_exit.py`: E EMA3/6 Long/Short, REALTIME/CLOSED, nhịp phút, dữ liệu thiếu/cũ/khác mã,
đóng toàn bộ đúng quyền và không phụ thuộc ALERT/Telegram.
`test_runtime_safety.py`: snapshot tài khoản chậm không trì hoãn BOT OFF hoặc gây gửi lệnh muộn sau khi đã tắt BOT.
`test_rule_controls.py`: TP % giá Long/Short với lệnh chờ, chu kỳ/chế độ/nhịp E độc lập,
chặn tham số lỗi, form lưu đủ E/TP và bộ lọc lịch sử không sửa dữ liệu gốc hoặc gửi lệnh.
`test_mode_switch.py`: PAPER/REAL không mở cửa sổ, xác minh trước khi đổi sổ,
thiếu/multiple/lỗi API giữ sổ cũ, đổi ý/API bỏ phản hồi cũ, sổ mới BOT OFF.

| File | Phạm vi |
| --- | --- |
| `test_default_rules.py` | Tự nạp preset duy nhất khi mở app chưa lưu E/M, giữ cấu hình đã sửa/kể cả OFF; Long/Short SL/ARM/DYNAMIC đóng toàn bộ, TP OFF; không tự bật BOT/Telegram hoặc nhận vị thế DNSE |
| `test_shared_rules.py` | Một RULE áp dụng hợp đồng đang giữ/chờ/mới, bỏ qua dữ liệu riêng cũ; đổi SL, fill muộn, restart giữ mốc; TP OFF; cấu hình cũ ALERT/ORIGINAL/tỷ lệ khác vẫn tự đóng toàn bộ số còn lại sau giảm tay, không tự bật nhánh đã tắt |
| `test_trade_notifications.py` | Biên nhận Long/Short SL/ARM/DYNAMIC, đóng từng phần, đúng thứ tự gửi/khớp, phí muộn không báo trùng; UNKNOWN/fill muộn, hủy chờ xác nhận, transaction rollback; tắt/restart không gửi bù; Telegram mất mạng/429 và trạng thái chờ DNSE |
| `test_ticket_estimates.py` | Giá/khối lượng lỗi xóa số ước tính cũ, TP OFF vẫn rõ; AUTO 0/thiếu sức mở hiển thị SL/phí theo 1 HĐ, không cấp sức mở; phí ước, thiếu và 0 phân biệt rõ |
| `test_protection.py` | SL/TP, ARM/DYNAMIC, Long/Short, bước lặp và HĐ nguyên |
| `test_execution.py` | Lệnh tay, fill tích lũy, timeout, đối soát, quản lý riêng; thoát toàn bộ qua gap/hồi giá, handoff, khớp từng phần và restart |
| `test_capital.py` | Sức mở/ký quỹ tự lấy từ broker, giữ chỗ lệnh local không trừ hai lần, kiểm tra lại trước gửi; SL chỉ ước tính lỗ, không thêm hạn mức; chỉnh vốn PAPER giữ lãi/phí/lịch sử, chặn giảm dưới ký quỹ và tách REAL |
| `test_broker_contract.py` | Chuẩn DNSE, native close, kiểm tra quyền trước POST |
| `test_stream_and_runtime.py` | Tick, ATR, restart, một kênh Telegram; PAPER giá DNSE/tiền ảo, áp dụng/lưu vốn, chặn giá thiếu/cũ/sai mã và API tài khoản/giao dịch, tải nến không chặn SL |
| `test_signals.py` | MA200, VA/X phiên, fill/restart, nhịp phút, bộ lọc, GET-only và lịch sử tín hiệu |
| `test_ui.py` | Hai tab Preview/Log, mốc E/M chỉ đọc, một form RULE chung MayinTien, không scope/kế thừa/ghi đè trên vé; TP OFF, quy đổi RULE chung cũ sang % giá từ dữ liệu đã xác minh, nhập SL âm/thập phân, chặn thiếu cơ sở/ngưỡng lỗi; DNSE/VỐN/Telegram/LỊCH, ba nhóm thông báo, DPI 100–200%, bảng/lịch sử |
| `test_account_preview.py` | GET-only đọc tài khoản CKPS ACTIVE, chọn gói đúng tài khoản, không chọn bừa khi nhiều kết quả, chặn gói CKCS/trùng ID; phí cố định 0 khác thiếu; bậc thang hợp lệ ước mức cao nhất, chặn biểu lỗi/trùng/hở; PAPER trừ phí mở/đóng, REAL dùng phí API; worker bỏ phản hồi cũ |
| `test_price_rules.py` | RULE mới dùng % giá vốn; Preview/hint cùng đơn vị; tương thích bản ghi cũ. Công thức Long/Short, 0,25% khác 2,5%, độc lập ký quỹ; bỏ qua policy riêng/vé cũ, đổi từ PNL giữ mốc lặp; vào thêm/giảm/restart |
| `test_pnl_rules.py` | Tương thích cấu hình % PNL cũ trên ký quỹ cơ sở, Long/Short SL/TP/ARM/DYNAMIC/LẶP; giảm lệnh không đổi tỷ lệ, vào thêm bình quân theo fill, restart không đổi cơ sở; thiếu ký quỹ không dựng ngưỡng, đóng tay vẫn được; quy đổi E/M cũ, bỏ hạn mức tài khoản cũ khi nạp/lưu |
| `test_connection_state.py` | DPAPI thực trên Windows, không lưu passcode, phiên ràng buộc API/tài khoản/hạn dùng; từ chối auth xóa phiên; khôi phục vẫn BOT OFF; snapshot không có secrets; cache giá chỉ xem, không tạo tín hiệu |
| `test_settings.py` | RULE chỉ E/M; Blackbox chỉ chứa RULE tín hiệu (không API/kết nối/Telegram/CHẠY), một E/M chung, KẾT NỐI hai tab cùng kích thước; xác nhận quyền BOT độc lập thông số, Blackbox lưu EMA/RSI, KẾT NỐI lưu Telegram/lịch; pipe backend không nhận tài khoản/OTP/lệnh; token ngoài argv; tắt thông báo không phát lại; DPI và trường cuộn tới được |
| `test_app_separation.py` | Backend không có quyền giao dịch; hai app chạy cùng lúc với sổ/cấu hình riêng; chống phát lại qua restart |
| `test_market_alerts.py` | MA200, biến động VN30, thông báo độc lập, chống trùng và Telegram không chặn E/M |
| `test_semi_auto.py` | Số tiền lỗi, sức mở theo giá vé, fill mâu thuẫn, hủy lệnh mở dư, ARM/LẶP Long/Short, nhắc đáo hạn và biên nhận Telegram |

`test_calendar.py`: ngày nghỉ/đáo hạn/đổi rổ, cache thiếu và lỗi, nhắc trước/chống trùng; đáo hạn không chặn,
chặn mở mới cả Long/Short tới handoff, vẫn cho đóng tay và SL tự động.
