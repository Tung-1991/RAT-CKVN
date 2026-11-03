# RAT VN30 · Semi-auto

- `main.py`: người dùng vào Long/Short bằng tay; BOT chỉ đóng/giảm vị thế theo SL/TP/E và TSL/PROTECT khi được cấp quyền.
- `backend.py`: chạy backend console bằng biến môi trường; thường dùng CHẠY/DỪNG ngay trong KẾT NỐI.
- `START_SYSTEM.bat`: mở app PAPER/REAL, backend hoặc kiểm thử tự động.

MAIN hiển thị ký quỹ lớn và tổng tiền nhỏ bên dưới; AUTO tính HĐ theo sức mở, không tự trích dự phòng. Cài đặt tập trung vào RULE (một E/M chung, TÍN HIỆU) và KẾT NỐI (DNSE / VỐN, TELEGRAM / LỊCH), hai cửa sổ cùng kích thước. DNSE / VỐN có ĐỌC API để chọn tài khoản/gói và xem ký quỹ/phí từ DNSE, dùng chung một cặp key/secret, có OTP và tùy chọn ghi nhớ kết nối bằng mã hóa Windows; không lưu mã OTP dùng một lần. Giá lưu gần nhất có thời gian và nhãn CŨ, chỉ để xem. Chọn dòng hợp đồng rồi mở RULE → E/M để nhận/bỏ quyền BOT. BOT OFF khi khởi động. Preview có hai kết quả ĐIỂM VÀO và THỊ TRƯỜNG UP/DOWN cùng trạng thái OTP; giấu thông số chỉ báo, chỉ hiện bảo vệ khi chọn vị thế. Bảng chính ẩn PNL. Telegram chỉ thông báo, không mở/đóng lệnh. Đáo hạn chỉ nhắc trước.

SL/TP giữ % giá vốn; ARM dùng % PNL trên ký quỹ cơ sở/HĐ, TSL/LẶP dùng điểm phần trăm PNL. Cơ sở được lưu cùng vị thế, giảm HĐ không tính lại cơ sở/HĐ, vào thêm bình quân theo fill; tiền nạp/rút không đổi mốc. Một RULE chung cho đang giữ/chờ/mới, không chọn đơn vị hoặc ghi đè trên vé. Preview RULE hiện ký quỹ cơ sở, PNL, điểm và tiền theo số HĐ còn giữ; thiếu cơ sở thì CHỜ. RULE cũ chỉ chuyển bản nháp rồi LƯU, không tự sửa cấu hình lúc mở. App chưa lưu RULE nạp SL 0,5% giá, TP OFF, ARM 5% PNL, TSL/LẶP 1,25 điểm % PNL, mỗi lượt đóng 50% còn lại; DYNAMIC ATR/giữ lãi và LẶP ON. BOT vẫn OFF khi mở.

TSL/ARM và DYNAMIC tự đóng 50% HĐ còn lại mỗi lượt khi BOT và quyền quản lý ON. Không có lựa chọn AUTO/ALERT, GỐC/CÒN LẠI hay nhập tỷ lệ đóng trong E/M. Cấu hình cũ cũng dùng các lựa chọn cố định này; các ngưỡng và cờ bật/tắt nhánh được giữ. Một HĐ còn lại thì đóng một; LẶP vẫn cần mốc giá mới và lệnh trước đã kết thúc.

E/M có SL/TP/ARM/Lùi/LẶP và hai chu kỳ EMA của E. DYNAMIC cho chỉnh START, lùi ATR, giữ % lãi đỉnh và TỚI MFE, giữ tham số/công tắc đã lưu. Preview chính và RULE hiện ATR14 từ nến ngày đã đóng, phiên dữ liệu và khoảng bắt đầu/lùi tính được; thiếu dữ liệu hiện CHỜ. ATR không dùng nến hôm nay và không làm giá cũ trở thành tín hiệu mới. Thiếu ký quỹ cơ sở dừng nhánh PNL cần cơ sở, SL/TP theo giá và E vẫn độc lập.

Telegram chủ yếu báo tín hiệu tham khảo để người dùng tự quyết định và thao tác; thông báo tín hiệu entry không tạo lệnh mở. Telegram giữ ba nhóm Biến động VN30, Nhắc đáo hạn, Tín hiệu / Lệnh. Nhóm thứ ba kèm trạng thái mở/đóng/giảm, gồm SL/TP/TSL/DYNAMIC, số HĐ khớp và còn lại. Backend chỉ nhận biên nhận rút gọn đã ghi sổ, không có quyền giao dịch; lỗi Telegram không chặn quản lý E/M.

PAPER dùng giá DNSE và tiền ảo; REAL cần tài khoản phái sinh và OTP. SL hiện do app thực thi, cần app và BOT đang hoạt động; chưa nghiệm thu REAL. Chi tiết: [nghiệp vụ CKPS](support/docs/CKPS.md).

E tự thoát bật tại RULE → E/M (mặc định OFF): Long EMA3 < EMA6, Short EMA3 > EMA6 thì đóng toàn bộ khi BOT và quyền vị thế ON. Chỉnh hai chu kỳ EMA ngay trong nhóm E tại E/M; luôn REALTIME theo từng giá mới hợp lệ trên nến 1D, độc lập ALERT/Telegram; backend không có quyền giao dịch. SL/TP/E đóng phần chưa giữ chỗ trước, phần còn lại chờ hủy/khớp lệnh cũ được xác nhận; timeout không tự gửi lại.

```powershell
.venv\Scripts\python.exe main.py
.venv\Scripts\python.exe backend.py
.venv\Scripts\python.exe -X utf8 -m pytest support/tests -q -p no:cacheprovider --tb=short
```
