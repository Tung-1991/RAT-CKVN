# RAT VN30 · Semi-auto

- `main.py`: vào Long/Short bằng tay, quản lý SL/TP và TSL/PROTECT.
- `backend.py`: chạy backend console bằng biến môi trường; thường dùng CHẠY/DỪNG ngay trong KẾT NỐI.
- `START_SYSTEM.bat`: mở app, backend, preview mẫu hoặc kiểm thử offline.

MAIN hiển thị ký quỹ lớn và tổng tiền nhỏ bên dưới; AUTO tính HĐ theo sức mở, không tự trích dự phòng. Cài đặt tập trung vào RULE (E/M chung/riêng, TÍN HIỆU) và KẾT NỐI (DNSE, VỐN, TELEGRAM / LỊCH), hai cửa sổ cùng kích thước. Nhận/bỏ quản lý tại RULE → E/M → VỊ THẾ. BOT OFF khi khởi động. Preview có hai kết quả ĐIỂM VÀO và THỊ TRƯỜNG UP/DOWN; giấu thông số chỉ báo, chỉ hiện bảo vệ khi chọn vị thế. Bảng chính ẩn PNL. Telegram chỉ thông báo, không mở/đóng lệnh. Đáo hạn chỉ nhắc trước.

PAPER dùng giá DNSE và tiền ảo; REAL cần tài khoản phái sinh và OTP. SL hiện do app thực thi, cần app và BOT đang hoạt động; chưa nghiệm thu REAL. Chi tiết: [nghiệp vụ CKPS](support/docs/CKPS.md).

```powershell
.venv\Scripts\python.exe main.py
.venv\Scripts\python.exe backend.py
.venv\Scripts\python.exe -m ckps --demo
.venv\Scripts\python.exe -X utf8 -m pytest support/tests -q -p no:cacheprovider --tb=short
```
