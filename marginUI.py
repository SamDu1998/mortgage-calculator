import ctypes
import sys
import tkinter as tk
from tkinter import ttk, messagebox
from calc import calc_by_monthly_payment, calc_by_house_price, find_perfect_house_price

# --- Windows 高DPI适配（必须在创建 Tk 之前） ---
if sys.platform == 'win32':
    try:
        ctypes.windll.shcore.SetProcessDpiAwareness(1)
    except Exception:
        try:
            ctypes.windll.user32.SetProcessDPIAware()
        except Exception:
            pass

mode_var = None


def toggle_mode(*args):
    """切换计算模式时更新UI"""
    if mode_var.get() == "按月供":
        entry_cash_pmt.config(state="normal")
        entry_house_price.config(state="disabled")
    else:
        entry_cash_pmt.config(state="disabled")
        entry_house_price.config(state="normal")
    calculate_mortgage()


def calculate_mortgage(event=None):
    try:
        income = float(entry_income.get())
        expenses = float(entry_expenses.get())
        cpf_pmt = float(entry_cpf_pmt.get())
        rate = float(entry_rate.get())
        dp_ratio = float(entry_dp_ratio.get())
        extra_pmt = float(entry_extra_pmt.get() or 0)

        mode = mode_var.get()

        base_savings = income - expenses
        lbl_savings_result.config(
            text=f"收入-开销: {base_savings:.0f} 元/月（实际闲钱随月供变化，见表格）"
        )

        # --- 自动计算20年完美卡点的房价（gap≈0，一分不剩） ---
        target_price, target_gap = find_perfect_house_price(
            income, expenses, cpf_pmt, rate, dp_ratio, extra_pmt, target_years=20
        )

        if target_price is not None:
            # 更新目标房价输入框（仅在按月供模式下自动写入）
            if mode == "按月供":
                entry_house_price.config(state="normal")
                entry_house_price.delete(0, tk.END)
                entry_house_price.insert(0, f"{target_price / 10000:.2f}")
                entry_house_price.config(state="disabled")
            if abs(target_gap) < 100:
                gap_text = "≈0"
            else:
                gap_text = f"{target_gap / 10000:.2f}万"
            lbl_target.config(
                text=f"20年刚好结清房价: {target_price / 10000:.2f}万 (剩余闲钱: {gap_text})",
                fg="#27AE60"
            )
        else:
            lbl_target.config(text="20年完美卡点: 无法达成（闲钱不足以覆盖任何房价）", fg="#E74C3C")

        # --- 确定本次计算使用的房价 ---
        if mode == "按月供":
            if target_price is not None:
                house_price_for_calc = target_price
            else:
                house_price_for_calc = 0
            cash_pmt = float(entry_cash_pmt.get())
        else:
            house_price_for_calc = float(entry_house_price.get()) * 10000
            cash_pmt = None

        # --- 清空并填充表格 ---
        for item in tree.get_children():
            tree.delete(item)

        loan_years_list = [10, 15, 20, 25, 30]

        for years in loan_years_list:
            if mode == "按月供":
                r = calc_by_monthly_payment(income, expenses, cash_pmt, cpf_pmt,
                                            rate, dp_ratio, years, extra_pmt)
            else:
                r = calc_by_house_price(income, expenses, house_price_for_calc,
                                        rate, dp_ratio, years, cpf_pmt, extra_pmt)

            tree.insert("", tk.END, values=(
                f"{years} 年",
                f"{r['house_price'] / 10000:.1f} 万",
                f"{r['loan_amount'] / 10000:.1f} 万",
                f"{r['total_pmt'] / 10000:.2f} 万",
                f"{r['remaining_principal'] / 10000:.1f} 万",
                r['status'],
                r['remark'],
            ), tags=(r['tag'],))

    except ValueError:
        messagebox.showerror("输入错误", "请输入有效的数字！")


# --- UI 界面搭建 ---
root = tk.Tk()
root.title("10年结清·动态买房推算器")
root.geometry("1100x530")
root.configure(padx=20, pady=20)

style = ttk.Style()
style.configure("TLabel", font=("Arial", 10))
style.configure("TButton", font=("Arial", 11, "bold"))
style.configure("Treeview.Heading", font=("Arial", 9, "bold"))
style.configure("Treeview", font=("Arial", 9), rowheight=28)

frame_inputs = ttk.LabelFrame(root, text=" 你的财务现状与预期参数 ", padding=(10, 10))
frame_inputs.pack(fill="x", pady=(0, 10))

# 计算模式选择
ttk.Label(frame_inputs, text="计算模式:").grid(row=0, column=6, sticky="e", padx=(10, 5))
mode_var = tk.StringVar(value="按月供")
rb1 = ttk.Radiobutton(frame_inputs, text="按月供", variable=mode_var, value="按月供", command=toggle_mode)
rb2 = ttk.Radiobutton(frame_inputs, text="按房价", variable=mode_var, value="按房价", command=toggle_mode)
rb1.grid(row=0, column=7, sticky="w", padx=(0, 10))
rb2.grid(row=0, column=8, sticky="w")

# 参数输入字段
labels = ["税后月薪 (元):", "日常开销 (元/月):", "公积金月供 (元):", "综合利率 (%):",
          "首付比例 (%):", "现金月供 (元):", "目标房价 (万):", "额外月供 (元):"]
default_values = ["15500", "5000", "5000", "3.0", "30", "2000", "100", "0"]
entries = []

for i in range(8):
    row = (i + 1) // 3
    col = (i % 3) * 2
    ttk.Label(frame_inputs, text=labels[i]).grid(row=row, column=col, sticky="e", padx=(10, 2), pady=5)
    entry = ttk.Entry(frame_inputs, width=12)
    entry.insert(0, default_values[i])
    entry.grid(row=row, column=col + 1, sticky="w", padx=(0, 15), pady=5)
    entries.append(entry)

(entry_income, entry_expenses, entry_cpf_pmt, entry_rate,
 entry_dp_ratio, entry_cash_pmt, entry_house_price, entry_extra_pmt) = entries

for entry in entries:
    entry.bind("<KeyRelease>", calculate_mortgage)
    entry.bind("<FocusOut>", calculate_mortgage)

entry_house_price.config(state="disabled")

# 20年完美卡点房价提示
lbl_target = tk.Label(root, text="正在计算...", font=("Arial", 11, "bold"), fg="#27AE60")
lbl_target.pack(pady=(0, 5))

lbl_savings_result = tk.Label(root, text="点击测算查看你的10年闲钱储备", font=("Arial", 10), fg="#D35400")
lbl_savings_result.pack(pady=(0, 8))

columns = ("years", "total_price", "loan_amount", "monthly_pmt", "remain_principal", "status", "remark")
tree = ttk.Treeview(root, columns=columns, show="headings", height=6)
tree.pack(fill="both", expand=True)

headers = ["贷款年限", "房屋总价", "初始贷款", "月供", "第10年末剩余本金", "第10年结清判定", "备注"]
widths = [70, 85, 85, 80, 120, 110, 240]
for col, text, width in zip(columns, headers, widths):
    tree.heading(col, text=text)
    tree.column(col, width=width, anchor="center")

tree.tag_configure('success', foreground='green')
tree.tag_configure('perfect', foreground='purple', font=("Arial", 10, "bold"))
tree.tag_configure('fail', foreground='red')

calculate_mortgage()

root.mainloop()
