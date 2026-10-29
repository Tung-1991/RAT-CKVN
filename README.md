# RAT VN30 · Semi-auto

- `main.py`: vào Long/Short bằng tay, quản lý SL/TP và TSL/PROTECT.
- `backend.py`: chạy backend console bằng biến môi trường; thường dùng CHẠY/DỪNG ngay trong KẾT NỐI.
- `START_SYSTEM.bat`: mở app, backend, preview mẫu hoặc kiểm thử offline.

MAIN hiển thị ký quỹ lớn và tổng tiền nhỏ bên dưới; AUTO tính HĐ theo sức mở, không tự trích dự phòng. Cài đặt tập trung vào RULE (một E/M chung, TÍN HIỆU) và KẾT NỐI (DNSE / VỐN, TELEGRAM / LỊCH), hai cửa sổ cùng kích thước. DNSE / VỐN có ĐỌC API để chọn tài khoản/gói và xem ký quỹ/phí từ DNSE, dùng chung một cặp key/secret, có OTP và tùy chọn ghi nhớ kết nối bằng mã hóa Windows; không lưu mã OTP dùng một lần. Giá lưu gần nhất có thời gian và nhãn CŨ, chỉ để xem. Chọn dòng hợp đồng rồi mở RULE → E/M để nhận/bỏ quyền BOT. BOT OFF khi khởi động. Preview có hai kết quả ĐIỂM VÀO và THỊ TRƯỜNG UP/DOWN cùng trạng thái OTP; giấu thông số chỉ báo, chỉ hiện bảo vệ khi chọn vị thế. Bảng chính ẩn PNL. Telegram chỉ thông báo, không mở/đóng lệnh. Đáo hạn chỉ nhắc trước.

E/M chỉ nhập % giá vốn bình quân hợp đồng, không tính trên ký quỹ hoặc NAV và không chọn đơn vị. Một RULE chung áp dụng cho toàn bộ hợp đồng đang giữ, lệnh chờ và lệnh mới; không MẶC ĐỊNH / VỊ THẾ, không kế thừa hay ghi đè SL/TP trên vé. TP cố định OFF. App chưa lưu RULE tự nạp SL 0,5%, ARM 1%, TSL/LẶP 0,25%, đóng 50% HĐ còn lại; DYNAMIC ATR/giữ lãi và LẶP ON. Các ngưỡng chung đã lưu được giữ nguyên, dữ liệu E/M riêng cũ bị bỏ qua, BOT vẫn OFF khi mở. Cấu hình điểm/% PNL chung cũ chỉ quy đổi khi LƯU RULE, thiếu cơ sở thì CHỜ. Hướng dẫn ở hint; lịch ngày nghỉ tự động, ngày riêng thu gọn.

TSL/ARM và DYNAMIC tự đóng 50% HĐ còn lại mỗi lượt khi BOT và quyền quản lý ON. Không có lựa chọn AUTO/ALERT, GỐC/CÒN LẠI hay nhập tỷ lệ đóng trong E/M. Cấu hình cũ cũng dùng các lựa chọn cố định này; các ngưỡng và cờ bật/tắt nhánh được giữ. Một HĐ còn lại thì đóng một; LẶP vẫn cần mốc giá mới và lệnh trước đã kết thúc.

Telegram giữ ba nhóm Biến động VN30, Nhắc đáo hạn, Tín hiệu / Lệnh. Nhóm thứ ba báo tín hiệu tham khảo và trạng thái mở/đóng/giảm, gồm SL/TP/TSL/DYNAMIC, số HĐ khớp và còn lại. Backend chỉ nhận biên nhận rút gọn đã ghi sổ, không có quyền giao dịch; lỗi Telegram không chặn quản lý E/M.

PAPER dùng giá DNSE và tiền ảo; REAL cần tài khoản phái sinh và OTP. SL hiện do app thực thi, cần app và BOT đang hoạt động; chưa nghiệm thu REAL. Chi tiết: [nghiệp vụ CKPS](support/docs/CKPS.md).

```powershell
.venv\Scripts\python.exe main.py
.venv\Scripts\python.exe backend.py
.venv\Scripts\python.exe -m ckps --demo
.venv\Scripts\python.exe -X utf8 -m pytest support/tests -q -p no:cacheprovider --tb=short
```
