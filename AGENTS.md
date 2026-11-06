# RAT VN30 · Hướng dẫn làm việc

- Chỉ gọi ba nhánh EXIT là ARM, E và DYNAMIC. ARM gồm mức Bắt đầu và Lùi bám đỉnh/đáy;
  không tách cơ chế bám đỉnh thành nhánh EXIT hoặc nhãn khác trên UI/Telegram.

- Menu BAT cố định: 1 Mở app, 2 Blackbox, 3 Rà soát/cài môi trường, 4 Update, 5 Nạp preset, 6 Thoát.
  Mục 1/2 không tự cài. Blackbox chỉ là panel RULE tín hiệu để phát triển entry bot sau này; không có kết nối/API/Telegram hoặc nút CHẠY.
  RULE app chính chỉ E/M; Update chỉ chạy git pull --ff-only origin main trong console BAT đang mở, không bật PowerShell riêng; không tải ZIP/cài/nạp RULE.
  Nạp preset cho chọn file JSON trong support/presets, giữ tài khoản/kết nối/vốn/Telegram/sổ lệnh; sao lưu trước ghi, không bật BOT.

- Gọi người dùng là **thưa Kaiser** hoặc **thưa Ngài**; trả lời ngắn, chính xác.
- Sản phẩm chỉ CKPS VN30. Đọc `support/docs/CKPS.md` trước khi sửa nghiệp vụ.
- Một agent, trừ khi Kaiser yêu cầu rõ dùng subagent.
- Entry chỉ từ thao tác tay. P1 so giá hợp đồng đang giao dịch với MA200.
  Ngoài phiên có thể xác nhận LO lưu tại app (SCHEDULED), giữ nguyên mã/giá/HĐ,
  chờ phiên hợp lệ rồi mới gửi bằng giá mới/sức mở/OTP REAL đã xác minh.
  Cache chỉ phục vụ vé, không làm mới quote hoặc tạo fill. Lệnh chờ sống qua restart,
  hủy local không gọi broker; quá phiên hẹn/đổi mã thì hết hiệu lực, không tự chuyển.
- Backend riêng giữ P1/P2 MayinTien để phân tích; Telegram gồm biến động VN30,
  nhắc trước đáo hạn và Tín hiệu / Lệnh (gợi ý, biên nhận mở/đóng/giảm).
  Không có quyền mở/đóng lệnh.
- E thực thi tại app giao dịch, tách khỏi E ALERT của backend: EMA nhanh/chậm
  mặc định 3/6, chỉnh ngay E/M; luôn REALTIME theo từng giá mới trên nến 1D, không chọn chế độ/nhịp.
  Long nhanh < chậm, Short nhanh > chậm thì đóng toàn bộ khi E + BOT + quyền vị thế ON. Preset app chưa lưu RULE có E ON;
  giữ E OFF đã lưu và dữ liệu cũ thiếu cờ. Bật/tắt và lưu tại RULE → E/M; không phụ thuộc ALERT/Telegram, không mở hoặc đảo chiều.
- SL/TP/E/ARM/DYNAMIC đóng toàn bộ HĐ khả dụng trước, hủy lệnh đóng cũ cản trở và chờ broker xác nhận
  trước khi giải phóng giữ chỗ. Ý định thoát lưu bền qua hồi giá/restart, vẫn
  cần BOT/quyền ON; tắt nhánh hoặc bỏ quản lý dừng ý định. UNKNOWN không gửi lại.
- UI dùng TÍN HIỆU / GIỜ THEO DÕI, không dùng BUY/ENTRY BUY/giờ mua. P2 và E
  giữ cổng ALERT riêng trong backend, UI gom dưới EMA/RSI; mặc định OFF,
  tắt chỉ ngừng thông báo, vẫn phân tích.
- P3 tự lấy sức mở/ký quỹ CKPS từ DNSE và giữ chỗ lệnh chờ; không có trần ký quỹ,
  tổng HĐ hoặc rủi ro % NAV tự nhập. Cấu hình hạn mức cũ bỏ qua, không chặn ẩn.
  SL/TP và Bắt đầu/Lùi ARM đều dùng % giá vào bình quân hợp đồng (PRICE_PERCENT), không dựa NAV/ký quỹ.
  Cả distance_unit và trailing_unit của RULE mới là PRICE_PERCENT; không nhập % PNL.
  Giá vốn 2.000, SL 0,25% là khoảng giá 5. TP mặc định OFF,
  có công tắc và mức % giá vốn tại RULE; bật thì chốt toàn bộ. Giữ cấu hình TP đã lưu.
  ARM bám đỉnh Long/đáy Short; khoảng lùi = giá vào × mức nhập / 100.
  Tiền/HĐ = khoảng điểm × 100.000. Preview hiện % giá vào, điểm và tiền theo HĐ còn giữ.
  PNL tiền chỉ là kết quả xem trước, không dùng % PNL hoặc lãi đã chốt làm cơ sở đặt mốc.
  RULE giá mới không cần ký quỹ để tính mốc; sức mở vẫn phải có ký quỹ DNSE xác minh.
  Không chọn đơn vị. RULE cũ chỉ quy đổi bản nháp rồi LƯU; thiếu cơ sở
  chỉ khóa ô cần quy đổi; phần còn lại vẫn chỉnh/lưu được. Giữ số và đơn vị nguồn
  của nhóm CHỜ, tự hoàn tất bản nháp khi có cơ sở; không tự áp dụng trước LƯU.
  RULE PNL cũ chỉ quy đổi khi có cơ sở đúng mã/giá, giữ nguyên khoảng giá, sàn và trạng thái.
  Giá đóng DNSE hợp lệ dùng được để xem trước/quy đổi, vẫn khóa giao dịch.
  Chỉ một RULE chung cho hợp đồng đang giữ, lệnh chờ và
  lệnh mới; bỏ qua E/M riêng cũ, không ghim hoặc ghi đè SL/TP trên vé lệnh.
  Giữ đầy đủ ARM/DYNAMIC/ATR; giữ lãi là % lãi đỉnh, không phải tỷ lệ HĐ đóng.
- ARM và DYNAMIC cố định tự đóng 100% HĐ còn lại khi đủ quyền.
  Không AUTO / ALERT, GỐC / CÒN LẠI hoặc ô nhập tỷ lệ đóng trong E/M;
  chỉ hiển thị dòng Đóng toàn bộ HĐ còn lại. Ẩn điều khiển LẶP chia lượt;
  giữ dữ liệu cũ để quy đổi nhưng không chờ bước LẶP khi thoát toàn bộ.
  Cấu hình cũ đọc/lưu cũng dùng AUTO + REMAINING + 100%; giữ các ngưỡng giá và
  cờ bật/tắt nhánh đã lưu. ALERT của tín hiệu/Telegram vẫn độc lập.
- App chưa lưu RULE tự nạp một preset tại `rules/defaults.py`: TP OFF, SL 1%, E ON EMA3/6,
  ARM Bắt đầu 1% giá, Lùi 0,3% giá vào, chạm mốc đóng toàn bộ HĐ còn lại.
  DYNAMIC dùng ATR14 nến ngày đã đóng; mặc định START 0,5 ATR, trail 0,8 ATR,
  giữ 65% lãi đỉnh, TỚI MFE OFF; chạm mốc đóng toàn bộ, không chia lượt; LẶP preset OFF.
  DYNAMIC cho chỉnh START/trail ATR/giữ lãi/TỚI MFE và bật/tắt từng thành phần.
  Giữ tham số đã lưu, không ép về mặc định. LẶP cũ chỉ giữ để tương thích dữ liệu;
  phần chưa khớp tiếp tục theo ý định thoát toàn bộ, không chờ mốc lặp.
  Chỉ nạp preset khi Ngài chọn mục Nạp preset và chọn file; mở app/Update giữ RULE đã lưu (kể cả OFF). BOT vẫn OFF khi mở.
- Chỉ có app chính PAPER/REAL, không có bản mẫu/offline hoặc `--demo`.
  BOT chung OFF khi khởi động; vị thế DNSE nhận quản lý thủ công.
- LỊCH giữ ngày nghỉ DNSE/bổ sung, né đổi rổ và ATO/ATC; đáo hạn chỉ báo trước,
  Ngài tự quyết định giao dịch, không chặn mở mới theo đáo hạn.
  Chỉ chặn mở mới/vào thêm; E/M và đóng/giảm không bị cổng lịch chặn.
  Né ATO/ATC mặc định ON cũng áp dụng trước gửi LO chờ phiên.
  LO đã được broker nhận vẫn có thể khớp trong phiên định kỳ.
- Xét đúng Long/Short, mã hợp đồng, khối lượng khớp và lệnh đang chờ. Không coi
  số liệu thiếu là 0, không dùng tiền CKCS thay ký quỹ phái sinh.
- Fill, vị thế, queue cùng transaction. Timeout là UNKNOWN, không tự POST lại.
- Giữ bố cục MayinTien: trái tài khoản/điều khiển/vé lệnh; phải bảng lệnh ở trên,
  PREVIEW / LOG ở dưới. Preview có hai kết quả ĐIỂM VÀO và THỊ TRƯỜNG UP/DOWN;
  hiện trạng thái phân tích và EMA/RSI chỉ đọc. Chỉ thêm ARM/DYNAMIC khi chọn vị thế; SL/TP nằm ở bảng, không lặp lại.
- Code chia theo `dashboard/`, `connections/`, `rules/`, `services/`, `trading/`;
  không thêm UI hoặc broker dạng file lớn phẳng tại gốc package.
- Cài đặt tại RULE (E/M), Blackbox (RULE tín hiệu) và KẾT NỐI (DNSE / VỐN, TELEGRAM / LỊCH),
  cùng kích thước/DPI; ít tab, RULE tín hiệu nằm tại panel Blackbox riêng. Lịch sử ở góc bảng.
  RULE E/M chỉ một form, nút LƯU RULE; không MẶC ĐỊNH / VỊ THẾ hoặc ô kế thừa.
  Chọn dòng hợp đồng chỉ để nhận/bỏ quyền BOT tại RULE; không đổi bộ tham số.
  Phân tích/Telegram vẫn chạy backend riêng, ba nhóm biến động, đáo hạn và Tín hiệu / Lệnh.
  Không danh mục CKCS, không tab BOT, không tooltip/legend/preview trùng lặp.
- DNSE dùng chung một cặp API key/secret; ĐỌC API hiển thị tài khoản CKPS/gói/phí,
  tự chọn khi duy nhất, có nhiều thì chọn từ API. Không nhập ID/phí tay; phí gói không đồng nghĩa tổng thuế/phí Sở.
  PROGRESSIVE hợp lệ dùng bậc cao nhất để ước phí, ghi rõ ƯỚC/≤; chưa xác nhận bậc thực tế.
  AUTO chưa có HĐ hợp lệ hiện SL/TP/phí theo 1 HĐ, không dựng tổng bằng 0 hoặc cấp sức mở.
- Bot token Telegram ghi nhớ bằng Windows DPAPI riêng khi LƯU/CHẠY; mở lại che token,
  backend vẫn chưa chạy. Không phụ thuộc ghi nhớ/đổi API DNSE; xóa token rồi LƯU để quên.
  Không ghi plaintext, không đưa token vào cache giá/JSON tham số hoặc Preview chỉ đọc.
- Đóng/giảm, hủy/sửa/đối soát lệnh dùng vùng thao tác trong màn hình; chỉ hiện nút phù hợp
  dòng đang chọn. Xác nhận gửi lệnh vẫn cần nhưng nằm trong app, không popup.
- Hướng dẫn/công thức đưa vào hint; lịch ngày nghỉ DNSE tự động, ngày bổ sung thu gọn
  trong NGÀY RIÊNG. Lỗ dự kiến tại SL tự tính từ E/M để xem trước khi xác nhận;
  không thêm hạn mức tài khoản bắt người dùng nhập.
- Tab/panel ngắn; chọn trực tiếp, hạn chế dropdown/cuộn và cửa sổ phụ.
- Dùng phần trình bày gốc tại `dashboard/mayin/`, không tự dựng lại form thay
  MayinTien. RULE/KẾT NỐI tối đa 780×600 logic, cùng DPI; E/M nhãn 12, số 14, giữ các nhóm gốc.
  SL/TP gom công tắc và ô số cùng hàng; không hiện bước chia lượt LẶP.
- E/M hiện ARM và DYNAMIC, đóng toàn bộ; ATR14 nguồn chỉ đọc,
  hệ số DYNAMIC chỉnh trực tiếp, không giấu trong nâng cao. Giữ hint và cùng cỡ hai cửa sổ.
- Preview và RULE cùng hiện ATR14, phiên nến, START/lùi tính ra từ nguồn thực thi;
  thiếu nến/khác mã hiện CHỜ. Giá cũ vẫn khóa tín hiệu; ATR nến đã đóng hiển thị
  riêng với ngày phiên, không lấy nến hôm nay hoặc dựng số mẫu trong app thật.
- Preview tự chạy backend chỉ đọc khi có API, cache riêng signals/preview;
  không cần CHẠY Telegram, ép Telegram OFF/token rỗng cả khi cấu hình/môi trường có sẵn.
  Đổi API chờ tiến trình cũ dừng; backend này không nhận tài khoản/OTP/E/M.
- Header giá bỏ badge mã; chênh lệch điểm/% so đóng phiên trước cùng mã và KQ/HĐ rút gọn.
  Mã, ký quỹ đầy đủ, giá/ngày phiên so sánh nằm trong hint ký quỹ, hover đứng 0,5 giây.
  Giá đóng trước lấy GET trades G1 cuối ngày trước ngày của quote, qua worker đọc riêng;
  không lấy basicPrice/tham chiếu hoặc nến nối kỳ thay close đúng mã. Cache chỉ để hiển thị.
- Preview gọn, hai ô kết quả chỉ đọc: điểm Long đủ điều kiện từ backend và giá
  hợp đồng so MA200. Thiếu/giá cũ trong phiên hiện CHỜ; không suy ngược điểm Short.
  Bảng chính ẩn PNL; Preview bảo vệ vị thế hiện % giá vào/điểm/tiền.
  Preview: nhãn 12–13, kết quả 22, chi tiết 13–14; OTP 11 thường, gọn một dòng, giá/vốn 24.
  Hai ô kết quả cao tối thiểu 96, vùng Preview tối thiểu 300 logic, tự tăng theo nội dung; căn lề 10,
  giãn dòng rõ, vẫn để bảng lệnh giãn phần còn lại và kiểm tra DPI 100–200%.
  Dòng bảo vệ chỉ hiện mốc, % giá vào/điểm/tiền và HĐ đóng; khoảng còn lại chi tiết đưa vào hint.
  DYNAMIC giữ ATR/giữ lãi đỉnh; Preview quy đổi các khoảng ATR về % giá vào/điểm/tiền, không cần ký quỹ.
  Hệ số Giữ lãi đỉnh (%) vẫn là % lãi đỉnh, không đổi thành khoảng % giá hoặc tỷ lệ HĐ đóng.
  Preview xuống dòng thay vì tự co chữ. Bảng lệnh giãn toàn bộ phần còn lại,
  Preview bám đáy; không co bảng theo số dòng hoặc chừa spacer đen bên dưới.
  Trạng thái bảng xét cả BOT chung và dữ liệu; bỏ nút BẢO VỆ LỆNH/NHẬN/BỎ QUẢN LÝ khỏi bảng,
  chọn dòng rồi mở RULE → E/M để nhận/bỏ quyền BOT. Backend chỉ nhận tham số tín hiệu qua pipe, không nhận tài khoản/OTP.
- Giá đóng DNSE từ 14:45 cùng ngày được hiện tham chiếu cuối phiên: ĐÓNG PHIÊN,
  EMA/RSI đã tính và thị trường so MA200, kèm giờ giá. Không cấp điểm LONG mới,
  không cập nhật giao cắt/xác nhận hay độ mới giao dịch từ tham chiếu này.
  Màu UP/Long xanh, DOWN đỏ, CHỜ/đóng phiên vàng; trạng thái nguồn đóng phiên xanh nhạt.
  LONG/SHORT bị khóa phải hiện lý do ngay dưới nút; PAPER vẫn chờ giá DNSE mới,
  không dùng giá đóng phiên/cache làm giá mới để khớp lệnh.
- Chọn PAPER/REAL không tự mở KẾT NỐI. REAL xác minh tài khoản/gói qua GET worker;
  thiếu cấu hình hoặc nhiều lựa chọn thì báo ngay MAIN, giữ sổ cũ. Bỏ kết quả cũ
  khi đổi ý/kết nối; chỉ dừng sổ cũ sau khi xác minh, sổ mới luôn BOT OFF.
- GET số dư/sức mở không cần OTP; không gộp quyền đọc với token giao dịch.
  Sổ lệnh đọc NORMAL, pageIndex từ 0, pageSize 100, đủ mọi trang mới đối soát.
  Số dư đã đọc được vẫn hiện khi endpoint khác lỗi; không cấp sức mở từ snapshot thiếu.
- Thay đổi tiền/vị thế/lệnh cần kiểm thử có ý nghĩa trong `support/tests/`.
  Test offline chặn mạng; không gửi lệnh thật hoặc Telegram để thử.
- `../RAT-CKVN-reference/sources/` chỉ đối chiếu local, không import và không đưa vào gói bán.
  Dữ liệu tài khoản, credentials, `.artifacts/` nằm ngoài Git.
- Nghiệp vụ tại `support/docs/`; script/ảnh tạm tại `.artifacts/`, không sinh
  báo cáo theo ngày trong source.
