import ctypes
import sys
import tkinter as tk
from tkinter import ttk, messagebox
import matplotlib
matplotlib.use('TkAgg')
from matplotlib.figure import Figure
from matplotlib.backends.backend_tkagg import FigureCanvasTkAgg
from calc import (calc_by_monthly_payment, calc_by_house_price,
                  find_perfect_house_price, simulate_payoff,
                  monthly_payment)

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
TARGET_YEARS_OPTIONS = [5, 8, 10, 12, 15, 20]


def toggle_mode(*args):
    """切换计算模式时更新UI"""
    if mode_var.get() == "按月供":
        entry_cash_pmt.config(state="normal")
        entry_house_price.config(state="disabled")
    else:
        entry_cash_pmt.config(state="disabled")
        entry_house_price.config(state="normal")
    calculate_mortgage()


def update_chart(chart_data, target_years):
    """更新图表：各年限下的累计存款与剩余本金"""
    ax.clear()

    colors = ['#3498DB', '#2ECC71', '#E67E22', '#9B59B6', '#E74C3C']

    for i, d in enumerate(chart_data):
        months = d['months']
        rp = d['rp']
        savings = d['savings']
        years = d['years']
        net = [s - r for s, r in zip(savings, rp)]
        ax.plot(months, net, linewidth=1.8, color=colors[i % len(colors)],
                label=f'{years}年贷款')

    target_month = target_years * 12
    ax.axvline(x=target_month, color='#F1C40F', linestyle='--', linewidth=1.5,
               label=f'{target_years}年目标线', zorder=3)
    ax.axhline(y=0, color='#95A5A6', linestyle=':', linewidth=1, alpha=0.7)

    ax.set_xlabel('月份', fontsize=10, color='#ECF0F1')
    ax.set_ylabel('金额 (万元)', fontsize=10, color='#ECF0F1')
    ax.set_title('各年限净资金变化趋势 (存款 - 剩余贷款)', fontsize=11,
                 color='#ECF0F1', pad=10)

    ax.yaxis.set_major_formatter(
        matplotlib.ticker.FuncFormatter(lambda x, _: f'{x / 10000:.0f}'))
    ax.legend(fontsize=8, loc='upper left', framealpha=0.8, facecolor='#34495E',
              edgecolor='#7F8C8D', labelcolor='#ECF0F1')
    ax.grid(True, alpha=0.2, color='#7F8C8D')
    ax.tick_params(colors='#BDC3C7')

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

        base_savings = income - expenses
        lbl_savings_result.config(
            text=f"收入-开销: {base_savings:.0f} 元/月（实际闲钱随月供变化，见表格）"
        )

        # --- 自动计算完美卡点房价 ---
        target_price, target_gap = find_perfect_house_price(
            income, expenses, cpf_pmt, rate, dp_ratio, target_years=target_years
        )

        if target_price is not None:
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
                text=f"{target_years}年刚好结清房价: {target_price / 10000:.2f}万 (剩余闲钱: {gap_text})",
                fg="#27AE60"
            )
        else:
            lbl_target.config(
                text=f"{target_years}年完美卡点: 无法达成（闲钱不足以覆盖任何房价）",
                fg="#E74C3C"
            )

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
        chart_data = []

        for years in loan_years_list:
            if mode == "按月供":
                r = calc_by_monthly_payment(income, expenses, cash_pmt, cpf_pmt,
                                            rate, dp_ratio, years, target_years)
                loan_amount = r['loan_amount']
            else:
                r = calc_by_house_price(income, expenses, house_price_for_calc,
                                        rate, dp_ratio, years, cpf_pmt, target_years)
                loan_amount = r['loan_amount']

            tree.insert("", tk.END, values=(
                f"{years} 年",
                f"{r['house_price'] / 10000:.1f} 万",
                f"{r['loan_amount'] / 10000:.1f} 万",
                f"{r['total_pmt'] / 10000:.2f} 万",
                f"{r['remaining_principal'] / 10000:.1f} 万",
                r['status'],
                r['remark'],
            ), tags=(r['tag'],))

            # 收集图表数据
            monthly_rate = rate / 100 / 12
            total_months = years * 12
            timeline = simulate_payoff(loan_amount, monthly_rate, total_months,
                                       r['raw_savings'])
            chart_data.append({
                'years': years,
                'months': timeline['months'],
                'rp': timeline['remaining_principal'],
                'savings': timeline['cumulative_savings'],
            })

        update_chart(chart_data, target_years)

    except ValueError:
        messagebox.showerror("输入错误", "请输入有效的数字！")


# --- UI 界面搭建 ---
root = tk.Tk()
root.title("买房结清·动态推算器")
root.geometry("1100x750")
root.configure(padx=20, pady=20)

style = ttk.Style()
style.configure("TLabel", font=("Arial", 10))
style.configure("TButton", font=("Arial", 11, "bold"))
style.configure("Treeview.Heading", font=("Arial", 9, "bold"))
style.configure("Treeview", font=("Arial", 9), rowheight=28)

# --- 操作指引 ---
frame_guide = ttk.LabelFrame(root, text=" 使用指引 ", padding=(10, 8))
frame_guide.pack(fill="x", pady=(0, 10))

guide_text = (
    "① 填写左侧财务参数（月薪、开销、公积金、利率、首付比例）\n"
    "② 选择「目标结清年限」，程序自动反推该年限刚好结清的房价\n"
    "③ 「按月供」模式：输入现金月供，表格展示不同贷款年限的测算结果\n"
    "④ 「按房价」模式：输入目标房价（万元），表格展示不同年限的月供与判定\n"
    "⑤ 下方图表展示各年限下「累计存款 - 剩余贷款」的净资金变化趋势"
)
lbl_guide = tk.Label(frame_guide, text=guide_text, font=("Arial", 9),
                     justify="left", fg="#2C3E50", anchor="w")
lbl_guide.pack(fill="x")

# --- 输入区域 ---
frame_inputs = ttk.LabelFrame(root, text=" 你的财务现状与预期参数 ", padding=(10, 10))
frame_inputs.pack(fill="x", pady=(0, 10))

# 计算模式选择
ttk.Label(frame_inputs, text="计算模式:").grid(row=0, column=6, sticky="e", padx=(10, 5))
mode_var = tk.StringVar(value="按月供")
rb1 = ttk.Radiobutton(frame_inputs, text="按月供", variable=mode_var,
                       value="按月供", command=toggle_mode)
rb2 = ttk.Radiobutton(frame_inputs, text="按房价", variable=mode_var,
                       value="按房价", command=toggle_mode)
rb1.grid(row=0, column=7, sticky="w", padx=(0, 10))
rb2.grid(row=0, column=8, sticky="w")

# 目标结清年限
ttk.Label(frame_inputs, text="目标结清年限:").grid(row=0, column=0, sticky="e", padx=(10, 2))
combo_target_years = ttk.Combobox(frame_inputs, values=TARGET_YEARS_OPTIONS,
                                   width=5, state="readonly")
combo_target_years.set(10)
combo_target_years.grid(row=0, column=1, sticky="w", padx=(0, 15))
combo_target_years.bind("<<ComboboxSelected>>", calculate_mortgage)

# 参数输入字段
labels = ["税后月薪 (元):", "日常开销 (元/月):", "公积金月供 (元):", "综合利率 (%):",
          "首付比例 (%):", "现金月供 (元):", "目标房价 (万):"]
default_values = ["15500", "5000", "5000", "3.0", "30", "2000", "100"]
entries = []

for i in range(7):
    row = (i + 1) // 3
    col = (i % 3) * 2
    ttk.Label(frame_inputs, text=labels[i]).grid(row=row, column=col, sticky="e",
                                                  padx=(10, 2), pady=5)
    entry = ttk.Entry(frame_inputs, width=12)
    entry.insert(0, default_values[i])
    entry.grid(row=row, column=col + 1, sticky="w", padx=(0, 15), pady=5)
    entries.append(entry)

(entry_income, entry_expenses, entry_cpf_pmt, entry_rate,
 entry_dp_ratio, entry_cash_pmt, entry_house_price) = entries

for entry in entries:
    entry.bind("<KeyRelease>", calculate_mortgage)
    entry.bind("<FocusOut>", calculate_mortgage)

entry_house_price.config(state="disabled")

# --- 结果提示 ---
lbl_target = tk.Label(root, text="正在计算...", font=("Arial", 11, "bold"), fg="#27AE60")
lbl_target.pack(pady=(0, 3))

lbl_savings_result = tk.Label(root, text="点击测算查看你的闲钱储备",
                              font=("Arial", 10), fg="#D35400")
lbl_savings_result.pack(pady=(0, 8))

# --- 表格 ---
columns = ("years", "total_price", "loan_amount", "monthly_pmt",
           "remain_principal", "status", "remark")
tree = ttk.Treeview(root, columns=columns, show="headings", height=5)
tree.pack(fill="x", pady=(0, 10))

headers = ["贷款年限", "房屋总价", "初始贷款", "月供",
           f"目标年末剩余本金", "结清判定", "备注"]
widths = [70, 85, 85, 80, 120, 110, 240]
for col, text, width in zip(columns, headers, widths):
    tree.heading(col, text=text)
    tree.column(col, width=width, anchor="center")

tree.tag_configure('success', foreground='green')
tree.tag_configure('perfect', foreground='purple', font=("Arial", 10, "bold"))
tree.tag_configure('fail', foreground='red')

# --- matplotlib 图表 ---
figure = Figure(figsize=(10, 3.2), dpi=100, facecolor='#2C3E50')
ax = figure.add_subplot(111)
ax.set_facecolor('#34495E')

canvas = FigureCanvasTkAgg(figure, master=root)
canvas.get_tk_widget().pack(fill="both", expand=True)

calculate_mortgage()

root.mainloop()
