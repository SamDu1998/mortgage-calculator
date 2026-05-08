import ctypes
import sys
import tkinter as tk
from tkinter import ttk, messagebox
import matplotlib
matplotlib.use('TkAgg')
import matplotlib.font_manager as fm
from matplotlib.figure import Figure
from matplotlib.backends.backend_tkagg import FigureCanvasTkAgg
from calc import (calc_by_monthly_payment, calc_by_house_price,
                  find_perfect_house_price, simulate_payoff)

# --- Windows 高DPI适配 ---
if sys.platform == 'win32':
    try:
        ctypes.windll.shcore.SetProcessDpiAwareness(1)
    except Exception:
        try:
            ctypes.windll.user32.SetProcessDPIAware()
        except Exception:
            pass

# --- matplotlib 中文字体 ---
_CN_FONT = None
for name in ['Microsoft YaHei', 'SimHei', 'Microsoft JhengHei', 'WenQuanYi Micro Hei']:
    matches = fm.findSystemFonts()
    if any(name.lower().replace(' ', '') in f.lower().replace(' ', '') for f in matches):
        _CN_FONT = name
        break

if _CN_FONT:
    matplotlib.rcParams['font.sans-serif'] = [_CN_FONT, 'DejaVu Sans']
    matplotlib.rcParams['axes.unicode_minus'] = False

CN = bool(_CN_FONT)
TARGET_YEARS_OPTIONS = [5, 8, 10, 12, 15, 20]

# --- 图表对象 ---
figure = Figure(facecolor='#2C3E50')
ax = figure.add_subplot(111)
ax.set_facecolor('#34495E')

# 防抖 resize
_resize_after_id = None


def _on_resize(event):
    global _resize_after_id
    if _resize_after_id:
        root.after_cancel(_resize_after_id)
    _resize_after_id = root.after(150, _do_resize)


def _do_resize():
    w = canvas_widget.winfo_width()
    h = canvas_widget.winfo_height()
    if w > 100 and h > 60:
        figure.set_size_inches(w / figure.get_dpi(), h / figure.get_dpi())
        figure.tight_layout()
        canvas.draw_idle()


def _t(cn_text, en_text):
    return cn_text if CN else en_text


def toggle_mode(*args):
    if mode_var.get() == "按月供":
        entry_cash_pmt.config(state="normal")
        entry_house_price.config(state="disabled")
    else:
        entry_cash_pmt.config(state="disabled")
        entry_house_price.config(state="normal")
    calculate_mortgage()


def update_chart(months, rp_wan, savings_wan, target_years):
    ax.clear()
    ax.set_facecolor('#34495E')

    ax.plot(months, rp_wan, linewidth=2, color='#E74C3C',
            label=_t('剩余贷款', 'Remaining Loan'))
    ax.plot(months, savings_wan, linewidth=2, color='#2ECC71',
            label=_t('累计可支配收入', 'Cumulative Savings'))

    tm = target_years * 12
    if tm <= months[-1]:
        ax.axvline(x=tm, color='#F1C40F', linestyle='--', linewidth=1.3,
                   label=_t(f'{target_years}年目标', f'{target_years}yr Target'), zorder=3)

    ax.set_xlabel(_t('月份', 'Month'), fontsize=9, color='#ECF0F1')
    ax.set_ylabel(_t('金额(万元)', 'Amount (10k)'), fontsize=9, color='#ECF0F1')
    ax.set_title(_t('剩余贷款 vs 累计可支配收入', 'Remaining Loan vs Savings'),
                 fontsize=11, color='#ECF0F1')
    ax.legend(fontsize=8, loc='center right', framealpha=0.8,
              facecolor='#34495E', edgecolor='#7F8C8D', labelcolor='#ECF0F1')
    ax.grid(True, alpha=0.2, color='#7F8C8D')
    ax.tick_params(colors='#BDC3C7', labelsize=8)

    figure.tight_layout()
    canvas.draw_idle()


def calculate_mortgage(event=None):
    try:
        income = float(entry_income.get())
        expenses = float(entry_expenses.get())
        cpf_pmt = float(entry_cpf_pmt.get())
        rate = float(entry_rate.get())
        dp_ratio = float(entry_dp_ratio.get())
        target_years = int(combo_target_years.get())
        mode = mode_var.get()

        lbl_savings_result.config(
            text=f"收入-开销: {income - expenses:.0f} 元/月"
        )

        # --- 完美卡点房价 ---
        target_price, target_gap = find_perfect_house_price(
            income, expenses, cpf_pmt, rate, dp_ratio, target_years)

        if target_price is not None:
            if mode == "按月供":
                entry_house_price.config(state="normal")
                entry_house_price.delete(0, tk.END)
                entry_house_price.insert(0, f"{target_price / 10000:.2f}")
                entry_house_price.config(state="disabled")
            gt = "≈0" if abs(target_gap) < 100 else f"{target_gap / 10000:.2f}万"
            lbl_target.config(
                text=f"{target_years}年刚好结清房价: {target_price / 10000:.2f}万 (闲钱: {gt})",
                fg="#27AE60")
        else:
            lbl_target.config(
                text=f"{target_years}年完美卡点: 无法达成", fg="#E74C3C")

        # --- 确定房价 ---
        if mode == "按月供":
            hp = target_price if target_price else 0
            cash = float(entry_cash_pmt.get())
        else:
            hp = float(entry_house_price.get()) * 10000
            cash = None

        # --- 表格 + 缓存30年结果 ---
        for item in tree.get_children():
            tree.delete(item)

        chart_r = None
        for years in [10, 15, 20, 25, 30]:
            if mode == "按月供":
                r = calc_by_monthly_payment(income, expenses, cash, cpf_pmt,
                                            rate, dp_ratio, years, target_years)
            else:
                r = calc_by_house_price(income, expenses, hp, rate, dp_ratio,
                                        years, cpf_pmt, target_years)

            tree.insert("", tk.END, values=(
                f"{years}年",
                f"{r['house_price'] / 10000:.1f}万",
                f"{r['loan_amount'] / 10000:.1f}万",
                f"{r['total_pmt']:.0f}元",
                f"{r['remaining_principal'] / 10000:.1f}万",
                r['status'],
                r['remark'],
            ), tags=(r['tag'],))

            if years == 30:
                chart_r = r

        # --- 图表：直接用表格30年行的数据 ---
        if chart_r and chart_r['raw_savings'] >= 0:
            mr = rate / 100 / 12
            tl = simulate_payoff(chart_r['loan_amount'], mr, 360,
                                 chart_r['raw_savings'])
            update_chart(
                tl['months'],
                [v / 10000 for v in tl['remaining_principal']],
                [v / 10000 for v in tl['cumulative_savings']],
                target_years)

    except ValueError:
        messagebox.showerror("输入错误", "请输入有效的数字！")


# ========== UI ==========

root = tk.Tk()
root.title("买房结清·动态推算器")
root.geometry("1100x750")
root.configure(padx=20, pady=20)

style = ttk.Style()
style.configure("TLabel", font=("Arial", 10))
style.configure("TButton", font=("Arial", 11, "bold"))
style.configure("Treeview.Heading", font=("Arial", 9, "bold"))
style.configure("Treeview", font=("Arial", 9), rowheight=28)

# 指引
frame_guide = ttk.LabelFrame(root, text=" 使用指引 ", padding=(10, 8))
frame_guide.pack(fill="x", pady=(0, 10))
tk.Label(frame_guide, font=("Arial", 9), justify="left", fg="#2C3E50", anchor="w",
         text="① 填写财务参数 → ② 选择目标结清年限 → ③ 选择「按月供」或「按房价」模式\n"
              "④ 表格展示各贷款年限的测算结果 → ⑤ 图表展示30年贷款的剩余贷款与累计可支配收入变化"
).pack(fill="x")

# 输入区
frame_inputs = ttk.LabelFrame(root, text=" 财务参数 ", padding=(10, 10))
frame_inputs.pack(fill="x", pady=(0, 10))

ttk.Label(frame_inputs, text="目标结清年限:").grid(row=0, column=0, sticky="e", padx=(10, 2))
combo_target_years = ttk.Combobox(frame_inputs, values=TARGET_YEARS_OPTIONS,
                                   width=5, state="readonly")
combo_target_years.set(10)
combo_target_years.grid(row=0, column=1, sticky="w", padx=(0, 15))
combo_target_years.bind("<<ComboboxSelected>>", calculate_mortgage)

ttk.Label(frame_inputs, text="计算模式:").grid(row=0, column=6, sticky="e", padx=(10, 5))
mode_var = tk.StringVar(value="按月供")
ttk.Radiobutton(frame_inputs, text="按月供", variable=mode_var,
                value="按月供", command=toggle_mode).grid(row=0, column=7, sticky="w", padx=(0, 10))
ttk.Radiobutton(frame_inputs, text="按房价", variable=mode_var,
                value="按房价", command=toggle_mode).grid(row=0, column=8, sticky="w")

labels = ["税后月薪:", "日常开销:", "公积金月供:", "综合利率(%):",
          "首付比例(%):", "现金月供:", "目标房价(万):"]
defaults = ["15500", "5000", "5000", "3.0", "30", "2000", "100"]
entries = []
for i in range(7):
    r, c = (i + 1) // 3, (i % 3) * 2
    ttk.Label(frame_inputs, text=labels[i]).grid(row=r, column=c, sticky="e", padx=(10, 2), pady=5)
    e = ttk.Entry(frame_inputs, width=12)
    e.insert(0, defaults[i])
    e.grid(row=r, column=c + 1, sticky="w", padx=(0, 15), pady=5)
    entries.append(e)

(entry_income, entry_expenses, entry_cpf_pmt, entry_rate,
 entry_dp_ratio, entry_cash_pmt, entry_house_price) = entries

for e in entries:
    e.bind("<KeyRelease>", calculate_mortgage)
    e.bind("<FocusOut>", calculate_mortgage)
entry_house_price.config(state="disabled")

# 提示
lbl_target = tk.Label(root, text="正在计算...", font=("Arial", 11, "bold"), fg="#27AE60")
lbl_target.pack(pady=(0, 3))
lbl_savings_result = tk.Label(root, text="", font=("Arial", 10), fg="#D35400")
lbl_savings_result.pack(pady=(0, 8))

# 表格
cols = ("years", "price", "loan", "pmt", "remain", "status", "remark")
tree = ttk.Treeview(root, columns=cols, show="headings", height=5)
tree.pack(fill="x", pady=(0, 10))

for col, text, w in zip(cols,
        ["贷款年限", "房屋总价", "初始贷款", "月供", "目标年末剩余本金", "结清判定", "备注"],
        [70, 85, 85, 80, 120, 110, 240]):
    tree.heading(col, text=text)
    tree.column(col, width=w, anchor="center")

tree.tag_configure('success', foreground='green')
tree.tag_configure('perfect', foreground='purple', font=("Arial", 10, "bold"))
tree.tag_configure('fail', foreground='red')

# 图表
canvas = FigureCanvasTkAgg(figure, master=root)
canvas_widget = canvas.get_tk_widget()
canvas_widget.pack(fill="both", expand=True)
canvas_widget.bind("<Configure>", _on_resize)

calculate_mortgage()
root.mainloop()
