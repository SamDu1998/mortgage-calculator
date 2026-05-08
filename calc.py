"""
房贷计算核心逻辑 — 纯函数，无UI依赖
包含：标准等额本息、逐月模拟、结清判定、完美卡点反推房价
"""


def monthly_payment(loan_amount, monthly_rate, total_months):
    """等额本息月供公式（标准年金）"""
    if total_months <= 0:
        return 0
    if monthly_rate > 0:
        return loan_amount * (monthly_rate * (1 + monthly_rate) ** total_months) / \
               ((1 + monthly_rate) ** total_months - 1)
    return loan_amount / total_months


def loan_from_payment(total_pmt, monthly_rate, total_months):
    """已知月供反推贷款额（年金现值）"""
    if monthly_rate > 0:
        return total_pmt * ((1 - (1 + monthly_rate) ** (-total_months)) / monthly_rate)
    return total_pmt * total_months


def simulate_remaining_principal(loan_amount, monthly_rate, total_months, elapsed_months):
    """逐月模拟：计算 elapsed_months 个月后的剩余本金。"""
    if elapsed_months <= 0:
        return loan_amount
    if elapsed_months >= total_months:
        return 0.0

    pmt = monthly_payment(loan_amount, monthly_rate, total_months)
    balance = loan_amount

    for _ in range(elapsed_months):
        if balance <= 0:
            return 0.0
        interest = balance * monthly_rate
        principal = pmt - interest
        balance -= principal

    return max(balance, 0.0)


def simulate_payoff(loan_amount, monthly_rate, total_months, raw_savings):
    """
    逐月模拟完整还款过程，返回逐月时间线数据（用于绘图）。

    返回 dict：
        months              月份列表 [0, 1, 2, ...]
        remaining_principal  每月剩余本金列表
        cumulative_savings   每月累计存款列表
    """
    pmt = monthly_payment(loan_amount, monthly_rate, total_months)
    balance = loan_amount
    savings = 0.0

    months = [0]
    rp_list = [balance]
    savings_list = [0.0]

    for month in range(1, total_months + 1):
        if balance > 0:
            interest = balance * monthly_rate
            principal = pmt - interest
            balance -= principal
        balance = max(balance, 0.0)
        savings += raw_savings

        months.append(month)
        rp_list.append(balance)
        savings_list.append(savings)

    return {
        'months': months,
        'remaining_principal': rp_list,
        'cumulative_savings': savings_list,
    }


def judge_payoff(income, expenses, cash_pmt, loan_amount, monthly_rate,
                 total_months, target_years=10):
    """
    结清判定 — 逐月模拟。

    逐月摊销 target_years 年，同时累计闲钱存款，最后比较存款与剩余本金。

    cash_pmt: 用户实际现金支出的月供（不含公积金部分）

    返回 dict：
        remaining_principal  目标年末剩余本金
        raw_savings          每月闲钱（收入-开销-现金月供）
        savings_target       目标年累计闲钱
        gap                  闲钱 vs 剩余本金的差值
        status               判定文字
        tag                  'success' | 'perfect' | 'fail'
    """
    elapsed_months = target_years * 12

    # 闲钱 = 收入 - 开销 - 现金月供
    raw_savings = income - expenses - cash_pmt

    if raw_savings < 0:
        return {
            'remaining_principal': 0,
            'raw_savings': raw_savings,
            'savings_target': 0,
            'gap': raw_savings,
            'status': '❌ 月供超出收入',
            'remark': f'月供{cash_pmt:.0f} 超出可用{(income - expenses):.0f}',
            'tag': 'fail',
        }

    # --- 逐月模拟 ---
    pmt = monthly_payment(loan_amount, monthly_rate, total_months)
    balance = loan_amount

    for _ in range(elapsed_months):
        if balance <= 0:
            balance = 0.0
            break
        interest = balance * monthly_rate
        principal = pmt - interest
        balance -= principal

    rp = max(balance, 0.0)

    # 累计闲钱
    savings_target = raw_savings * elapsed_months

    gap = savings_target - rp

    savings_info = f'闲钱{raw_savings:.0f}/月 累计{savings_target / 10000:.1f}万'

    if 0 <= gap <= 50000:
        status = '🌟 完美卡点'
        remark = f'{savings_info} 刚好覆盖'
        tag = 'perfect'
    elif gap > 50000:
        status = '✅ 轻松结清'
        remark = f'{savings_info} 余{gap / 10000:.1f}万'
        tag = 'success'
    else:
        status = '❌ 资金缺口'
        remark = f'{savings_info} 缺{-gap / 10000:.1f}万'
        tag = 'fail'

    return {
        'remaining_principal': rp,
        'raw_savings': raw_savings,
        'savings_target': savings_target,
        'gap': gap,
        'status': status,
        'remark': remark,
        'tag': tag,
    }


def calc_by_monthly_payment(income, expenses, cash_pmt, cpf_pmt, rate, dp_ratio,
                            years, target_years=10):
    """按月供模式：给定月供，反推贷款额和房价"""
    monthly_rate = rate / 100 / 12
    total_months = years * 12
    total_pmt = cash_pmt + cpf_pmt

    loan_amount = loan_from_payment(total_pmt, monthly_rate, total_months)
    house_price = loan_amount / (1 - dp_ratio / 100)

    result = judge_payoff(income, expenses, cash_pmt, loan_amount,
                          monthly_rate, total_months, target_years)
    result.update({
        'years': years,
        'house_price': house_price,
        'loan_amount': loan_amount,
        'total_pmt': total_pmt,
    })
    return result


def calc_by_house_price(income, expenses, house_price, rate, dp_ratio,
                        years, cpf_pmt=0, target_years=10):
    """
    按房价模式：给定房价，正算月供。

    cpf_pmt: 用户每月公积金缴存额（用于抵扣月供中的现金部分）
    现金月供 = 总月供 - 公积金（取 max 0）
    """
    monthly_rate = rate / 100 / 12
    total_months = years * 12
    loan_amount = house_price * (1 - dp_ratio / 100)

    total_pmt = monthly_payment(loan_amount, monthly_rate, total_months)

    # 现金月供 = 总月供 - 公积金抵扣
    cash_pmt = max(total_pmt - cpf_pmt, 0)

    result = judge_payoff(income, expenses, cash_pmt, loan_amount,
                          monthly_rate, total_months, target_years)
    result.update({
        'years': years,
        'house_price': house_price,
        'loan_amount': loan_amount,
        'total_pmt': total_pmt,
    })
    return result


def find_perfect_house_price(income, expenses, cpf_pmt, rate, dp_ratio,
                             target_years=20):
    """
    二分搜索：找到 target_years 年刚好结清的房屋总价。
    内部固定使用30年贷款来搜索，target_years 仅用于结清判定。
    目标 = gap ≈ 0（闲钱刚好覆盖剩余本金，不多不少）

    返回 (house_price, gap) 或 (None, None) 表示无法找到。
    """
    search_loan_years = 30  # 固定用30年贷款搜索

    def gap_at_price(price):
        r = calc_by_house_price(income, expenses, price, rate, dp_ratio,
                                search_loan_years, cpf_pmt, target_years)
        return r['gap']

    # 验证可行性：房价极小时 gap 应 > 0
    gap_low = gap_at_price(1)
    if gap_low < 0:
        return None, None

    # 二分搜索：找到 gap ≈ 0 的房价
    lo = 1
    hi = 100_000_000  # 1亿

    # 确认上界确实 gap < 0
    if gap_at_price(hi) >= 0:
        return hi, gap_at_price(hi)

    for _ in range(100):
        mid = (lo + hi) / 2
        g = gap_at_price(mid)
        if g > 0:
            lo = mid
        else:
            hi = mid
        if hi - lo < 1:  # 精度到1元
            break

    # 取 lo 侧（gap >= 0），确保在"完美卡点"区间内
    price = lo
    gap = gap_at_price(price)
    return price, gap
