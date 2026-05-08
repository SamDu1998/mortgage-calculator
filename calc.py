"""
房贷计算核心逻辑 — 纯函数，无UI依赖
包含：标准等额本息、提前还款（额外月供）、10年结清判定、20年完美卡点反推房价
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


def remaining_principal_standard(loan_amount, monthly_rate, total_months, elapsed_months):
    """标准等额本息下，elapsed_months个月后的剩余本金（无额外还款）"""
    if elapsed_months >= total_months:
        return 0.0
    remaining_months = total_months - elapsed_months
    pmt = monthly_payment(loan_amount, monthly_rate, total_months)
    if monthly_rate > 0:
        return pmt * ((1 - (1 + monthly_rate) ** (-remaining_months)) / monthly_rate)
    return pmt * remaining_months


def remaining_principal_with_extra(loan_amount, monthly_rate, total_months, elapsed_months, extra_pmt=0):
    """
    有额外月供时，elapsed_months个月后的剩余本金。

    数学推导：
    标准还款 B_n = B*(1+i)^n - pmt*[(1+i)^n - 1]/i
    多还 extra 后：B_n = B*(1+i)^n - (pmt+extra)*[(1+i)^n - 1]/i
    等价于：标准剩余本金 - extra*[(1+i)^n - 1]/i

    当 extra 大到在 elapsed_months 内已还清时，返回 0。
    """
    if extra_pmt == 0:
        return remaining_principal_standard(loan_amount, monthly_rate, total_months, elapsed_months)

    if elapsed_months >= total_months:
        return 0.0

    if monthly_rate > 0:
        growth = (1 + monthly_rate) ** elapsed_months
        standard_remaining = loan_amount * growth - \
            monthly_payment(loan_amount, monthly_rate, total_months) * (growth - 1) / monthly_rate
        extra_reduction = extra_pmt * (growth - 1) / monthly_rate
        result = standard_remaining - extra_reduction
        return max(result, 0.0)
    else:
        pmt = monthly_payment(loan_amount, monthly_rate, total_months)
        total_paid = (pmt + extra_pmt) * elapsed_months
        return max(loan_amount - total_paid, 0.0)


def judge_10year_payoff(income, expenses, cash_pmt, loan_amount, monthly_rate,
                        total_months, extra_pmt=0):
    """
    10年结清判定。

    cash_pmt: 用户实际现金支出的月供（不含公积金部分）
    extra_pmt: 额外月供（从闲钱中额外拿出用于提前还贷）

    返回 dict：
        remaining_principal  第10年末剩余本金
        raw_savings          每月闲钱（收入-开销-现金月供）
        savings_10_years     10年累计闲钱（扣除额外月供后的存款部分）
        extra_pmt            实际生效的额外月供
        extra_total_10y      10年额外还款总额
        gap                  闲钱 vs 剩余本金的差值
        status               判定文字
        tag                  'success' | 'perfect' | 'fail'
    """
    elapsed_months = 120

    # 闲钱 = 收入 - 开销 - 现金月供
    raw_savings = income - expenses - cash_pmt

    if raw_savings < 0:
        return {
            'remaining_principal': 0,
            'raw_savings': raw_savings,
            'savings_10_years': 0,
            'extra_pmt': extra_pmt,
            'extra_total_10y': 0,
            'gap': raw_savings,
            'status': '❌ 月供超出收入',
            'remark': f'月供{cash_pmt:.0f} 超出可用{(income - expenses):.0f}',
            'tag': 'fail',
        }

    # 额外月供不能超过闲钱
    effective_extra = min(extra_pmt, raw_savings)

    # 第10年末剩余本金（考虑额外月供加速还款）
    rp = remaining_principal_with_extra(loan_amount, monthly_rate, total_months,
                                         elapsed_months, effective_extra)

    # 10年累计闲钱（扣除额外月供后的部分，作为"存款"）
    net_monthly_savings = raw_savings - effective_extra
    savings_10_years = net_monthly_savings * 120

    extra_total_10y = effective_extra * 120

    gap = savings_10_years - rp

    savings_info = f'闲钱{raw_savings:.0f}/月 累计{savings_10_years / 10000:.1f}万'
    if effective_extra > 0:
        savings_info += f' 额外月供{effective_extra:.0f}/月'

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
        'savings_10_years': savings_10_years,
        'extra_pmt': effective_extra,
        'extra_total_10y': extra_total_10y,
        'gap': gap,
        'status': status,
        'remark': remark,
        'tag': tag,
    }


def calc_by_monthly_payment(income, expenses, cash_pmt, cpf_pmt, rate, dp_ratio,
                            years, extra_pmt=0):
    """按月供模式：给定月供，反推贷款额和房价"""
    monthly_rate = rate / 100 / 12
    total_months = years * 12
    total_pmt = cash_pmt + cpf_pmt

    loan_amount = loan_from_payment(total_pmt, monthly_rate, total_months)
    house_price = loan_amount / (1 - dp_ratio / 100)

    result = judge_10year_payoff(income, expenses, cash_pmt, loan_amount,
                                 monthly_rate, total_months, extra_pmt)
    result.update({
        'years': years,
        'house_price': house_price,
        'loan_amount': loan_amount,
        'total_pmt': total_pmt,
    })
    return result


def calc_by_house_price(income, expenses, house_price, rate, dp_ratio,
                        years, cpf_pmt=0, extra_pmt=0):
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

    result = judge_10year_payoff(income, expenses, cash_pmt, loan_amount,
                                 monthly_rate, total_months, extra_pmt)
    result.update({
        'years': years,
        'house_price': house_price,
        'loan_amount': loan_amount,
        'total_pmt': total_pmt,
    })
    return result


def find_perfect_house_price(income, expenses, cpf_pmt, rate, dp_ratio,
                             extra_pmt=0, target_years=20):
    """
    二分搜索：找到使 target_years 贷款"刚好一点不剩"的房屋总价。
    目标 = gap ≈ 0（闲钱刚好覆盖剩余本金，不多不少）

    返回 (house_price, gap) 或 (None, None) 表示无法找到。
    """

    def gap_at_price(price):
        r = calc_by_house_price(income, expenses, price, rate, dp_ratio,
                                target_years, cpf_pmt, extra_pmt)
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
