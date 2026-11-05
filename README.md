# RAT VN30 · Semi-auto

- `main.py`: người dùng vào Long/Short bằng tay; BOT chỉ đóng/giảm vị thế theo SL/TP/E và ARM/DYNAMIC khi được cấp quyền.
- `backend.py`: chạy backend console bằng biến môi trường; thường dùng CHẠY/DỪNG ngay trong KẾT NỐI.
- `START_SYSTEM.bat`: mở app PAPER/REAL, backend hoặc kiểm thử tự động.

VPS cần Windows 64-bit có phiên Desktop/RDP và Internet. Mở `START_SYSTEM.bat` → **1**: lần đầu tự tải Python riêng cho app nếu cần, tạo `.venv`, cài/kiểm tra thư viện rồi mở app; không cần cài Python trước hoặc quyền admin. Mục **3** cài lại/kiểm tra môi trường, **4** kiểm thử offline. Python lấy từ gói đầy đủ chính thức của Python.org, kiểm tra SHA256 và chữ ký PSF; lưu trong `runtime/python`, không sửa PATH/registry Windows. Môi trường đã sẵn sàng được dùng lại, yêu cầu thư viện thay đổi thì tự cập nhật. Backend thông báo thường chạy từ KẾT NỐI → TELEGRAM / LỊCH → CHẠY; mục **2** dành cho console dùng biến môi trường.

MAIN hiển thị ký quỹ lớn và tổng tiền nhỏ bên dưới; AUTO tính HĐ theo sức mở, không tự trích dự phòng. Cài đặt tập trung vào RULE (một E/M chung, TÍN HIỆU) và KẾT NỐI (DNSE / VỐN, TELEGRAM / LỊCH), hai cửa sổ cùng kích thước. DNSE / VỐN có ĐỌC API để chọn tài khoản/gói và xem ký quỹ/phí từ DNSE, dùng chung một cặp key/secret, có OTP và tùy chọn ghi nhớ kết nối bằng mã hóa Windows; không lưu mã OTP dùng một lần. Giá lưu gần nhất có thời gian và nhãn CŨ, chỉ để xem. Chọn dòng hợp đồng rồi mở RULE → E/M để nhận/bỏ quyền BOT. BOT OFF khi khởi động. Preview có hai kết quả ĐIỂM VÀO và THỊ TRƯỜNG UP/DOWN cùng trạng thái OTP; hiện lý do chờ và EMA/RSI chỉ đọc; ATR đủ % giá vào/điểm/tiền, OTP gọn một dòng, chỉ hiện mốc bảo vệ vị thế khi chọn dòng. Bảng chính ẩn PNL. Telegram chỉ thông báo, không mở/đóng lệnh. Đáo hạn chỉ nhắc trước.

SL/TP và Bắt đầu/Lùi ARM cùng dùng % giá vào bình quân hợp đồng. Khoảng điểm = giá vào × mức nhập / 100; tiền lãi/lỗ xem trước = khoảng điểm × 100.000 × HĐ còn giữ, đúng chiều Long/Short. Không lấy ký quỹ, tổng tiền tài khoản hoặc lãi đã chốt làm cơ sở đặt mốc. Một RULE chung cho đang giữ/chờ/mới, không chọn đơn vị hoặc ghi đè trên vé. RULE PNL cũ được quy đổi bằng cơ sở đã xác minh, giữ nguyên khoảng giá; thiếu cơ sở chỉ giữ nguyên nhóm cũ chờ quy đổi, không gán nhãn % giá cho số chưa đổi. App chưa lưu RULE nạp SL 1% giá, TP OFF, E ON EMA3/6, ARM Bắt đầu 1% giá và Lùi 0,3% giá vào; DYNAMIC ATR/giữ lãi đỉnh. BOT vẫn OFF khi mở.

E/SL/TP/ARM/DYNAMIC đều đóng toàn bộ HĐ khả dụng khi đủ điều kiện, BOT và quyền quản lý ON. Không chia 33%/50%, không nhập tỷ lệ đóng hoặc bước LẶP trong E/M. Cấu hình cũ cũng dùng AUTO + REMAINING + 100%; các ngưỡng và cờ bật/tắt nhánh được giữ. Ý định thoát sống qua hồi giá/restart; phần bị lệnh khác giữ chỗ chờ broker xác nhận, không chờ thêm mốc LẶP. UNKNOWN không tự gửi lại. Telegram chỉ thông báo.

E/M có SL/TP/ARM/Lùi và hai chu kỳ EMA của E. DYNAMIC cho chỉnh START/lùi theo hệ số ATR, giữ % lãi đỉnh và TỚI MFE, giữ tham số/công tắc đã lưu. Các khoảng ATR được hiện thêm % giá vào, điểm và tiền; Giữ lãi đỉnh vẫn là hệ số trên lãi đỉnh. Preview chính và RULE hiện ATR14 từ nến ngày đã đóng, phiên dữ liệu và khoảng bắt đầu/lùi tính được; thiếu dữ liệu hiện CHỜ. ATR không dùng nến hôm nay và không làm giá cũ trở thành tín hiệu mới. RULE giá mới tính mốc không cần ký quỹ; việc gửi lệnh vẫn kiểm tra sức mở/quyền và dữ liệu DNSE.

Telegram chủ yếu báo tín hiệu tham khảo để người dùng tự quyết định và thao tác; thông báo tín hiệu entry không tạo lệnh mở. Telegram giữ ba nhóm Biến động VN30, Nhắc đáo hạn, Tín hiệu / Lệnh. Nhóm thứ ba kèm trạng thái mở/đóng/giảm, gồm SL/TP/ARM/DYNAMIC, số HĐ khớp và còn lại. Backend chỉ nhận biên nhận rút gọn đã ghi sổ, không có quyền giao dịch; lỗi Telegram không chặn quản lý E/M.

PAPER dùng giá DNSE và tiền ảo; REAL cần tài khoản phái sinh và OTP. SL hiện do app thực thi, cần app và BOT đang hoạt động; chưa nghiệm thu REAL. Chi tiết: [nghiệp vụ CKPS](support/docs/CKPS.md).

E tự thoát tại RULE → E/M có sẵn ON trong preset app chưa lưu RULE; giữ nguyên E OFF đã lưu và dữ liệu cũ thiếu cờ. Long EMA3 < EMA6, Short EMA3 > EMA6 thì đóng toàn bộ khi BOT và quyền vị thế ON. Chỉnh hai chu kỳ EMA ngay trong nhóm E tại E/M; luôn REALTIME theo từng giá mới hợp lệ trên nến 1D, độc lập ALERT/Telegram; backend không có quyền giao dịch. SL/TP/E đóng phần chưa giữ chỗ trước, phần còn lại chờ hủy/khớp lệnh cũ được xác nhận; timeout không tự gửi lại.

```powershell
.venv\Scripts\python.exe main.py
.venv\Scripts\python.exe backend.py
.venv\Scripts\python.exe -X utf8 -m pytest support/tests -q -p no:cacheprovider --tb=short
```
