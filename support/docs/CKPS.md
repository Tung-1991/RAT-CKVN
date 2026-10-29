# RAT VN30 · Semi-auto

## Phạm vi

App giao dịch VN30F1M: người dùng chọn Long/Short và xác nhận vào lệnh; BOT quản lý SL/TP và PROTECT/TSL cho vị thế được nhận quản lý. Không tự mở, DCA/PCA hoặc đảo chiều. BOT OFF khi khởi động. Vị thế DNSE phải nhận quản lý thủ công. App/backend chạy độc lập; nguồn MayinTien chỉ tham chiếu local, không import.

## Tiền và lệnh

Không tự trích dự phòng: AUTO tính số HĐ theo sức mở DNSE và các hạn mức đã đặt, làm tròn xuống, có thể 0. Tài khoản hiện KÝ QUỸ chữ lớn và tổng tiền chữ nhỏ bên dưới. REAL hiển thị tổng tiền DNSE `stock.totalCash` chỉ để xem; ký quỹ là số tổng cọc DNSE hoặc cọc còn lại + cọc đã dùng khi đủ dữ liệu. Cọc nộp/rút chờ duyệt không cộng vào cọc đã xác nhận; tiền CKCS không cấp sức mở phái sinh. Thiếu dữ liệu hiện chờ, không dựng 0. PAPER dùng tiền ảo, giá DNSE; tỷ lệ ký quỹ PAPER là giả định mô phỏng, không dùng cho REAL.

Sức mở REAL dùng PPSE của đúng tài khoản, mã, gói và giá vé trước gửi. Vé xác nhận số HĐ cụ thể, ký quỹ và lỗ dự kiến tại SL. Phí/trượt giá có thể làm số thực khác. Một điểm/HĐ = 100.000 đồng. Không ép mua 1 HĐ nếu không đủ sức mở. Lệnh đóng/sửa LO kiểm tra bước giá và biên khi có dữ liệu.

Khớp, vị thế và queue cùng transaction; FILLED thiếu bằng chứng đủ HĐ là UNKNOWN. Timeout/5xx là UNKNOWN, không tự gửi lại. Đối soát đúng mã, chiều, KL và ID. Hủy/sửa chờ xác nhận. Khi thoát hết, app yêu cầu hủy phần mở còn chờ; xử lý fill muộn của yêu cầu đó theo ý định thoát hết, không coi yêu cầu hủy là đã hủy.

## Bảo vệ

RULE mặc định các nhánh OFF; cần nhập và bật SL, ARM và khoảng lùi phù hợp. BOT và quyền vị thế cùng ON mới cho app tự gửi lệnh bảo vệ. SL/TP đóng toàn bộ HĐ có thể đóng; ARM/DYNAMIC chỉ xử lý khi còn lãi trước phí. Long bám đỉnh, Short bám đáy, sàn không tự nới. ARM phần trăm tính khoảng lùi trên giá vốn; điểm là khoảng cách điểm. LẶP ARM theo đỉnh/đáy mới sau lượt trước; mặc định không lặp dưới ARM. E/M hiện đầy đủ TSL/ARM, DYNAMIC, ATR, giữ lãi, tỷ lệ đóng, GỐC/CÒN LẠI và LẶP; không giấu trong nâng cao. AUTO tự đóng khi đủ quyền; ALERT chỉ ghi LOG trong app, độc lập Telegram. Khớp từng phần cùng lệnh chỉ tính một lượt; mốc bất lợi được giữ qua UNKNOWN/restart.

ĐIỂM và % GIÁ là hai đơn vị khoảng giá. Đổi đơn vị sẽ quy đổi sáu ngưỡng theo giá hợp đồng mới đang xem; thiếu giá mới thì giữ nguyên đơn vị/ngưỡng và báo lý do. Ngưỡng phần trăm sau khi lưu vẫn áp dụng theo giá vốn từng vị thế; cần kiểm tra trước khi lưu.

SL này do app theo dõi và gửi, không phải SL đã xác nhận tại DNSE. BOT OFF, app ngừng, OTP hết hạn hoặc dữ liệu lỗi có thể làm app không gửi đóng. Chưa tích hợp API SL tại broker; chưa nghiệm thu REAL. Nến REAL tải trên worker riêng, không chặn worker xử lý E/M.

## Giao diện

Bố cục MayinTien: tài khoản/vé lệnh trái, bảng vị thế/lệnh phải, PREVIEW/LOG dưới. Bảng chính ẩn PNL; lịch sử giữ số liệu PNL và phí. Bảng có các cột hợp đồng, chiều/HĐ, giá vốn/LO, SL, TP và trạng thái; mỗi vị thế một dòng. Cột trạng thái xét BOT chung, quyền vị thế, dữ liệu và lệnh chờ, không ghi ON chỉ vì vị thế đã được nhận quản lý. Không lặp các dòng chờ giá/kết nối ở nhiều khu vực. Cài đặt tập trung vào RULE (E/M, TÍN HIỆU) và KẾT NỐI (DNSE / VỐN, TELEGRAM / LỊCH); hai cửa sổ cùng kích thước theo DPI, tab không tự đổi cỡ. Không mở cửa sổ cài đặt Telegram riêng.

Preview tập trung hai ô kết quả: ĐIỂM VÀO và THỊ TRƯỜNG. Điểm vào lấy kết quả đã đủ mọi điều kiện từ EMA/RSI và bộ lọc backend; badge READY trung gian không phải điểm vào. Hiện giá Long tại thời điểm phân tích, giấu thông số EMA/RSI và đếm giao cắt. Thị trường UP/DOWN/ĐI NGANG so giá hợp đồng với MA200 từ 200 nến ngày đã đóng; không suy ngược thành tín hiệu Short. Cả hai chỉ để xem, không điền vé, không mở/đóng lệnh hoặc chặn E/M.

DNSE / VỐN dùng chung trang. Một cặp API key/secret dùng cho giá, PAPER/REAL, Preview và backend tín hiệu; Telegram vẫn cần Bot token/Chat ID riêng. ĐỌC API đọc GET /accounts, lọc tài khoản CKPS ACTIVE, rồi lấy gói/biểu phí từ /accounts/{accountNo}/loan-packages (DERIVATIVE) và ký quỹ từ /balances. Một tài khoản/gói thì tự chọn; nhiều thì chọn từ danh sách API, không nhập ID tay. Đọc Preview chạy worker riêng, chưa đổi sổ hay xác thực OTP. Có nút HIỆN/ẨN key; mở lại luôn che. Form luôn hiện OTP; PAPER không cần OTP nên khóa thao tác xác thực. Nút LƯU áp dụng hạn mức, KẾT NỐI DNSE áp dụng kết nối và đối soát sổ. Ghi nhớ kết nối là tùy chọn: API key/secret và phiên xác thực còn hạn được Windows DPAPI mã hóa theo người dùng, ràng buộc đúng API và tài khoản. Không lưu mã OTP dùng một lần; bỏ ghi nhớ rồi LƯU sẽ xóa dữ liệu đã ghi nhớ. Không đưa token giao dịch vào snapshot UI hoặc pipe backend. Preview hiện trạng thái OTP và hạn phiên; app luôn mở PAPER, BOT OFF, REAL do người dùng chọn.

Phí gói là thông tin chỉ đọc từ tradingFee của gói đã chọn, không nhập Phí/HĐ. FIXED giữ đúng giá trị 0; thiếu, không hợp lệ hoặc PROGRESSIVE chưa đủ mức áp dụng hiện CHỜ. fixedTradingFee là phí thường; fixedDailyCloseTradingFee là mức đóng trong ngày. Ước lượng rủi ro/đóng dùng mức cao hơn trong hai mức cố định; chưa coi phí gói là tổng thuế/phí Sở. REAL không lấy phí mô phỏng hoặc tỷ lệ CKCS thay phí gói; bật trần rủi ro mà chưa biết phí thì chờ. PAPER dùng phí gói đã đọc để mô phỏng; khi chưa có mức áp dụng, phí mô phỏng cũ chỉ là giả định, không phải xác nhận từ DNSE. Bốn giới hạn ký quỹ/HĐ/lỗ tới SL/lỗ theo NAV là giới hạn Ngài tự đặt, không phải dữ liệu broker.

Giá DNSE gần nhất được lưu riêng ngoài Git, giữ nguyên mã hợp đồng và thời điểm giá. Mở lại khi chưa có giá mới vẫn hiển thị GIÁ LƯU/CŨ và thời gian; cache này chỉ dùng trình bày, không nhập vào quote giao dịch, không khớp PAPER, không cấp sức mở hoặc tạo tín hiệu mới. Preview báo rõ thiếu giá, thiếu nến ngày hoặc backend chưa chạy; kết quả Long có thời gian phân tích.

Backend chuyển kết quả rút gọn qua tệp JSON local ghi nguyên tử. Chỉ dùng khi đúng mã và thời gian giá/phân tích còn mới; backend chưa chạy, thiếu nến hoặc giá cũ hiện CHỜ. Tắt Telegram không tắt phân tích. Không chuyển trạng thái tín hiệu cũ thành mới chỉ vì có quote mới.

SL/TP và trạng thái chỉ hiện một lần tại bảng lệnh. Chọn vị thế mới hiện hai dòng TSL/ARM và DYNAMIC bên dưới hai ô tín hiệu. Bảng lệnh giãn toàn bộ chiều cao còn lại, Preview bám đáy cửa sổ; không dành vùng đen trống bên dưới. Chi tiết cấu hình/LẶP mở khi bấm tiêu đề, không tự bung khi rê chuột. RULE → E/M có phạm vi CHUNG / VỊ THẾ: chỉnh bảo vệ riêng, kế thừa RULE chung và nhận/bỏ quyền quản lý vị thế đã chọn. Nhận/bỏ quản lý có xác nhận ngay trong RULE; phải lưu E/M trước khi nhận, xác nhận lại nếu vị thế, E/M hoặc BOT thay đổi. Chọn kế thừa hiển thị các giá trị RULE chung. Đổi đơn vị riêng dùng giá mới đúng mã vị thế, kể cả hợp đồng khác mã đang xem. Không còn nút bảo vệ/nhận/bỏ quản lý tại bảng; đóng/giảm và xác nhận lệnh tay giữ tại bảng. Bản mẫu chỉ sửa trong RAM, không dùng runtime hoặc dữ liệu tài khoản thật.

RULE → TÍN HIỆU giữ tham số EMA/RSI riêng cho điểm vào và E, cổng ALERT riêng, REALTIME/CLOSED và nhịp TICK/1M/2M/5M trên nến 1D; giao cắt VA/X PHIÊN, quét trước, xác nhận phút, giờ theo dõi, volume, whipsaw và ngưỡng biến động. Lưu tham số này không sửa E/M hay vốn. MA200 ở backend và Preview cùng dùng 200 nến ngày đã đóng trước hôm nay; ATR14 dùng phiên trước.

Chữ thống nhất theo vai trò: nhãn 13–14, nội dung 14, kết quả 18, giá/vốn lớn 24. Preview xuống dòng khi thiếu chỗ, không tự thu nhỏ chữ. Bảng chính dùng chữ 14 và dòng cao 44; lịch sử giữ dòng phụ khi cần. Nền trung tính; Long/UP/TP xanh, SL/DOWN đỏ, TSL xanh dương và DYNAMIC cam; trạng thái tạm dừng vàng.

## Lịch và Telegram

Đáo hạn tính thứ Năm thứ ba, lùi theo ngày nghỉ đã biết; nếu thiếu lịch hiển thị dự kiến. Trước ngày đáo hạn backend gửi nhắc, không chặn giao dịch ngày đó. Ngày nghỉ, đổi rổ và ATO/ATC vẫn theo cấu hình; chỉ chặn mở mới, không chặn đóng/E/M.

Một kênh Telegram với ba lựa chọn: Biến động VN30, Nhắc đáo hạn, Vào lệnh. Nhóm vào lệnh gồm tín hiệu P1/P2/E chỉ tham khảo và thông báo gửi/khớp/hủy/lỗi lệnh mở từ app. App chuyển biên nhận rút gọn qua SQLite cục bộ; backend không đọc tài khoản, token giao dịch hay nhận lệnh giao dịch. Không gửi lại tin cũ khi backend khởi động, tắt nhánh chỉ dừng thông báo. Token chỉ trong phiên/biến môi trường.

Token/chat, ba nhóm thông báo, lịch và nút CHẠY/DỪNG nằm trong KẾT NỐI → TELEGRAM / LỊCH. CHẠY tạo tiến trình backend không giao diện; pipe riêng chỉ truyền API đọc giá, token Telegram và tham số tín hiệu, không truyền số tài khoản, OTP hoặc E/M. Lưu áp dụng cấu hình vào backend đang chạy. Tắt Vào lệnh chặn cả P1/P2/E và biên nhận mở lệnh; không tắt phân tích hoặc gửi bù điều kiện cũ khi bật lại.

## Kiểm thử

Chạy `.venv\Scripts\python.exe -X utf8 -m pytest support/tests -q -p no:cacheprovider --tb=short`. Fixture chặn mạng, dùng sổ tạm. Không gửi lệnh hoặc Telegram thật để thử. Giữ runtime, credentials, môi trường và .artifacts ngoài Git. Trước dùng REAL cần đối chiếu tài khoản/giá/ký quỹ, phí và độ trễ với DNSE.
