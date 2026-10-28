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
  PREVIEW / LOG ở dưới. Preview có một dòng bối cảnh thị trường chỉ đọc, còn lại
  là SL/TP, TSL/ARM, DYNAMIC và LẶP; không thêm form EMA/VA hoặc tình huống mẫu.
- Code chia theo `dashboard/`, `connections/`, `rules/`, `services/`, `trading/`;
  không thêm UI hoặc broker dạng file lớn phẳng tại gốc package.
- MAIN chỉ có RULE chỉ E/M / KẾT NỐI (DNSE, VỐN, Telegram, LỊCH); lịch sử giao dịch/lệnh ở góc bảng.
  Tín hiệu và Telegram nằm ở backend riêng với ba lựa chọn biến động, đáo hạn và vào lệnh.
  Không danh mục CKCS, không tab BOT, không tooltip/legend/preview trùng lặp.
- Thao tác vị thế/lệnh dùng vùng thao tác trong màn hình; chỉ hiện nút phù hợp
  dòng đang chọn. Xác nhận gửi lệnh vẫn cần nhưng nằm trong app, không popup.
- Tab/panel ngắn; chọn trực tiếp, hạn chế dropdown/cuộn và cửa sổ phụ.
- Dùng phần trình bày gốc tại `dashboard/mayin/`, không tự dựng lại form thay
  MayinTien. RULE và KẾT NỐI là hai cửa sổ; giữ font/DPI và các nhóm gốc.
- Thay đổi tiền/vị thế/lệnh cần kiểm thử có ý nghĩa trong `support/tests/`.
  Test offline chặn mạng; không gửi lệnh thật hoặc Telegram để thử.
- `../RAT-CKVN-reference/sources/` chỉ đối chiếu local, không import và không đưa vào gói bán.
  Dữ liệu tài khoản, credentials, `.artifacts/` nằm ngoài Git.
- Nghiệp vụ tại `support/docs/`; script/ảnh tạm tại `.artifacts/`, không sinh
  báo cáo theo ngày trong source.
