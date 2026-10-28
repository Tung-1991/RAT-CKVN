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

Bố cục MayinTien: tài khoản/vé lệnh trái, bảng vị thế/lệnh phải, PREVIEW/LOG dưới. Preview có một dòng bối cảnh MA200 1D và biến động chỉ đọc, cùng SL/TP, ARM/DYNAMIC và LẶP; thiếu nguồn hiện chờ. Không có quyền giao dịch từ tín hiệu. RULE và KẾT NỐI cùng kích thước, giới hạn theo màn hình/DPI; tab KẾT NỐI không tự đổi cỡ. E/M cuộn khi màn hình nhỏ; các nút ? giải thích nghiệp vụ ngay trong cửa sổ. VỐN hiện trực tiếp hạn mức/rủi ro/phí; 0 là không đặt trần riêng.

Preview giữ chiều cao gọn, bảng lệnh nhận phần không gian còn lại. Ba ô trạng thái màu tách BOT, quyền quản lý vị thế và dữ liệu giá/đối soát; giá cũ hoặc chưa đồng bộ không hiện quản lý ON. Bản mẫu luôn ghi GIÁ MẪU, không hiện trạng thái kết nối DNSE. Chỉ giữ mốc và khoảng cách hiện tại trên Preview; bấm tiêu đề TSL/ARM hoặc DYNAMIC để xem panel giải thích, cấu hình và LẶP bằng chữ lớn. Nút BẢO VỆ LỆNH chỉnh riêng vị thế đang chọn; RULE giữ cấu hình chung đầy đủ.

## Lịch và Telegram

Đáo hạn tính thứ Năm thứ ba, lùi theo ngày nghỉ đã biết; nếu thiếu lịch hiển thị dự kiến. Trước ngày đáo hạn backend gửi nhắc, không chặn giao dịch ngày đó. Ngày nghỉ, đổi rổ và ATO/ATC vẫn theo cấu hình; chỉ chặn mở mới, không chặn đóng/E/M.

Một kênh Telegram với ba lựa chọn: Biến động VN30, Nhắc đáo hạn, Vào lệnh. Nhóm vào lệnh gồm tín hiệu P1/P2/E chỉ tham khảo và thông báo gửi/khớp/hủy/lỗi lệnh mở từ app. App chuyển biên nhận rút gọn qua SQLite cục bộ; backend không đọc tài khoản, token giao dịch hay nhận lệnh giao dịch. Không gửi lại tin cũ khi backend khởi động, tắt nhánh chỉ dừng thông báo. Token chỉ trong phiên/biến môi trường.

## Kiểm thử

Chạy `.venv\Scripts\python.exe -X utf8 -m pytest support/tests -q -p no:cacheprovider --tb=short`. Fixture chặn mạng, dùng sổ tạm. Không gửi lệnh hoặc Telegram thật để thử. Giữ runtime, credentials, môi trường và .artifacts ngoài Git. Trước dùng REAL cần đối chiếu tài khoản/giá/ký quỹ, phí và độ trễ với DNSE.
