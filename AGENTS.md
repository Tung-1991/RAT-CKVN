# RAT VN30 · Hướng dẫn làm việc

- Gọi người dùng là **thưa Kaiser** hoặc **thưa Ngài**; trả lời ngắn, chính xác.
- Sản phẩm chỉ CKPS VN30. Đọc `support/docs/CKPS.md` trước khi sửa nghiệp vụ.
- Một agent, trừ khi Kaiser yêu cầu rõ dùng subagent.
- Entry chỉ từ thao tác tay. P1 so giá hợp đồng đang giao dịch với MA200.
- Backend riêng giữ P1/P2 MayinTien để phân tích; Telegram gồm biến động VN30,
  nhắc trước đáo hạn và Tín hiệu / Lệnh (gợi ý, biên nhận mở/đóng/giảm).
  Không có quyền mở/đóng lệnh.
- UI dùng TÍN HIỆU / GIỜ THEO DÕI, không dùng BUY/ENTRY BUY/giờ mua. P2 và E
  giữ cổng ALERT riêng trong backend, UI gom dưới EMA/RSI; mặc định OFF,
  tắt chỉ ngừng thông báo, vẫn phân tích.
- P3 tự lấy sức mở/ký quỹ CKPS từ DNSE và giữ chỗ lệnh chờ; không có trần ký quỹ,
  tổng HĐ hoặc rủi ro % NAV tự nhập. Cấu hình hạn mức cũ bỏ qua, không chặn ẩn.
  E/M mới dùng duy nhất % giá vốn bình quân hợp đồng (PRICE_PERCENT), không dựa
  ký quỹ hoặc NAV. Giá vốn 2.000, SL 0,25% là khoảng giá 5; TP cố định OFF.
  TSL/LẶP bám đỉnh Long/đáy Short, khoảng lùi quy ra từ cùng % giá vốn.
  RULE tạo mới trong code cũng mặc định PRICE_PERCENT. Preview/hint chỉ hiện
  % giá vốn; đơn vị dữ liệu cũ chỉ xử lý nội bộ, không trình bày thành mode.
  Không chọn đơn vị. Điểm/% PNL cũ chỉ quy đổi bản nháp rồi LƯU; thiếu cơ sở
  giữ nguyên và báo CHỜ. Chỉ một RULE chung cho hợp đồng đang giữ, lệnh chờ và
  lệnh mới; bỏ qua E/M riêng cũ, không ghim hoặc ghi đè SL/TP trên vé lệnh.
  Giữ đầy đủ TSL/DYNAMIC/ATR/LẶP; giữ lãi là % lãi đỉnh, tỷ lệ đóng là % HĐ.
- TSL và DYNAMIC cố định tự đóng 50% HĐ còn lại mỗi lượt khi đủ quyền.
  Không AUTO / ALERT, GỐC / CÒN LẠI hoặc ô nhập tỷ lệ đóng trong E/M;
  chỉ hiển thị dòng 50% HĐ còn lại và giải thích làm tròn trong hint.
  Cấu hình cũ đọc/lưu cũng dùng AUTO + REMAINING + 50%; giữ bốn ngưỡng giá và
  cờ bật/tắt nhánh đã lưu. ALERT của tín hiệu/Telegram vẫn độc lập.
- App chưa lưu RULE tự nạp một preset tại `rules/defaults.py`: TP OFF, SL 0,5%,
  ARM 1%, TSL lùi/LẶP 0,25%, mỗi lượt 50% HĐ còn lại; lặp dưới ARM khi còn lãi.
  DYNAMIC cố định ATR14 nến ngày đã đóng: START 0,5 ATR, trail 0,8 ATR,
  giữ 70% lãi đỉnh, không TỚI MFE riêng; LẶP mặc định ON.
  Chỉ bốn ô số SL/ARM/Lùi/LẶP; bỏ ô chỉnh ATR/giữ lãi/TỚI MFE và lặp dưới ARM.
  Cấu hình cũ cũng dùng các hệ số cố định này; vẫn giữ cờ nhánh/LẶP đã lưu.
  Không thêm menu preset; giữ RULE đã lưu (kể cả OFF). BOT vẫn OFF khi mở.
- BOT chung OFF khi khởi động; vị thế DNSE nhận quản lý thủ công. BOT mẫu bật/tắt trong RAM.
- LỊCH giữ ngày nghỉ DNSE/bổ sung, né đổi rổ và ATO/ATC; đáo hạn chỉ báo trước,
  Ngài tự quyết định giao dịch, không chặn mở mới theo đáo hạn.
  Chỉ chặn mở mới/vào thêm; E/M và đóng/giảm không bị cổng lịch chặn.
- Xét đúng Long/Short, mã hợp đồng, khối lượng khớp và lệnh đang chờ. Không coi
  số liệu thiếu là 0, không dùng tiền CKCS thay ký quỹ phái sinh.
- Fill, vị thế, queue cùng transaction. Timeout là UNKNOWN, không tự POST lại.
- Giữ bố cục MayinTien: trái tài khoản/điều khiển/vé lệnh; phải bảng lệnh ở trên,
  PREVIEW / LOG ở dưới. Preview có hai kết quả ĐIỂM VÀO và THỊ TRƯỜNG UP/DOWN;
  giấu EMA/RSI/các đếm giao cắt. Chỉ thêm TSL/DYNAMIC khi chọn vị thế; SL/TP nằm ở bảng, không lặp lại.
- Code chia theo `dashboard/`, `connections/`, `rules/`, `services/`, `trading/`;
  không thêm UI hoặc broker dạng file lớn phẳng tại gốc package.
- Cài đặt tập trung vào RULE (E/M, TÍN HIỆU) và KẾT NỐI (DNSE / VỐN, TELEGRAM / LỊCH),
  cùng kích thước/DPI; ít tab, không mở cửa sổ cài đặt backend riêng. Lịch sử ở góc bảng.
  RULE E/M chỉ một form, nút LƯU RULE; không MẶC ĐỊNH / VỊ THẾ hoặc ô kế thừa.
  Chọn dòng hợp đồng chỉ để nhận/bỏ quyền BOT tại RULE; không đổi bộ tham số.
  Phân tích/Telegram vẫn chạy backend riêng, ba nhóm biến động, đáo hạn và Tín hiệu / Lệnh.
  Không danh mục CKCS, không tab BOT, không tooltip/legend/preview trùng lặp.
- DNSE dùng chung một cặp API key/secret; ĐỌC API hiển thị tài khoản CKPS/gói/phí,
  tự chọn khi duy nhất, có nhiều thì chọn từ API. Không nhập ID/phí tay; phí gói không đồng nghĩa tổng thuế/phí Sở.
- Đóng/giảm, hủy/sửa/đối soát lệnh dùng vùng thao tác trong màn hình; chỉ hiện nút phù hợp
  dòng đang chọn. Xác nhận gửi lệnh vẫn cần nhưng nằm trong app, không popup.
- Hướng dẫn/công thức đưa vào hint; lịch ngày nghỉ DNSE tự động, ngày bổ sung thu gọn
  trong NGÀY RIÊNG. Lỗ dự kiến tại SL tự tính từ E/M để xem trước khi xác nhận;
  không thêm hạn mức tài khoản bắt người dùng nhập.
- Tab/panel ngắn; chọn trực tiếp, hạn chế dropdown/cuộn và cửa sổ phụ.
- Dùng phần trình bày gốc tại `dashboard/mayin/`, không tự dựng lại form thay
  MayinTien. RULE và KẾT NỐI là hai cửa sổ; giữ font/DPI và các nhóm gốc.
- E/M hiện TSL/ARM và DYNAMIC, mức đóng cố định, LẶP; ATR/giữ lãi chỉ đọc,
  không giấu trong nâng cao hoặc thêm option. Giữ hint và cùng cỡ hai cửa sổ.
- Preview và RULE cùng hiện ATR14, phiên nến, START/lùi tính ra từ nguồn thực thi;
  thiếu nến/khác mã hiện CHỜ. Giá cũ vẫn khóa tín hiệu; ATR nến đã đóng hiển thị
  riêng với ngày phiên, không lấy nến hôm nay hoặc dựng số mẫu trong app thật.
- Preview gọn, hai ô kết quả chỉ đọc: điểm Long đủ điều kiện từ backend và giá
  hợp đồng so MA200. Thiếu/giá cũ hiện CHỜ; không suy ngược điểm Short. Ẩn PNL
  và trạng thái lặp trên màn hình chính. Nội dung 14, kết quả 18, giá/vốn 24;
  Preview xuống dòng thay vì tự co chữ. Bảng lệnh giãn toàn bộ phần còn lại,
  Preview bám đáy; không co bảng theo số dòng hoặc chừa spacer đen bên dưới.
  Trạng thái bảng xét cả BOT chung và dữ liệu; bỏ nút BẢO VỆ LỆNH/NHẬN/BỎ QUẢN LÝ khỏi bảng,
  chọn dòng rồi mở RULE → E/M để nhận/bỏ quyền BOT. Backend chỉ nhận tham số tín hiệu qua pipe, không nhận tài khoản/OTP.
- Thay đổi tiền/vị thế/lệnh cần kiểm thử có ý nghĩa trong `support/tests/`.
  Test offline chặn mạng; không gửi lệnh thật hoặc Telegram để thử.
- `../RAT-CKVN-reference/sources/` chỉ đối chiếu local, không import và không đưa vào gói bán.
  Dữ liệu tài khoản, credentials, `.artifacts/` nằm ngoài Git.
- Nghiệp vụ tại `support/docs/`; script/ảnh tạm tại `.artifacts/`, không sinh
  báo cáo theo ngày trong source.
