# Kiểm thử CKPS

Chạy bằng `START_SYSTEM.bat → 5` hoặc `.venv\Scripts\python.exe -X utf8 -m pytest`.
Fixture chặn HTTP/socket, tách runtime tạm. Không dùng tài khoản hay Telegram thật.

| File | Phạm vi |
| --- | --- |
| `test_protection.py` | SL/TP, ARM/DYNAMIC, Long/Short, bước lặp và HĐ nguyên |
| `test_execution.py` | Lệnh tay, fill tích lũy, timeout, đối soát, quản lý riêng; mốc LẶP qua gap/hồi giá, handoff, khớp từng phần và restart |
| `test_capital.py` | Ký quỹ, HĐ tối đa, ngân sách rủi ro; chỉnh vốn PAPER giữ lãi/phí/lịch sử, chặn giảm dưới ký quỹ và tách REAL |
| `test_broker_contract.py` | Chuẩn DNSE, native close, kiểm tra quyền trước POST |
| `test_stream_and_runtime.py` | Tick, ATR, restart, một kênh Telegram; PAPER giá DNSE/tiền ảo, áp dụng/lưu vốn, chặn giá thiếu/cũ/sai mã và API tài khoản/giao dịch, tải nến không chặn SL |
| `test_signals.py` | MA200, VA/X phiên, fill/restart, nhịp phút, bộ lọc, GET-only và lịch sử tín hiệu |
| `test_ui.py` | Hai tab Preview/Log, mốc E/M chỉ đọc, RULE và bảo vệ riêng dùng chung form/hint MayinTien; quy đổi đơn vị đúng mã vị thế, chặn giá thiếu/cũ/sai mã và ngưỡng lỗi; KẾT NỐI DNSE/VỐN/Telegram/LỊCH, backend ba công tắc, Long mẫu, DPI 100–200% và khung 1080×700; cột/màu Long/Short/PnL, chọn dòng bằng chuột/phím, lịch sử và cuộn nhiều dòng |
| `test_settings.py` | RULE hai tab, KẾT NỐI ba tab cùng kích thước, phạm vi chung/vị thế, xác nhận quyền quản lý, lưu EMA/RSI và Telegram/lịch độc lập; pipe backend không nhận tài khoản/OTP/lệnh; token ngoài argv; cổng Vào lệnh OFF vẫn theo dõi, không phát lại; DPI và mọi trường cuộn tới được |
| `test_app_separation.py` | Backend không có quyền giao dịch; hai app chạy cùng lúc với sổ/cấu hình riêng; chống phát lại qua restart; Long mẫu không ghi sổ |
| `test_market_alerts.py` | MA200, biến động VN30, thông báo độc lập, chống trùng và Telegram không chặn E/M |
| `test_semi_auto.py` | Số tiền lỗi, sức mở theo giá vé, fill mâu thuẫn, hủy lệnh mở dư, ARM/LẶP Long/Short, nhắc đáo hạn và biên nhận Telegram |

`test_calendar.py`: ngày nghỉ/đáo hạn/đổi rổ, cache thiếu và lỗi, nhắc trước/chống trùng; đáo hạn không chặn,
chặn mở mới cả Long/Short tới handoff, vẫn cho đóng tay và SL tự động.
