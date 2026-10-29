from __future__ import annotations

from ckps.models import FINAL, ExitSettings, Position, load_record
from .formatting import money, price, clock
from .theme import MUTED, GREEN, RED, WARN
from .mayin.tokens import COL_TEXT as TEXT
from .mayin.market_table import MarketTable
from .mayin.preview_state import preview_state, TONES

STATUS_LABELS = {"CREATED": "ĐÃ XẾP", "SUBMITTING": "ĐANG GỬI", "WORKING": "CHỜ KHỚP",
    "PARTIAL": "KHỚP MỘT PHẦN", "UNKNOWN": "CHƯA RÕ", "CANCEL_PENDING": "CHỜ HỦY",
    "REPLACE_PENDING": "CHỜ SỬA", "FILLED": "KHỚP ĐỦ", "CANCELLED": "ĐÃ HỦY",
    "REJECTED": "TỪ CHỐI", "EXPIRED": "HẾT HIỆU LỰC", "FAILED": "LỖI"}
REASON_LABELS = {"MANUAL":"ĐẶT TAY", "SL":"CẮT LỖ", "TP":"CHỐT LỜI", "ARM":"SAU ARM", "DYN":"DYNAMIC"}


class DashboardTablesMixin:
    def _tree(self, parent, columns, *, hierarchy=False):
        tree = MarketTable(parent, columns, hierarchy=hierarchy,
            empty_text="Chưa có vị thế hoặc lệnh chờ" if hierarchy else "Chưa có lịch sử trong sổ này",
            compact=hierarchy)
        tree.pack(fill="both", expand=True, padx=1, pady=1)
        for key, label, width in columns:
            tree.column(key, anchor="e" if key in {"entry", "last", "pnl", "mae", "mfe", "sl", "tp", "price", "fees"}
                        else "center" if key in {"quantity", "side", "kind", "fill", "rsi"} else "w")
        tree.bind("<Control-c>", lambda _event: self.copy_row(tree))
        return tree

    def _running_tree(self, frame):
        tree = self._tree(frame, (("state", "TRẠNG THÁI", 100), ("side", "CHIỀU", 60), ("quantity", "HĐ", 55),
            ("entry", "GIÁ VÀO", 90), ("last", "GIÁ", 85), ("pnl", "PNL GIÁ", 115),
            ("sl", "SL", 75), ("tp", "TP", 75), ("protect", "PROTECT", 90), ("managed", "QL", 45),
            ("mae", "MAE ĐIỂM", 90), ("mfe", "MFE ĐIỂM", 90)), hierarchy=True)
        tree.configure(displaycolumns=("side", "entry", "sl", "tp", "managed"))
        tree.heading('side',text='CHIỀU / HĐ')
        tree.heading("entry",text="GIÁ VỐN / LO")
        tree.heading('managed',text='TRẠNG THÁI')
        for key,width,weight in (("#0",104,1),("side",94,0),("entry",100,1),("sl",82,1),("tp",82,1),("managed",136,1)):
            tree.column(key,minwidth=width,weight=weight)
        tree.bind("<<TreeviewSelect>>", lambda _event: self._sync_selection())
        tree.bind("<Double-1>", lambda _event: self._open_running_row())
        tree.bind("<<RowActivate>>", lambda _event: self._open_running_row())
        tree.bind("<Button-3>", self._running_context)
        return tree

    def copy_row(self, tree):
        selected = tree.selection()
        if selected:
            self.clipboard_clear()
            self.clipboard_append(tree.item(selected[0], "text") + "\t" + "\t".join(map(str, tree.item(selected[0], "values"))))

    def _render_running(self):
        tree = self.positions_tree
        present, roots = set(), set()
        all_items = set(tree.get_children(""))
        for item in list(all_items):
            all_items.update(tree.get_children(item))
        self.running_rows = {}
        def upsert(key, parent, text, values, tag):
            if tree.exists(key):
                tree.move(key, parent, "end")
                tree.item(key, text=text, values=values, tags=(tag,))
            else:
                tree.insert(parent, "end", iid=key, text=text, values=values, tags=(tag,), open=True)
            present.add(key)
        for raw in self.view.get("positions", []):
            p = load_record(Position, raw)
            last = self.view.get("quotes", {}).get(p.symbol, {}).get("last")
            pnl = p.pnl(last) if last else None
            levels = p.metrics.get("levels", {})
            state = "ĐANG GIỮ" if p.managed else "THEO DÕI"
            upsert(p.id, "", p.symbol, (state, p.side, p.quantity, price(p.entry), price(last), money(pnl),
                price(levels.get("sl")), price(levels.get("tp")), price(levels.get("protect")), "ON" if p.managed else "OFF",
                f"{min(0, p.sign * ((p.worst or p.entry) - p.entry)):+.1f}", f"{max(0, p.sign * ((p.best or p.entry) - p.entry)):+.1f}"),
                "profit" if pnl and pnl > 0 else "loss" if pnl and pnl < 0 else "flat")
            roots.add(p.id)
            self.running_rows[p.id] = ("positions", raw)
            rule=load_record(ExitSettings,p.exit_overrides or self.settings.exit)
            try:
                sl=price(p.entry-p.sign*rule.points(rule.sl_distance,p.entry,p.margin_per_contract)) if rule.sl_enabled else 'OFF'
                tp=price(p.entry+p.sign*rule.points(rule.tp_distance,p.entry,p.margin_per_contract)) if rule.tp_enabled else 'OFF'
            except ValueError:sl=tp='CHỜ KÝ QUỸ'
            management,tone=preview_state(self.view,self.settings.max_quote_age,p,rule,
                changing_book=bool(self.mode_requested or self.switch_pending))[1]
            tree.cell(p.id,"#0",detail='')
            tree.cell(p.id,"side",text=f'{p.side} · {p.quantity}',color=GREEN if p.side=="LONG" else RED)
            tree.cell(p.id,"quantity",numeric=True)
            tree.cell(p.id,"entry",numeric=True,detail='')
            tree.cell(p.id,'sl',text=sl if rule.sl_enabled else '—',numeric=True,color=RED if rule.sl_enabled else MUTED)
            tree.cell(p.id,'tp',text=tp if rule.tp_enabled else '—',numeric=True,color=GREEN if rule.tp_enabled else MUTED)
            tree.cell(p.id,'managed',text=management.removeprefix('QL · '),color=TONES[tone][2])
            tree.cell(p.id,"pnl",numeric=True,color=GREEN if pnl and pnl>0 else RED if pnl and pnl<0 else TEXT,
                      detail="Giá "+price(last))
            tree.cell(p.id,"protect",text="SL "+sl+" / TP "+tp,
                detail=(levels.get("stage","")+" "+price(levels["protect"])) if levels.get("protect") else "ARM / DYNAMIC —")
        for o in self.view.get("orders", []):
            if o["status"] in FINAL:
                continue
            parent = o["position_id"] if o["position_id"] in roots else ""
            label = "ĐÓNG" if o["action"] == "CLOSE" else "MỞ"
            upsert(o["id"], parent, label + " · " + (o["broker_id"][-8:] if parent and o["broker_id"] else o["symbol"]),
                (STATUS_LABELS.get(o["status"], o["status"]), o["side"], f"{o['filled']}/{o['quantity']}", price(o["price"]), price(o["avg_fill"]),
                 "--", "--", "--", "--" if o["reason"] == "MANUAL" else o["reason"], "TAY" if o["source"] == "MANUAL" else "BOT", "--", "--"), "unknown" if o["status"] == "UNKNOWN" else "pending")
            self.running_rows[o["id"]] = ("orders", o)
            state=STATUS_LABELS.get(o["status"],o["status"])
            alert_color=RED if o["status"]=="UNKNOWN" else WARN
            tree.cell(o["id"],"#0",text=label+" · "+(o["kind"] if parent else o["symbol"]),detail=state,detail_color=alert_color)
            tree.cell(o["id"],"side",text=f"{o['side']} · {o['filled']}/{o['quantity']}",color=GREEN if o["side"]=="LONG" else RED)
            tree.cell(o["id"],"quantity",numeric=True)
            tree.cell(o["id"],"entry",text=price(o["price"]) if o["kind"]=="LO" else o["kind"],numeric=o["kind"]=="LO",detail="Giá LO" if o["kind"]=="LO" else "Lệnh thị trường")
            tree.cell(o["id"],"pnl",text="—",detail="Khớp @ "+price(o["avg_fill"]))
            tree.cell(o["id"],"protect",text=REASON_LABELS.get(o["reason"],o["reason"]),detail="ID "+o["broker_id"][-8:] if o["broker_id"] else "Chưa có ID broker",color=alert_color)
            tree.cell(o['id'],'sl',text='—',color=MUTED)
            tree.cell(o['id'],'tp',text='—',color=MUTED)
            tree.cell(o['id'],'managed',text='KHỚP 1 PHẦN' if o['status']=='PARTIAL' else state,color=alert_color)
        for key in all_items - present:
            if tree.exists(key):
                tree.delete(key)
        self._sync_selection()
        if hasattr(self,"running_count"):
            self.running_count.configure(text=f"{len(roots)} vị thế · {sum(o['status'] not in FINAL for o in self.view.get('orders',[]))} lệnh chờ")

    def _sync_selection(self):
        if not hasattr(self, "action_bar"):
            return
        selected = self.positions_tree.selection()
        row = self.running_rows.get(selected[0]) if selected else None
        position = row[1] if row and row[0] == "positions" else None
        order = row[1] if row and row[0] == "orders" else None
        reserved = sum(o["quantity"] - o["filled"] for o in self.view.get("orders", [])
            if position and o.get("position_id") == position["id"] and o["action"] == "CLOSE" and o["status"] not in FINAL)
        enabled = {"close":bool(position and position["quantity"] > reserved),
                   "cancel":bool(order and order["broker_id"] and order["status"] in {"WORKING", "PARTIAL"}),
                   "edit":bool(order and order["kind"] == "LO" and order["broker_id"] and order["status"] in {"WORKING", "PARTIAL"}),
                   "reconcile":bool(order and order["status"] == "UNKNOWN")}
        for key, button in self.action_buttons.items():
            button.pack_forget()
            button.configure(state="normal" if enabled[key] else "disabled")
            if enabled[key]:
                button.pack(side="right", padx=3, pady=3)
        if row:
            self.action_bar.grid()
        else:
            self.action_bar.grid_remove()
        self._refresh_ticket_preview()



    def _running_context(self, event):
        row = self.positions_tree.identify_row(event.y)
        if row:
            event.widget.selection_set(row)
            self._sync_selection()


    def _open_running_row(self):
        selected = self.positions_tree.selection()
        row = self.running_rows.get(selected[0]) if selected else None
        if row:
            self.position_exit() if row[0] == "positions" else self.edit_order()

    def _fill_tree(self, tree, rows):
        existing = set(tree.get_children())
        for key, values, tag in rows:
            if tree.exists(key):
                tree.item(key, values=values, tags=(tag,))
            else:
                tree.insert("", "end", iid=key, values=values, tags=(tag,))
            existing.discard(key)
        for key in existing:
            tree.delete(key)

    def _render_history(self):
        if not hasattr(self, "history_tree") or not self.history_tree.winfo_exists():
            return
        self._fill_tree(self.history_tree, [(p["id"], (clock(p["closed_at"]), p["symbol"], p["side"], p["original_quantity"],
            price(p["entry"]), money(p["realized"] - p["fees"]) if p["pnl_verified"] else "CHƯA XÁC MINH", money(p["fees"]), p["source"]),
            "flat") for p in reversed(self.view.get("history", []))])
        self._fill_tree(self.order_history_tree, [(o["id"], (clock(o["created_at"]), o["symbol"], o["action"], o["side"], o["kind"],
            price(o["price"]), f"{o['filled']}/{o['quantity']}", o["status"], o["reason"]), "flat") for o in reversed(self.view.get("orders", []))])

        for raw in self.view.get("history",[]):
            key=raw["id"]
            pnl=raw["realized"]-raw["fees"]
            self._history_cells(self.history_tree,key,"closed",raw["side"])
            self.history_tree.cell(key,"pnl",numeric=raw["pnl_verified"],
                color=(GREEN if pnl>0 else RED if pnl<0 else TEXT) if raw["pnl_verified"] else WARN,
                detail="Sau phí đã ghi" if raw["pnl_verified"] else "Chờ đối chiếu")
            self.history_tree.cell(key,"entry",numeric=True)
            self.history_tree.cell(key,"fees",numeric=True,color=MUTED)
            self.history_tree.cell(key,"source",text={"APP":"APP","EXTERNAL":"DNSE","MIXED":"APP / DNSE"}.get(raw["source"],raw["source"]))
        for raw in self.view.get("orders",[]):
            key=raw["id"]
            self._history_cells(self.order_history_tree,key,"time",raw["side"])
            status=raw["status"]
            color=GREEN if status=="FILLED" else RED if status in {"UNKNOWN","REJECTED","FAILED"} else MUTED if status in FINAL else WARN
            self.order_history_tree.cell(key,"action",text="MỞ" if raw["action"]=="OPEN" else "ĐÓNG")
            self.order_history_tree.cell(key,"status",text=STATUS_LABELS.get(status,status),color=color)
            self.order_history_tree.cell(key,"reason",text=REASON_LABELS.get(raw["reason"],raw["reason"]),detail="" if raw["source"]=="MANUAL" else "BOT")
            self.order_history_tree.cell(key,"price",numeric=True)
            self.order_history_tree.cell(key,"fill",numeric=True,color=color)

    @staticmethod
    def _history_cells(tree,key,time_key,side=None):
        values=tree.item(key,"values")
        stamp=str(values[0]).split()
        tree.cell(key,time_key,text=stamp[-1],detail=stamp[0] if len(stamp)>1 else "")
        if side:
            tree.cell(key,"side",color=GREEN if side=="LONG" else RED)
            tree.cell(key,"quantity",numeric=True)
