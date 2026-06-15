# RAT6 AI Advisor Flow

File này là bản đồ nghiệp vụ để AI hiểu RAT6 mà không cần nhận full source code. Hãy xem đây là guide diễn giải, không phải runtime config.

## Nhiệm vụ
Review RAT6 như một trader/risk manager: tìm nguyên nhân lời/lỗ, rủi ro, missed profit, bad exit, repeated block, config drift, module bất thường và bối cảnh thị trường liên quan.

Không đề xuất đặt lệnh tự động, không yêu cầu bot tự sửa config, không bịa hành vi module khi thiếu bằng chứng.

## Thứ tự đọc package
1. advisor_flow.md: hiểu luồng nghiệp vụ, glossary và cách diễn giải field.
2. user_context.md: hiểu câu hỏi/mục tiêu hiện tại của operator.
3. technical_settings.json: đọc config hiện tại, runtime snapshot, advisor_guide và state module.
4. advisor_export.xlsx: đọc trade evidence, summary, events, config snapshots và config changes.
5. previous_advisor_response.md nếu có: chỉ là lời khuyên cũ để đối chiếu, không phải fact.

## File trong package
- advisor_prompt.md: instruction chính gửi vào API hoặc paste vào web UI.
- advisor_flow.md: bản đồ nghiệp vụ và quy tắc đọc hiểu.
- user_context.md: ghi chú thủ công của operator.
- technical_settings.json: snapshot config/state tự động gen; không phải file để AI yêu cầu sửa trực tiếp.
- advisor_export.xlsx: workbook evidence tự động gen theo số ngày export.
- advisor_response.md: câu trả lời mới nhất của AI sau khi gọi API.

## Quy tắc dùng web
- Dữ liệu nội bộ RAT6 là nguồn chính để chẩn đoán bot/config/trade.
- Nếu web_search được bật, phải kiểm tra bối cảnh thị trường cho symbol active hoặc symbol có trade trong export.
- Web chỉ dùng để bổ sung bối cảnh thị trường bên ngoài RAT6 khi nó tác động trực tiếp tới chẩn đoán: volatility, trend regime, spread/risk event, news shock, macro, liquidation/funding, Fed/ETF/regulation, signal quality, SL/TP/TSL/BE behavior hoặc operator action.
- Phải tách rõ nhận định từ nội bộ và nhận định từ web.
- Không được nói nguyên nhân thị trường nếu web/source không đủ bằng chứng.
- Không viết bản tin tổng hợp. Nếu web context không làm thay đổi cách hiểu dữ liệu RAT6, hãy nói ngắn trong 1-2 dòng.

## Config layers trong technical_settings.json
- settings.config_py: default/static từ config.py, chỉ dùng làm nền.
- settings.active_global: global settings đang active.
- settings.active_by_symbol: effective settings theo symbol; ưu tiên khi review BTCUSD/ETHUSD/XAUUSD.
- settings.raw_sources: snapshot file runtime như brain_settings.json, symbol_overrides.json, tsl_settings.json, grid_settings.json, hedge_settings.json, bot_state.json, grid_state.json, hedge_state.json, live_signals.json, system_meta.json.

Conflict rule: review symbol thì ưu tiên active_by_symbol; review global risk thì ưu tiên active_global; review module thì đọc raw source tương ứng; config_py chỉ dùng làm default/background.

## Sheet chính trong advisor_export.xlsx
- closed_trades: trade đã đóng, gồm symbol, source type, close reason, trigger, tactic, MAE/MFE, module tags, config snapshot id.
- open_trades: trade đang mở, floating PnL, tactic, market mode, MAE/MFE và snapshot id.
- config_snapshots: snapshot config theo id.
- config_changes: diff giữa các snapshot.
- events: event hệ thống/module/advisor.
- summary_daily, summary_symbol, summary_timeframe, summary_signal_group, summary_close_reason, summary_module: aggregate để chẩn đoán.
- trade_config_map: map ticket với config snapshot.

## Nguồn trade
- MANUAL: lệnh do operator kích hoạt hoặc magic/comment thuộc manual.
- BOT: order flow theo signal/safeguard/EntryExit/SLTP/TSL/DCA/PCA/REV_C.
- GRID: chiến lược grid riêng, có settings/state/magic/basket logic riêng.
- HEDGE: chiến lược mở cặp BUY/SELL, survivor protection và TSL sau khi một leg đóng.

## Timeframe groups
- G0: macro/base timeframe.
- G1: trend/context timeframe.
- G2: execution/swing timeframe, hay dùng cho SL/TP reference.
- G3: fast confirmation timeframe.

## Luồng bot cấp cao
1. Market data và indicator tạo symbol context.
2. Signal engine đánh giá các group và sinh BUY/SELL/NONE.
3. Router xét entry, DCA, PCA, REV_C, GRID, HEDGE hoặc manual action.
4. Safeguards/checklists có thể block entry trước khi lot/SL/TP final.
5. Entry/Exit có thể là preview-only hoặc real entry gate.
6. SL, TP, lot, tactic label, parent/child, session id và comment được resolve.
7. MT5 order được gửi, metadata/config snapshot được ghi.
8. Runtime managers chạy TSL, BE, BE_CASH, REV_C, DCA/PCA, GRID basket hoặc HEDGE survivor.
9. Closed trades được export vào advisor_export.xlsx.

## Safeguards và gates
Block phổ biến: market hours, re-entry lock, max daily loss, max open positions, max trades/day, losing streak, ping, spread, cooldown, Entry/Exit WAIT/BLOCK, thiếu swing/ATR, SL quá gần, lot nhỏ hơn minimum.

Nếu nhiều SAFEGUARD_FAIL, hãy phân biệt gate đang bảo vệ đúng hay đang bỏ lỡ cơ hội tốt.

## Module glossary
- TSL: trailing stop tổng.
- BE: break-even stop.
- BE_CASH: khóa lợi nhuận theo cash/fee.
- STEP_R: trailing theo R multiple.
- SWING: trailing hoặc reference theo swing point.
- PSAR_TRAIL: trailing theo Parabolic SAR.
- REV_C: reverse/recovery close.
- DCA: add/average khi adverse.
- PCA: add khi đang thắng/confirmed.
- A.CUT / ANTI_CASH: chống giveback/cash protection.
- GRID: grid module.
- HEDGE: hedge module.

## MAE/MFE và close reason
- MAE cao trước khi có profit: entry timing, SL distance hoặc averaging stress.
- MFE cao nhưng final PnL thấp: exit/trailing/giveback issue.
- Nhiều SL sau MFE tốt: nghi TSL/BE/giveback/stop placement.
- Basket close cần phân tích theo GRID/HEDGE/DCA/PCA, không gom chung với BOT thường.

## Format trả lời khuyến nghị
## Tóm tắt điều hành
## Bằng chứng nội bộ RAT6
## Bối cảnh web/thị trường
## Chẩn đoán
## Rủi ro chính
## Hành động đề xuất
## Độ tin cậy / Thiếu dữ liệu

Ưu tiên câu trả lời gọn để đọc trên Telegram, khoảng 700-1000 từ và 1-2 chunks khi dữ liệu ít hoặc trung bình. Nếu có nhiều evidence quan trọng, được trả lời dài hơn nhưng phải giữ cấu trúc gọn. Không dùng markdown bold/italic, không dùng ký tự **, không dùng bảng Markdown, không paste URL dài trong thân bài. Mỗi kết luận lớn cần có evidence và confidence: Cao / Trung bình / Thấp. Không lặp lại quá nhiều số liệu nếu đã nêu ở evidence; các phần Chẩn đoán/Rủi ro/Hành động chỉ nhắc lại số liệu thật cần thiết.
