# RAT VN30 · Hướng dẫn làm việc

- Gọi người dùng là **thưa Kaiser** hoặc **thưa Ngài**; trả lời ngắn, chính xác.
- Sản phẩm chỉ CKPS VN30. Đọc `support/docs/CKPS.md` trước khi sửa nghiệp vụ.
- Một agent, trừ khi Kaiser yêu cầu rõ dùng subagent.
- Entry chỉ từ thao tác tay. P1 so giá hợp đồng đang giao dịch với MA200.
- Backend riêng giữ P1/P2 MayinTien để phân tích; Telegram gồm biến động VN30,
  nhắc trước đáo hạn và thông báo/gợi ý vào lệnh. Không có quyền mở/đóng lệnh.
- UI dùng TÍN HIỆU / GIỜ THEO DÕI, không dùng BUY/ENTRY BUY/giờ mua. P2 và E
  giữ cổng ALERT riêng trong backend, UI gom dưới EMA/RSI; mặc định OFF,
  tắt chỉ ngừng thông báo, vẫn phân tích.
- P3 giữ giới hạn vốn CKPS; E/M giữ nghiệp vụ hiện có.
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
  RULE E/M chọn CHUNG / VỊ THẾ; cấu hình riêng, kế thừa và nhận/bỏ quản lý đều ở đó.
  Phân tích/Telegram vẫn chạy backend riêng, ba nhóm biến động, đáo hạn và vào lệnh.
  Không danh mục CKCS, không tab BOT, không tooltip/legend/preview trùng lặp.
- DNSE dùng chung một cặp API key/secret; ĐỌC API hiển thị tài khoản CKPS/gói/phí,
  tự chọn khi duy nhất, có nhiều thì chọn từ API. Không nhập ID/phí tay; phí gói không đồng nghĩa tổng thuế/phí Sở.
- Đóng/giảm, hủy/sửa/đối soát lệnh dùng vùng thao tác trong màn hình; chỉ hiện nút phù hợp
  dòng đang chọn. Xác nhận gửi lệnh vẫn cần nhưng nằm trong app, không popup.
- Tab/panel ngắn; chọn trực tiếp, hạn chế dropdown/cuộn và cửa sổ phụ.
- Dùng phần trình bày gốc tại `dashboard/mayin/`, không tự dựng lại form thay
  MayinTien. RULE và KẾT NỐI là hai cửa sổ; giữ font/DPI và các nhóm gốc.
- E/M phải hiện đầy đủ TSL/ARM và DYNAMIC (ATR, giữ lãi, tỷ lệ đóng, LẶP),
  không giấu trong nâng cao. Giữ hint giải thích và cùng kích thước hai cửa sổ.
- Preview gọn, hai ô kết quả chỉ đọc: điểm Long đủ điều kiện từ backend và giá
  hợp đồng so MA200. Thiếu/giá cũ hiện CHỜ; không suy ngược điểm Short. Ẩn PNL
  và trạng thái lặp trên màn hình chính. Nội dung 14, kết quả 18, giá/vốn 24;
  Preview xuống dòng thay vì tự co chữ. Bảng lệnh giãn toàn bộ phần còn lại,
  Preview bám đáy; không co bảng theo số dòng hoặc chừa spacer đen bên dưới.
  Trạng thái bảng xét cả BOT chung và dữ liệu; bỏ nút BẢO VỆ LỆNH/NHẬN/BỎ QUẢN LÝ khỏi bảng,
  dùng RULE → E/M → VỊ THẾ. Backend chỉ nhận tham số tín hiệu qua pipe, không nhận tài khoản/OTP.
- Thay đổi tiền/vị thế/lệnh cần kiểm thử có ý nghĩa trong `support/tests/`.
  Test offline chặn mạng; không gửi lệnh thật hoặc Telegram để thử.
- `../RAT-CKVN-reference/sources/` chỉ đối chiếu local, không import và không đưa vào gói bán.
  Dữ liệu tài khoản, credentials, `.artifacts/` nằm ngoài Git.
- Nghiệp vụ tại `support/docs/`; script/ảnh tạm tại `.artifacts/`, không sinh
  báo cáo theo ngày trong source.
