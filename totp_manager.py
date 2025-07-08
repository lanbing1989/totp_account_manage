import os
import json
import time
import base64
import pyotp
import tkinter as tk
from tkinter import ttk, messagebox, simpledialog, filedialog
from pyzbar.pyzbar import decode
from PIL import Image
from urllib.parse import urlparse, parse_qs, unquote

DATA_FILE = "totp_accounts.json"

def load_accounts():
    if not os.path.isfile(DATA_FILE):
        return []
    try:
        with open(DATA_FILE, "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return []

def save_accounts(accounts):
    with open(DATA_FILE, "w", encoding="utf-8") as f:
        json.dump(accounts, f, ensure_ascii=False, indent=2)

def parse_otpauth_url(url):
    if not url.startswith("otpauth://totp/"):
        return None
    url = url.replace("otpauth://totp/", "")
    if "?" not in url:
        return None
    label, params = url.split("?", 1)
    label = unquote(label)
    qs = parse_qs(params)
    secret = qs.get("secret", [""])[0]
    issuer = qs.get("issuer", [""])[0]
    name = label
    if ":" in label:
        name = label.split(":", 1)[1]
    return {"name": name, "secret": secret, "note": issuer}

def scan_qr_image(image_path):
    try:
        img = Image.open(image_path)
        decoded = decode(img)
        if not decoded:
            return None
        data = decoded[0].data.decode()
        if data.startswith("otpauth://totp/"):
            return parse_otpauth_url(data)
        elif data.startswith("otpauth-migration://"):
            return {"migration_url": data}
        return None
    except Exception:
        return None

def parse_otpauth_migration_url(url):
    qs = urlparse(url)
    data = parse_qs(qs.query).get("data", [None])[0]
    if not data:
        return []
    payload = base64.urlsafe_b64decode(data + '=' * (-len(data) % 4))
    return parse_migration_payload(payload)

def parse_migration_payload(payload_bytes):
    accounts = []
    def read_varint(data, idx):
        shift = 0
        result = 0
        while True:
            b = data[idx]
            result |= ((b & 0x7F) << shift)
            idx += 1
            if not (b & 0x80):
                return result, idx
            shift += 7
    idx = 0
    end = len(payload_bytes)
    otp_list = []
    def read_length_delim(data, idx):
        size, idx = read_varint(data, idx)
        val = data[idx:idx+size]
        return val, idx+size
    while idx < end:
        tag = payload_bytes[idx]
        idx += 1
        field_num = tag >> 3
        wire_type = tag & 0x7
        if field_num == 1 and wire_type == 2:
            val, idx = read_length_delim(payload_bytes, idx)
            otp_list.append(val)
        else:
            if wire_type == 0:
                _, idx = read_varint(payload_bytes, idx)
            elif wire_type == 2:
                size, idx = read_varint(payload_bytes, idx)
                idx += size
            else:
                return []
    for otp in otp_list:
        param_idx = 0
        param_end = len(otp)
        secret = b""
        name = ""
        issuer = ""
        while param_idx < param_end:
            tag = otp[param_idx]
            param_idx += 1
            field_num = tag >> 3
            wire_type = tag & 0x7
            if field_num == 1 and wire_type == 2:
                val, param_idx = read_length_delim(otp, param_idx)
                secret = val
            elif field_num == 2 and wire_type == 2:
                val, param_idx = read_length_delim(otp, param_idx)
                name = val.decode(errors="ignore")
            elif field_num == 5 and wire_type == 2:
                val, param_idx = read_length_delim(otp, param_idx)
                issuer = val.decode(errors="ignore")
            else:
                if wire_type == 0:
                    _, param_idx = read_varint(otp, param_idx)
                elif wire_type == 2:
                    size, param_idx = read_varint(otp, param_idx)
                    param_idx += size
                else:
                    break
        if secret:
            secret_b32 = base64.b32encode(secret).decode("utf-8").replace('=', '')
            accounts.append({
                "name": name,
                "secret": secret_b32,
                "note": issuer
            })
    return accounts

class CodeWindow(tk.Toplevel):
    def __init__(self, master, account_info, on_edit_note, on_delete, width=520):
        super().__init__(master)
        self.title(f"验证码 - {account_info['name']}")
        self.configure(bg="#f3f1ee")
        self.resizable(False, False)
        self.account_info = account_info
        self.secret = account_info["secret"]
        self.on_edit_note = on_edit_note
        self.on_delete = on_delete
        self.current_code = ""
        self.copied_label = None
        self.win_width = width
        self.win_height = 370

        main_frame = ttk.Frame(self, padding=24)
        main_frame.pack(fill=tk.BOTH, expand=True)
        ttk.Label(main_frame, text=f"账号: {account_info['name']}", font=("微软雅黑", 16)).pack(pady=(0, 10))

        note_frame = ttk.Frame(main_frame)
        note_frame.pack(pady=(0, 12))
        self.label_note = ttk.Label(note_frame, text=f"备注: {account_info.get('note','') or '无'}", font=("微软雅黑", 13), foreground="#888")
        self.label_note.pack(side=tk.LEFT)
        self.btn_note = ttk.Button(note_frame, text="编辑备注", command=self.edit_note, width=12)
        self.btn_note.pack(side=tk.LEFT, padx=12)

        self.label_code = ttk.Label(main_frame, text="------", font=("Consolas", 54, "bold"), foreground="#1976d2")
        self.label_code.pack(pady=(0, 16))
        self.label_timer = ttk.Label(main_frame, text="倒计时: -- 秒", font=("微软雅黑", 16))
        self.label_timer.pack(pady=(0, 16))

        btns = ttk.Frame(main_frame)
        btns.pack(pady=10)
        ttk.Button(btns, text="复制", command=self.copy_code, style="Accent.TButton", width=14).pack(side=tk.LEFT, padx=16, ipadx=14, ipady=4)
        ttk.Button(btns, text="删除", command=self.delete_account, width=14).pack(side=tk.LEFT, padx=16, ipadx=14, ipady=4)

        self.update_code()
        self.set_right_side(self.win_width, self.win_height)

    def set_right_side(self, width=520, height=370):
        self.update_idletasks()
        sw = self.winfo_screenwidth()
        sh = self.winfo_screenheight()
        x = sw - width - 40
        y = int((sh - height) / 2)
        self.geometry(f"{width}x{height}+{x}+{y}")

    def edit_note(self):
        new_note = simpledialog.askstring("编辑备注", "请输入备注：", initialvalue=self.account_info.get("note", ""))
        if new_note is not None:
            self.account_info["note"] = new_note
            self.label_note.config(text=f"备注: {new_note or '无'}")
            self.on_edit_note(self.account_info, new_note)

    def delete_account(self):
        if messagebox.askyesno("删除确认", f"确定要删除账号: {self.account_info['name']}?"):
            self.on_delete(self.account_info)
            self.destroy()

    def copy_code(self):
        code = self.current_code
        if code:
            self.clipboard_clear()
            self.clipboard_append(code)
            if self.copied_label:
                self.copied_label.destroy()
            self.copied_label = ttk.Label(self, text="已复制!", font=("微软雅黑", 14), foreground="green", background="#f3f1ee")
            self.copied_label.place(relx=0.5, rely=0.90, anchor="center")
            self.after(1200, lambda: self.copied_label.destroy())

    def update_code(self):
        try:
            now = int(time.time())
            totp = pyotp.TOTP(self.secret)
            code = totp.now()
            seconds_left = 30 - (now % 30)
        except Exception:
            code = "ERROR"
            seconds_left = "--"
        self.current_code = code
        self.label_code.config(text=code)
        self.label_timer.config(text=f"倒计时: {seconds_left} 秒")
        self.after(1000, self.update_code)

class TOTPAccountApp:
    def __init__(self, root):
        self.root = root
        self.root.title("TOTP 多账号管理器")
        bg_color = "#fff"
        self.root.configure(bg=bg_color)
        self.root.geometry("520x640")
        self.set_right_side(520, 640)
        style = ttk.Style(self.root)
        style.theme_use('clam')
        style.configure("Treeview", font=("微软雅黑", 13), rowheight=36, background=bg_color, fieldbackground=bg_color, foreground="#222")
        style.configure("Treeview.Heading", font=("微软雅黑", 14, "bold"), background=bg_color, foreground="#222")
        style.configure("Accent.TButton", foreground="white", background="#1976d2")

        # grid布局
        self.root.grid_rowconfigure(0, weight=1)
        self.root.grid_rowconfigure(1, weight=0)
        self.root.grid_columnconfigure(0, weight=1)

        # 主内容Frame
        main_frame = ttk.Frame(self.root)
        main_frame.grid(row=0, column=0, sticky='nsew')

        frm_top = ttk.Frame(main_frame, padding=(14, 14, 14, 0))
        frm_top.pack(fill=tk.X)
        ttk.Button(frm_top, text="导入二维码", command=self.import_qrcode).pack(side=tk.LEFT, padx=(0, 10))
        ttk.Button(frm_top, text="新增账号", command=self.add_account).pack(side=tk.LEFT, padx=(0, 10))
        ttk.Button(frm_top, text="刷新账号列表", command=self.refresh_accounts).pack(side=tk.LEFT, padx=(0, 10))

        frm_table = ttk.Frame(main_frame, padding=(14, 8, 14, 6))
        frm_table.pack(fill=tk.BOTH, expand=True)
        self.tree = ttk.Treeview(frm_table, columns=("name","note"), show="headings", height=16, style="Treeview")
        self.tree.heading("name", text="账号")
        self.tree.heading("note", text="备注")
        self.tree.column("name", width=220, anchor="center")
        self.tree.column("note", width=220, anchor="center")
        vsb = ttk.Scrollbar(frm_table, orient="vertical", command=self.tree.yview)
        self.tree.configure(yscrollcommand=vsb.set)
        self.tree.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        vsb.pack(side=tk.RIGHT, fill=tk.Y)
        self.tree.bind("<Double-1>", self.show_code_window)

        self.accounts = load_accounts()
        self.reload_treeview()

        # 版权信息（单独一行，直接grid到root）
        copyright_label = ttk.Label(
            self.root,
            text="© 2025 灯火通明（济宁）网络有限公司",
            font=("微软雅黑", 11),
            foreground="#1976d2",
            anchor="center"
        )
        copyright_label.grid(row=1, column=0, sticky='ew', pady=(0, 6))

    def set_right_side(self, width=520, height=640):
        self.root.update_idletasks()
        sw = self.root.winfo_screenwidth()
        sh = self.root.winfo_screenheight()
        x = sw - width - 40
        y = int((sh - height) / 2)
        self.root.geometry(f"{width}x{height}+{x}+{y}")

    def reload_treeview(self):
        for item in self.tree.get_children():
            self.tree.delete(item)
        for acc in self.accounts:
            self.tree.insert("", tk.END, values=(acc["name"], acc.get("note","")))

    def refresh_accounts(self):
        self.accounts = load_accounts()
        self.reload_treeview()
        messagebox.showinfo("提示", "账号列表已刷新")

    def add_account(self):
        name = simpledialog.askstring("账号名称", "请输入账号名称:")
        if not name:
            return
        secret = simpledialog.askstring("TOTP密钥", "请输入TOTP密钥（Base32，比如JBSWY3DPEHPK3PXP）:")
        if not secret:
            return
        note = simpledialog.askstring("备注（可选）", "请输入备注信息（如邮箱/平台）:")
        if not secret.strip().replace(" ", "").isalnum():
            messagebox.showerror("错误", "密钥格式不正确，请输入Base32字符。")
            return
        account = {"name": name.strip(), "secret": secret.strip().replace(" ", ""), "note": note or ""}
        self.accounts.append(account)
        save_accounts(self.accounts)
        self.reload_treeview()

    def import_qrcode(self):
        file_path = filedialog.askopenfilename(
            title="选择二维码图片",
            filetypes=[("图片文件", "*.png *.jpg *.jpeg *.bmp *.gif"), ("All Files", "*.*")]
        )
        if not file_path:
            return
        result = scan_qr_image(file_path)
        if not result:
            messagebox.showerror("错误", "二维码识别失败，或非标准二维码")
            return

        if result.get("secret"):
            for acc in self.accounts:
                if acc["name"] == result["name"] and acc["secret"] == result["secret"]:
                    messagebox.showinfo("提示", f"该账号已存在：{result['name']}")
                    return
            note = simpledialog.askstring("备注", "请输入备注信息（如邮箱/平台）：", initialvalue=result.get("note", ""))
            result["note"] = note or result.get("note", "")
            msg = f"识别到账号：\n 账号名称: {result['name']}\n 备注: {result['note']}\n Secret: {result['secret'][:6]}...{result['secret'][-3:]}\n\n是否导入？"
            if messagebox.askyesno("确认导入", msg):
                self.accounts.append(result)
                save_accounts(self.accounts)
                self.reload_treeview()
                messagebox.showinfo("成功", f"导入成功：{result['name']}")
            return

        if result.get("migration_url"):
            accounts = parse_otpauth_migration_url(result["migration_url"])
            if not accounts:
                messagebox.showerror("错误", "批量迁移二维码解码失败")
                return
            to_add = []
            existed = []
            for acc in accounts:
                duplicate = False
                for old in self.accounts:
                    if old["name"] == acc["name"] and old["secret"] == acc["secret"]:
                        duplicate = True
                        break
                if duplicate:
                    existed.append(acc["name"])
                else:
                    note = simpledialog.askstring("备注", f"为账号 “{acc['name']}” 输入备注信息：", initialvalue=acc.get("note", ""))
                    acc["note"] = note or acc.get("note", "")
                    to_add.append(acc)
            msg = f"识别到{len(accounts)}个账号。\n将导入{len(to_add)}个新账号。\n"
            if existed:
                msg += f"已存在账号: {', '.join(existed)}\n"
            msg += "\n是否导入？"
            if not to_add:
                messagebox.showinfo("提示", "二维码中所有账号都已存在，无需导入。")
                return
            if messagebox.askyesno("确认批量导入", msg):
                self.accounts.extend(to_add)
                save_accounts(self.accounts)
                self.reload_treeview()
                messagebox.showinfo("成功", f"成功导入{len(to_add)}个账号！")
            return

        messagebox.showerror("错误", "二维码内容无法识别为支持的账号数据。")

    def show_code_window(self, event):
        selected = self.tree.selection()
        if not selected:
            return
        item = selected[0]
        values = self.tree.item(item, "values")
        name = values[0]
        for acc in self.accounts:
            if acc["name"] == name:
                CodeWindow(self.root, acc, self.edit_note, self.delete_account, width=520)
                break

    def delete_account(self, account):
        self.accounts = [a for a in self.accounts if not (a["name"] == account["name"] and a["secret"] == account["secret"])]
        save_accounts(self.accounts)
        self.reload_treeview()

    def edit_note(self, account, new_note):
        for acc in self.accounts:
            if acc["name"] == account["name"] and acc["secret"] == account["secret"]:
                acc["note"] = new_note
        save_accounts(self.accounts)
        self.reload_treeview()

if __name__ == "__main__":
    root = tk.Tk()
    app = TOTPAccountApp(root)
    root.mainloop()