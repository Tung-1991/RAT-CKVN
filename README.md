# RAT VN30 · Semi-auto

- `main.py`: mở app giao dịch PAPER/REAL, entry tay và BOT chỉ quản lý thoát.
- `backend.py`: mở panel **Blackbox** chỉ để chỉnh RULE tín hiệu.
- `START_SYSTEM.bat`: **1 Mở app · 2 Blackbox · 3 Rà soát/cài môi trường · 4 Update · 5 Nạp preset · 6 Thoát**.

VPS cần Windows 64-bit có phiên Desktop/RDP và Internet. Máy mới chọn **3** để chuẩn bị Python/Tkinter/thư viện riêng, sau đó **1** để mở app. Mục **1/2 chỉ mở chương trình**, thiếu môi trường báo chọn mục 3, không tự cài. Mục 3 rà soát, dùng lại môi trường đã sẵn sàng và sửa khi thiếu/lỗi; Python từ Python.org được kiểm tra SHA256/chữ ký PSF, không cần admin hoặc sửa PATH/registry. Mục **2** mở Blackbox chỉ có RULE tín hiệu và LƯU; không có API, kết nối, Telegram, nút CHẠY hoặc điều khiển bot. Tham số tín hiệu được đưa khỏi RULE của app chính.

Mục **4 Update** chạy ngay trong cửa sổ BAT hiện tại, không mở thêm cửa sổ; xong bấm phím bất kỳ để quay về menu mới. Mục này chỉ chạy `git pull --ff-only origin main`; không cài thư viện, chạy test hoặc nạp RULE. Không có bước tải ZIP. Nếu Git báo xung đột hoặc không thể fast-forward thì giữ lỗi để xử lý, không reset.

Mục **5 Nạp preset** mở hộp chọn file JSON tại `support/presets`. File **`kaiser-vn30.json`** đã chứa RULE E/M và tín hiệu Blackbox đang lưu trên máy Kaiser; file đi cùng repo để nạp trên VPS. Đóng app/Blackbox, chọn 5 rồi chọn file đó: nạp các nhóm RULE có trong file, giữ nguyên tài khoản, vốn, API, Telegram và dữ liệu lệnh/vị thế của VPS; sao lưu cấu hình cũ trước ghi. File lỗi không được áp dụng. Mục **6** thoát menu. Kiểm thử bảo trì chạy bằng `.venv\Scripts\python.exe -X utf8 -m pytest support/tests -q -p no:cacheprovider --tb=short`.


MAIN hiển thị ký quỹ lớn và tổng tiền nhỏ bên dưới; AUTO tính HĐ theo sức mở, không tự trích dự phòng. Cài đặt tập trung vào RULE (một E/M chung), Blackbox (RULE tín hiệu) và KẾT NỐI (DNSE / VỐN, TELEGRAM / LỊCH), RULE/KẾT NỐI cùng kích thước. DNSE / VỐN có ĐỌC API để chọn tài khoản/gói và xem ký quỹ/phí từ DNSE, dùng chung một cặp key/secret, có OTP và tùy chọn ghi nhớ kết nối bằng mã hóa Windows; không lưu mã OTP dùng một lần. Giá lưu gần nhất có thời gian và nhãn CŨ, chỉ để xem. Chọn dòng hợp đồng rồi mở RULE → E/M để nhận/bỏ quyền BOT. BOT OFF khi khởi động. Preview có hai kết quả ĐIỂM VÀO và THỊ TRƯỜNG UP/DOWN cùng trạng thái OTP; hiện lý do chờ và EMA/RSI chỉ đọc; ATR đủ % giá vào/điểm/tiền, OTP gọn một dòng, chỉ hiện mốc bảo vệ vị thế khi chọn dòng. Bảng chính ẩn PNL. Telegram chỉ thông báo, không mở/đóng lệnh. Đáo hạn chỉ nhắc trước.

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
