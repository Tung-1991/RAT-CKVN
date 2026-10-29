# RAT VN30 · Semi-auto

## Phạm vi

App giao dịch VN30F1M: người dùng chọn Long/Short và xác nhận vào lệnh; BOT quản lý SL/TP và PROTECT/TSL cho vị thế được nhận quản lý. Không tự mở, DCA/PCA hoặc đảo chiều. BOT OFF khi khởi động. Vị thế DNSE phải nhận quản lý thủ công. App/backend chạy độc lập; nguồn MayinTien chỉ tham chiếu local, không import.

## Tiền và lệnh

Không tự trích dự phòng: AUTO tính số HĐ theo sức mở DNSE đã xác minh, trừ phần lệnh local chưa được broker giữ chỗ, làm tròn xuống, có thể 0. Tài khoản hiện KÝ QUỸ chữ lớn và tổng tiền chữ nhỏ bên dưới. REAL hiển thị tổng tiền DNSE `stock.totalCash` chỉ để xem; ký quỹ là số tổng cọc DNSE hoặc cọc còn lại + cọc đã dùng khi đủ dữ liệu. Cọc nộp/rút chờ duyệt không cộng vào cọc đã xác nhận; tiền CKCS không cấp sức mở phái sinh. Thiếu dữ liệu hiện chờ, không dựng 0. PAPER dùng tiền ảo, giá DNSE; tỷ lệ ký quỹ PAPER là giả định mô phỏng, không dùng cho REAL.

Sức mở REAL dùng PPSE của đúng tài khoản, mã, gói và giá vé trước gửi. Vé xác nhận số HĐ cụ thể, ký quỹ và lỗ dự kiến tại SL. Phí/trượt giá có thể làm số thực khác. Một điểm/HĐ = 100.000 đồng. Không ép mua 1 HĐ nếu không đủ sức mở. Lệnh đóng/sửa LO kiểm tra bước giá và biên khi có dữ liệu.

Khớp, vị thế và queue cùng transaction; FILLED thiếu bằng chứng đủ HĐ là UNKNOWN. Timeout/5xx là UNKNOWN, không tự gửi lại. Đối soát đúng mã, chiều, KL và ID. Hủy/sửa chờ xác nhận. Khi thoát hết, app yêu cầu hủy phần mở còn chờ; xử lý fill muộn của yêu cầu đó theo ý định thoát hết, không coi yêu cầu hủy là đã hủy.

## Bảo vệ

RULE mặc định các nhánh OFF, TP tạm thời OFF. BOT và quyền vị thế cùng ON mới cho app tự gửi lệnh bảo vệ. SL/TP đóng toàn bộ HĐ có thể đóng; ARM/DYNAMIC chỉ xử lý khi còn lãi trước phí. Long bám đỉnh, Short bám đáy, mốc bảo vệ không tự nới. LẶP dùng bước giá riêng giữa các lượt, theo dõi mốc mới sau lượt trước; mặc định không lặp ARM dưới ngưỡng ARM. E/M hiện đầy đủ TSL/ARM, DYNAMIC, ATR, giữ lãi, tỷ lệ đóng, GỐC/CÒN LẠI và LẶP. AUTO tự đóng khi đủ quyền; ALERT chỉ ghi LOG, độc lập Telegram. Khớp từng phần cùng lệnh chỉ tính một lượt; mốc bất lợi được giữ qua UNKNOWN/restart.

Chưa triển khai nạp/xuất preset nghiệp vụ; app chỉ khôi phục cấu hình đã lưu. Bản mẫu offline dùng TP OFF, SL 0,5% giá, ARM 1% giá, khoảng lùi/bước lặp 0,25% giá, đóng 50% số HĐ còn lại; DYNAMIC dùng ATR START 0,5, ATR trail 0,8 và giữ 70% lãi đỉnh. Đây là dữ liệu minh họa trong RAM, không tự áp vào tài khoản thật hoặc xác nhận ngưỡng giao dịch đã được tối ưu.

E/M mới chỉ dùng PRICE_PERCENT: mọi khoảng SL/TP/ARM/Lùi/LẶP/Tới MFE bằng giá vốn bình quân nhân tỷ lệ nhập rồi chia 100, không phụ thuộc ký quỹ hay NAV. Giá vốn 2.000, SL 0,25% là khoảng giá 5: Long cắt tại 1.995, Short tại 2.005; lỗ trước phí 500.000 đồng/HĐ. SL 2,5% là khoảng giá 50, lỗ 5 triệu/HĐ. Nhập SL 0,25 hoặc -0,25 đều dùng khoảng cách dương 0,25%; dấu chấm hoặc phẩy thập phân đều được. TSL lấy đỉnh Long/đáy Short trừ/cộng khoảng lùi tính trên giá vốn; ví dụ ARM 1%, lùi 0,25%, Long từ 2.000 đạt đỉnh 2.025 thì mốc 2.020. Đóng bớt không đổi giá vốn; vào thêm bình quân giá vốn theo HĐ khớp thực tế, rồi dùng giá vốn mới để tính các khoảng. Mốc bảo vệ đã ghi nhận không tự nới.

Giữ lãi (%) vẫn là phần trăm lãi đỉnh; tỷ lệ đóng (%) vẫn trên số HĐ; ATR vẫn là hệ số biến động giá. Tiền lãi/lỗ được tính riêng từ chênh lệch giá, số HĐ và hệ số 100.000 đồng. PNL% trên ký quỹ cơ sở chỉ còn dùng để đọc lịch sử/hiển thị; ký quỹ vẫn cần cho sức mở DNSE, không quyết định ngưỡng bảo vệ mới. Thiếu ký quỹ cơ sở không khóa quản lý vị thế PRICE_PERCENT có giá vốn hợp lệ.

Không có nút chọn đơn vị. POINTS/PERCENT/PNL_PERCENT cũ vẫn được backend đọc đúng đơn vị cũ cho đến khi lưu chuyển đổi. RULE dựng bản nháp PRICE_PERCENT: cấu hình điểm cần giá vốn/giá hợp đồng xác minh; % PNL cần thêm ký quỹ cơ sở cũ đúng vị thế. Thiếu cơ sở thì CHỜ và khóa lưu, không đổi nhãn hoặc thay số bằng 0. Không có quy đổi ngầm khi mở app. Khi khởi động bằng RULE cũ, các vị thế/lệnh mở đang chờ kế thừa được giữ E/M cũ riêng để đổi RULE mặc định không thay giá bảo vệ của chúng; muốn chuyển vị thế thì LƯU tại VỊ THẾ. Ngưỡng, sàn bảo vệ và trạng thái LẶP đã ghi nhận vẫn giữ nguyên khi chuyển đổi tương đương.

Đơn vị của dữ liệu cũ chỉ là tương thích nội bộ. RULE tạo mới luôn mặc định % giá vốn; bản ghi cũ thiếu nhãn đơn vị vẫn được đọc theo nghĩa cũ để không làm đổi giá SL/TP. Preview, khoảng cách tới mốc và hint cấu hình đều trình bày bằng % giá vốn, không hiện thêm lựa chọn hoặc nhãn mode PNL/điểm. Thiếu dữ liệu quy đổi thì hiện CHỜ DỮ LIỆU; việc trình bày không sửa vị thế, sàn bảo vệ hoặc lượt LẶP.

SL này do app theo dõi và gửi, không phải SL đã xác nhận tại DNSE. BOT OFF, app ngừng, OTP hết hạn hoặc dữ liệu lỗi có thể làm app không gửi đóng. Chưa tích hợp API SL tại broker; chưa nghiệm thu REAL. Nến REAL tải trên worker riêng, không chặn worker xử lý E/M.

## Giao diện

Bố cục MayinTien: tài khoản/vé lệnh trái, bảng vị thế/lệnh phải, PREVIEW/LOG dưới. Bảng chính ẩn PNL; lịch sử giữ số liệu PNL và phí. Bảng có các cột hợp đồng, chiều/HĐ, giá vốn/LO, SL, TP và trạng thái; mỗi vị thế một dòng. Cột trạng thái xét BOT chung, quyền vị thế, dữ liệu và lệnh chờ, không ghi ON chỉ vì vị thế đã được nhận quản lý. Không lặp các dòng chờ giá/kết nối ở nhiều khu vực. Cài đặt tập trung vào RULE (E/M, TÍN HIỆU) và KẾT NỐI (DNSE / VỐN, TELEGRAM / LỊCH); hai cửa sổ cùng kích thước theo DPI, tab không tự đổi cỡ. Không mở cửa sổ cài đặt Telegram riêng.

Preview tập trung hai ô kết quả: ĐIỂM VÀO và THỊ TRƯỜNG. Điểm vào lấy kết quả đã đủ mọi điều kiện từ EMA/RSI và bộ lọc backend; badge READY trung gian không phải điểm vào. Hiện giá Long tại thời điểm phân tích, giấu thông số EMA/RSI và đếm giao cắt. Thị trường UP/DOWN/ĐI NGANG so giá hợp đồng với MA200 từ 200 nến ngày đã đóng; không suy ngược thành tín hiệu Short. Cả hai chỉ để xem, không điền vé, không mở/đóng lệnh hoặc chặn E/M.

DNSE / VỐN dùng chung trang. Một cặp API key/secret dùng cho giá, PAPER/REAL, Preview và backend tín hiệu; Telegram vẫn cần Bot token/Chat ID riêng. ĐỌC API đọc GET /accounts, lọc tài khoản CKPS ACTIVE, rồi lấy gói/biểu phí từ /accounts/{accountNo}/loan-packages (DERIVATIVE) và ký quỹ từ /balances. Một tài khoản/gói thì tự chọn; nhiều thì chọn từ danh sách API, không nhập ID tay. Đọc Preview chạy worker riêng, chưa đổi sổ hay xác thực OTP. Có nút HIỆN/ẨN key; mở lại luôn che. Form luôn hiện OTP; PAPER không cần OTP nên khóa thao tác xác thực. Nút LƯU ghi cấu hình kết nối, KẾT NỐI DNSE áp dụng kết nối và đối soát sổ. Ghi nhớ kết nối là tùy chọn: API key/secret và phiên xác thực còn hạn được Windows DPAPI mã hóa theo người dùng, ràng buộc đúng API và tài khoản. Không lưu mã OTP dùng một lần; bỏ ghi nhớ rồi LƯU sẽ xóa dữ liệu đã ghi nhớ. Không đưa token giao dịch vào snapshot UI hoặc pipe backend. Preview hiện trạng thái OTP và hạn phiên; app luôn mở PAPER, BOT OFF, REAL do người dùng chọn.

Phí gói là thông tin chỉ đọc từ tradingFee của gói đã chọn, không nhập Phí/HĐ. FIXED giữ đúng giá trị 0; thiếu, không hợp lệ hoặc PROGRESSIVE chưa đủ mức áp dụng hiện CHỜ. fixedTradingFee là phí thường; fixedDailyCloseTradingFee là mức đóng trong ngày. Ước lượng rủi ro/đóng dùng mức cao hơn trong hai mức cố định; chưa coi phí gói là tổng thuế/phí Sở. REAL không lấy phí mô phỏng hoặc tỷ lệ CKCS thay phí gói; thiếu phí thì phần ước tính lỗ tại SL hiện chờ, không tạo thêm cổng hạn mức. PAPER dùng phí gói đã đọc để mô phỏng; khi chưa có mức áp dụng, phí mô phỏng cũ chỉ là giả định, không phải xác nhận từ DNSE. Không có GIỚI HẠN TỰ ĐẶT hoặc ô nhập trần ký quỹ, tổng HĐ, rủi ro % NAV. Sức mở Long/Short, ký quỹ và phí tự đọc từ DNSE đúng tài khoản/gói/giá vé; PAPER tính sức mở từ tiền ảo và giả định ký quỹ mô phỏng. Các trường hạn mức tài khoản cũ được bỏ qua khi đọc và không ghi lại, không còn chặn lệnh ẩn. Người dùng chọn số HĐ hoặc AUTO rồi xác nhận lệnh tay; SL/TP/TSL/DYNAMIC theo RULE % giá vốn. Lỗ tại SL chỉ là ước tính để xem trước, không tự đặt thêm ngân sách rủi ro hoặc giới hạn số HĐ. Broker đã giữ chỗ cho lệnh nhận thì không trừ hai lần; lệnh local chưa nhận vẫn phải giữ chỗ. Thiếu sức mở hoặc ký quỹ thì chờ, không ép 1 HĐ; trước gửi kiểm tra lại PPSE đúng giá vé.

Giá DNSE gần nhất được lưu riêng ngoài Git, giữ nguyên mã hợp đồng và thời điểm giá. Mở lại khi chưa có giá mới vẫn hiển thị GIÁ LƯU/CŨ và thời gian; cache này chỉ dùng trình bày, không nhập vào quote giao dịch, không khớp PAPER, không cấp sức mở hoặc tạo tín hiệu mới. Preview báo rõ thiếu giá, thiếu nến ngày hoặc backend chưa chạy; kết quả Long có thời gian phân tích.

Backend chuyển kết quả rút gọn qua tệp JSON local ghi nguyên tử. Chỉ dùng khi đúng mã và thời gian giá/phân tích còn mới; backend chưa chạy, thiếu nến hoặc giá cũ hiện CHỜ. Tắt Telegram không tắt phân tích. Không chuyển trạng thái tín hiệu cũ thành mới chỉ vì có quote mới.

SL/TP và trạng thái chỉ hiện một lần tại bảng lệnh. Chọn vị thế mới hiện hai dòng TSL/ARM và DYNAMIC bên dưới hai ô tín hiệu. Bảng lệnh giãn toàn bộ chiều cao còn lại, Preview bám đáy cửa sổ; không dành vùng đen trống bên dưới. Chi tiết cấu hình/LẶP mở khi bấm tiêu đề, không tự bung khi rê chuột. RULE → E/M có phạm vi MẶC ĐỊNH (CHUNG) / VỊ THẾ: chỉnh bảo vệ riêng, kế thừa RULE chung và nhận/bỏ quyền quản lý vị thế đã chọn. Nhận/bỏ quản lý có xác nhận ngay trong RULE; phải lưu E/M trước khi nhận, xác nhận lại nếu vị thế, E/M hoặc BOT thay đổi. Chọn kế thừa hiển thị các giá trị RULE chung. Quy đổi cấu hình cũ dùng giá vốn của đúng vị thế, kể cả hợp đồng khác mã đang xem; riêng % PNL cũ cần ký quỹ cơ sở đã lưu của vị thế đó. Không còn nút bảo vệ/nhận/bỏ quản lý tại bảng; đóng/giảm và xác nhận lệnh tay giữ tại bảng. Bản mẫu chỉ sửa trong RAM, không dùng runtime hoặc dữ liệu tài khoản thật.

RULE → TÍN HIỆU giữ tham số EMA/RSI riêng cho điểm vào và E, cổng ALERT riêng, REALTIME/CLOSED và nhịp TICK/1M/2M/5M trên nến 1D; giao cắt VA/X PHIÊN, quét trước, xác nhận phút, giờ theo dõi, volume, whipsaw và ngưỡng biến động. Lưu tham số này không sửa E/M hay vốn. MA200 ở backend và Preview cùng dùng 200 nến ngày đã đóng trước hôm nay; ATR14 dùng phiên trước.

Hướng dẫn/công thức nằm trong hint; ngoài form chỉ giữ nhãn, giá trị và trạng thái. Lịch tự dùng ngày nghỉ DNSE, ba lựa chọn né ATO/ATC/đổi rổ và nhắc trước đáo hạn. Ngày nghỉ/ngày đổi rổ bổ sung nằm trong khối NGÀY RIÊNG có thể thu gọn, không mở cửa sổ phụ.

Chữ thống nhất theo vai trò: nhãn 13–14, nội dung 14, kết quả 18, giá/vốn lớn 24. Preview xuống dòng khi thiếu chỗ, không tự thu nhỏ chữ. Bảng chính dùng chữ 14 và dòng cao 44; lịch sử giữ dòng phụ khi cần. Nền trung tính; Long/UP/TP xanh, SL/DOWN đỏ, TSL xanh dương và DYNAMIC cam; trạng thái tạm dừng vàng.

## Lịch và Telegram

Đáo hạn tính thứ Năm thứ ba, lùi theo ngày nghỉ đã biết; nếu thiếu lịch hiển thị dự kiến. Trước ngày đáo hạn backend gửi nhắc, không chặn giao dịch ngày đó. Ngày nghỉ, đổi rổ và ATO/ATC vẫn theo cấu hình; chỉ chặn mở mới, không chặn đóng/E/M.

Một kênh Telegram với ba lựa chọn: Biến động VN30, Nhắc đáo hạn, Vào lệnh. Nhóm vào lệnh gồm tín hiệu P1/P2/E chỉ tham khảo và thông báo gửi/khớp/hủy/lỗi lệnh mở từ app. App chuyển biên nhận rút gọn qua SQLite cục bộ; backend không đọc tài khoản, token giao dịch hay nhận lệnh giao dịch. Không gửi lại tin cũ khi backend khởi động, tắt nhánh chỉ dừng thông báo. Token chỉ trong phiên/biến môi trường.

Token/chat, ba nhóm thông báo, lịch và nút CHẠY/DỪNG nằm trong KẾT NỐI → TELEGRAM / LỊCH. CHẠY tạo tiến trình backend không giao diện; pipe riêng chỉ truyền API đọc giá, token Telegram và tham số tín hiệu, không truyền số tài khoản, OTP hoặc E/M. Lưu áp dụng cấu hình vào backend đang chạy. Tắt Vào lệnh chặn cả P1/P2/E và biên nhận mở lệnh; không tắt phân tích hoặc gửi bù điều kiện cũ khi bật lại.

## Kiểm thử

Chạy `.venv\Scripts\python.exe -X utf8 -m pytest support/tests -q -p no:cacheprovider --tb=short`. Fixture chặn mạng, dùng sổ tạm. Không gửi lệnh hoặc Telegram thật để thử. Giữ runtime, credentials, môi trường và .artifacts ngoài Git. Trước dùng REAL cần đối chiếu tài khoản/giá/ký quỹ, phí và độ trễ với DNSE.
