"""
房贷计算逻辑全面测试
覆盖：标准公式、零利率边界、10年结清判定、额外月供加速、
     按房价模式公积金抵扣、20年完美卡点反推(gap≈0)、交叉验证、逐月模拟
"""
import pytest
from calc import (
    monthly_payment, loan_from_payment,
    remaining_principal_standard, remaining_principal_with_extra,
    judge_10year_payoff, calc_by_monthly_payment, calc_by_house_price,
    find_perfect_house_price,
)

# 精度常量
TIGHT = 1.0       # 1元精度
LOOSE = 100.0     # 100元精度
PERFECT_GAP_MAX = 1000  # find_perfect_house_price 的 gap 应在此范围内


# ═══════════════════════════════════════════════════════════════
# 一、基础公式验证
# ═══════════════════════════════════════════════════════════════

class TestMonthlyPayment:
    """等额本息月供公式"""

    @pytest.mark.parametrize("loan,annual_rate,months,expected", [
        (1_000_000, 3.0, 360, 4216.04),
        (1_000_000, 4.9, 240, 6544.44),
        (500_000, 3.5, 120, 4943.99),
        (2_000_000, 4.0, 360, 9548.31),
        (800_000, 3.0, 180, 5524.65),
    ])
    def test_known_values(self, loan, annual_rate, months, expected):
        pmt = monthly_payment(loan, annual_rate / 100 / 12, months)
        assert abs(pmt - expected) < 1.0

    def test_zero_interest(self):
        assert monthly_payment(600_000, 0, 240) == 2500.0

    def test_single_month(self):
        pmt = monthly_payment(100_000, 0.05/12, 1)
        assert abs(pmt - 100_416.67) < 1.0

    @pytest.mark.parametrize("loan", [0, 0.0, -0])
    def test_zero_loan(self, loan):
        assert monthly_payment(loan, 0.03/12, 360) == 0

    @pytest.mark.parametrize("months", [0, -1])
    def test_zero_or_negative_months(self, months):
        assert monthly_payment(100_000, 0.03/12, months) == 0
        assert monthly_payment(100_000, 0, months) == 0

    def test_high_rate(self):
        """极端高利率"""
        pmt = monthly_payment(500_000, 0.20/12, 60)
        assert pmt > 10000  # 高利率月供应很高

    def test_very_long_term(self):
        """超长期限"""
        pmt = monthly_payment(1_000_000, 0.03/12, 600)  # 50年
        assert pmt > 0
        assert pmt < monthly_payment(1_000_000, 0.03/12, 360)  # 比30年低


class TestLoanFromPayment:
    """年金现值反推贷款额"""

    def test_inverse_of_monthly_payment(self):
        loan = 800_000
        rate = 0.035 / 12
        months = 240
        pmt = monthly_payment(loan, rate, months)
        recovered = loan_from_payment(pmt, rate, months)
        assert abs(recovered - loan) < TIGHT

    def test_zero_interest(self):
        assert loan_from_payment(5000, 0, 240) == 1_200_000

    @pytest.mark.parametrize("annual_rate", [1.5, 2.5, 3.0, 3.5, 4.0, 4.5, 5.0, 5.5, 6.0])
    @pytest.mark.parametrize("years", [10, 15, 20, 25, 30])
    def test_roundtrip(self, annual_rate, years):
        loan = 1_000_000
        r = annual_rate / 100 / 12
        m = years * 12
        pmt = monthly_payment(loan, r, m)
        recovered = loan_from_payment(pmt, r, m)
        assert abs(recovered - loan) < TIGHT

    def test_small_payment(self):
        """小额月供"""
        result = loan_from_payment(100, 0.03/12, 360)
        assert 23_000 < result < 24_000


# ═══════════════════════════════════════════════════════════════
# 二、剩余本金计算
# ═══════════════════════════════════════════════════════════════

class TestRemainingPrincipalStandard:
    """标准等额本息剩余本金"""

    def test_full_term_paid_off(self):
        assert remaining_principal_standard(500_000, 0.03/12, 240, 240) == 0

    def test_beyond_full_term(self):
        assert remaining_principal_standard(500_000, 0.03/12, 240, 300) == 0
        assert remaining_principal_standard(500_000, 0.03/12, 240, 999) == 0

    def test_zero_elapsed(self):
        rp = remaining_principal_standard(800_000, 0.03/12, 240, 0)
        assert abs(rp - 800_000) < TIGHT

    @pytest.mark.parametrize("years,expected_range", [
        (30, (700_000, 850_000)),
        (25, (600_000, 780_000)),
        (20, (450_000, 650_000)),
        (15, (250_000, 450_000)),
    ])
    def test_10year_mark(self, years, expected_range):
        loan = 1_000_000
        rate = 0.03 / 12
        rp = remaining_principal_standard(loan, rate, years * 12, 120)
        assert expected_range[0] < rp < expected_range[1]

    def test_zero_interest_linear(self):
        loan = 600_000
        months = 240
        assert abs(remaining_principal_standard(loan, 0, months, 120) - 300_000) < TIGHT
        assert abs(remaining_principal_standard(loan, 0, months, 60) - 450_000) < TIGHT
        assert abs(remaining_principal_standard(loan, 0, months, 0) - 600_000) < TIGHT
        assert remaining_principal_standard(loan, 0, months, 240) == 0

    def test_monotonically_decreasing(self):
        loan = 1_000_000
        rate = 0.04 / 12
        months = 360
        prev = loan
        for m in range(1, 361):
            rp = remaining_principal_standard(loan, rate, months, m)
            assert rp < prev, f"第{m}月剩余本金未递减"
            prev = rp
        assert prev == 0  # 最后一个月还清

    def test_various_rates(self):
        """不同利率下剩余本金都合理"""
        loan = 1_000_000
        months = 360
        for annual_rate in [2.0, 3.0, 4.0, 5.0, 6.0]:
            rp = remaining_principal_standard(loan, annual_rate/100/12, months, 120)
            assert 0 < rp < loan


class TestRemainingPrincipalWithExtra:
    """额外月供下的剩余本金"""

    def test_extra_zero_equals_standard(self):
        loan = 1_000_000
        rate = 0.03 / 12
        rp_std = remaining_principal_standard(loan, rate, 360, 120)
        rp_extra = remaining_principal_with_extra(loan, rate, 360, 120, 0)
        assert abs(rp_std - rp_extra) < TIGHT

    def test_extra_reduces_faster(self):
        loan = 1_000_000
        rate = 0.03 / 12
        rp_std = remaining_principal_standard(loan, rate, 360, 120)
        rp_extra = remaining_principal_with_extra(loan, rate, 360, 120, 3000)
        assert rp_extra < rp_std
        assert rp_std - rp_extra > 200_000

    def test_extra_can_fully_pay_off(self):
        rp = remaining_principal_with_extra(500_000, 0.03/12, 360, 120, 20000)
        assert rp == 0.0

    def test_zero_interest_with_extra(self):
        loan = 600_000
        # 标准月供=2500，额外1000 → 每月3500，120月还420000，剩180000
        rp = remaining_principal_with_extra(loan, 0, 240, 120, 1000)
        assert abs(rp - 180_000) < TIGHT

    def test_extra_beyond_loan_balance(self):
        rp = remaining_principal_with_extra(100_000, 0.03/12, 360, 120, 50000)
        assert rp == 0.0

    @pytest.mark.parametrize("extra", [500, 1000, 2000, 3000, 5000, 10000])
    def test_extra_monotonicity(self, extra):
        loan = 1_000_000
        rate = 0.03 / 12
        rp_std = remaining_principal_standard(loan, rate, 360, 120)
        rp = remaining_principal_with_extra(loan, rate, 360, 120, extra)
        assert rp <= rp_std

    def test_full_term_with_extra(self):
        """满期+额外月供 → 仍为0"""
        rp = remaining_principal_with_extra(500_000, 0.03/12, 240, 240, 1000)
        assert rp == 0.0


# ═══════════════════════════════════════════════════════════════
# 三、10年结清判定逻辑
# ═══════════════════════════════════════════════════════════════

class TestJudgement:
    """判定边界与分类"""

    def test_monthly_pmt_exceeds_income(self):
        r = judge_10year_payoff(5000, 2000, 4000, 500_000, 0.03/12, 360)
        assert r['tag'] == 'fail'
        assert '月供超出收入' in r['status']
        assert r['raw_savings'] < 0
        assert r['savings_10_years'] == 0

    def test_monthly_pmt_equals_surplus(self):
        r = judge_10year_payoff(10000, 3000, 7000, 1_000_000, 0.03/12, 360)
        assert r['tag'] == 'fail'
        assert r['raw_savings'] == 0

    def test_perfect_match_constructed(self):
        """构造完美卡点场景"""
        loan = 1_000_000
        rate = 0.03 / 12
        rp = remaining_principal_standard(loan, rate, 360, 120)
        target_gap = 25000
        monthly_savings = (rp + target_gap) / 120
        pmt = monthly_payment(loan, rate, 360)
        income = monthly_savings + 5000 + pmt
        r = judge_10year_payoff(income, 5000, pmt, loan, rate, 360)
        assert r['tag'] == 'perfect'
        assert 0 <= r['gap'] <= 50000

    def test_easy_payoff(self):
        r = judge_10year_payoff(30000, 5000, 4000, 500_000, 0.03/12, 360)
        assert r['tag'] == 'success'
        assert r['gap'] > 50000

    def test_funding_gap(self):
        r = judge_10year_payoff(10000, 3000, 4000, 2_000_000, 0.04/12, 360)
        assert r['tag'] == 'fail'
        assert '资金缺口' in r['status']

    def test_exact_50000_boundary(self):
        """gap≈50000 → perfect（上边界）"""
        loan = 1_000_000
        rate = 0.03 / 12
        rp = remaining_principal_standard(loan, rate, 360, 120)
        monthly_savings = (rp + 49999) / 120
        pmt = monthly_payment(loan, rate, 360)
        income = monthly_savings + 5000 + pmt
        r = judge_10year_payoff(income, 5000, pmt, loan, rate, 360)
        assert r['tag'] == 'perfect'

    def test_just_over_50000_is_success(self):
        """gap略超50000 → success"""
        loan = 1_000_000
        rate = 0.03 / 12
        rp = remaining_principal_standard(loan, rate, 360, 120)
        monthly_savings = (rp + 50001) / 120
        pmt = monthly_payment(loan, rate, 360)
        income = monthly_savings + 5000 + pmt
        r = judge_10year_payoff(income, 5000, pmt, loan, rate, 360)
        assert r['tag'] == 'success'

    def test_gap_zero_is_perfect(self):
        """gap=0 → perfect（下边界）"""
        loan = 1_000_000
        rate = 0.03 / 12
        rp = remaining_principal_standard(loan, rate, 360, 120)
        monthly_savings = rp / 120
        pmt = monthly_payment(loan, rate, 360)
        income = monthly_savings + 5000 + pmt
        r = judge_10year_payoff(income, 5000, pmt, loan, rate, 360)
        assert r['tag'] == 'perfect'
        assert abs(r['gap']) < TIGHT

    @pytest.mark.parametrize("years", [10, 8, 5, 3])
    def test_short_loan_no_remaining(self, years):
        r = judge_10year_payoff(15000, 5000, 5000, 500_000, 0.03/12, years * 12)
        assert r['remaining_principal'] == 0

    def test_negative_gap_absolute_value(self):
        """缺口的绝对值 = remaining - savings"""
        r = judge_10year_payoff(8000, 3000, 3000, 1_500_000, 0.04/12, 360)
        if r['tag'] == 'fail' and '资金缺口' in r['status']:
            assert r['gap'] < 0
            assert abs(r['gap']) == r['remaining_principal'] - r['savings_10_years']

    def test_remark_contains_key_info(self):
        """备注应包含闲钱和累计信息"""
        r = judge_10year_payoff(15000, 5000, 3000, 800_000, 0.03/12, 360)
        assert '闲钱' in r['remark']
        assert '累计' in r['remark']

    def test_extra_pmt_in_judgement(self):
        """判定中额外月供生效"""
        r = judge_10year_payoff(15000, 5000, 3000, 1_000_000, 0.03/12, 360, extra_pmt=2000)
        assert r['extra_pmt'] == 2000
        assert r['extra_total_10y'] == 2000 * 120


# ═══════════════════════════════════════════════════════════════
# 四、额外月供加速效果
# ═══════════════════════════════════════════════════════════════

class TestExtraPaymentEffect:
    """验证额外月供如何改善判定结果"""

    def test_extra_improves_gap(self):
        income, expenses = 12000, 3000
        loan = 1_500_000
        rate = 0.035 / 12
        pmt = monthly_payment(loan, rate, 360)

        r0 = judge_10year_payoff(income, expenses, pmt, loan, rate, 360, 0)
        r1 = judge_10year_payoff(income, expenses, pmt, loan, rate, 360, 2000)

        assert r1['remaining_principal'] < r0['remaining_principal']
        assert r1['gap'] > r0['gap']

    def test_extra_capped_at_savings(self):
        r = judge_10year_payoff(10000, 3000, 3000, 1_000_000, 0.03/12, 360, extra_pmt=10000)
        assert r['extra_pmt'] == 4000  # 闲钱=10000-3000-3000=4000

    def test_extra_reduces_remaining_exact(self):
        """精确验证额外月供减少量"""
        loan = 1_000_000
        rate = 0.03 / 12
        extra = 2000

        rp_std = remaining_principal_standard(loan, rate, 360, 120)
        rp_extra = remaining_principal_with_extra(loan, rate, 360, 120, extra)

        growth = (1 + rate) ** 120
        extra_reduction = extra * (growth - 1) / rate
        assert abs(rp_extra - (rp_std - extra_reduction)) < TIGHT

    @pytest.mark.parametrize("extra", [0, 500, 1000, 2000, 5000])
    def test_extra_monotonic_gap(self, extra):
        """额外月供越大，gap越大"""
        income, expenses = 15000, 5000
        loan = 1_500_000
        rate = 0.035 / 12
        pmt = monthly_payment(loan, rate, 360)
        r = judge_10year_payoff(income, expenses, pmt, loan, rate, 360, extra)
        if extra > 0:
            r_prev = judge_10year_payoff(income, expenses, pmt, loan, rate, 360, extra - 500 if extra >= 500 else 0)
            assert r['gap'] >= r_prev['gap']


# ═══════════════════════════════════════════════════════════════
# 五、按房价模式公积金抵扣逻辑
# ═══════════════════════════════════════════════════════════════

class TestHousePriceModeCPF:
    """按房价模式：公积金抵扣月供中的现金部分"""

    def test_cpf_reduces_cash_pmt(self):
        r0 = calc_by_house_price(15000, 5000, 1_000_000, 3.0, 30, 30, cpf_pmt=0)
        r3k = calc_by_house_price(15000, 5000, 1_000_000, 3.0, 30, 30, cpf_pmt=3000)
        assert abs(r0['total_pmt'] - r3k['total_pmt']) < TIGHT
        assert r3k['raw_savings'] > r0['raw_savings']
        assert r3k['gap'] > r0['gap']

    def test_cpf_covers_entire_payment(self):
        r = calc_by_house_price(15000, 5000, 500_000, 3.0, 30, 30, cpf_pmt=10000)
        assert r['raw_savings'] == 10000  # 全额公积金覆盖

    def test_cpf_partial_coverage(self):
        """公积金部分覆盖"""
        r = calc_by_house_price(15000, 5000, 2_000_000, 3.5, 30, 30, cpf_pmt=3000)
        # 总月供约6000+, 公积金3000, 现金月供≈3000+
        assert r['raw_savings'] < 15000 - 5000  # 比无月供少
        assert r['raw_savings'] > 15000 - 5000 - r['total_pmt']  # 比全现金多

    @pytest.mark.parametrize("cpf", [0, 1000, 3000, 5000, 8000])
    def test_cpf_monotonic_savings(self, cpf):
        """公积金越多，闲钱越多"""
        r = calc_by_house_price(15000, 5000, 1_500_000, 3.5, 30, 30, cpf_pmt=cpf)
        r0 = calc_by_house_price(15000, 5000, 1_500_000, 3.5, 30, 30, cpf_pmt=0)
        assert r['raw_savings'] >= r0['raw_savings']

    def test_cpf_with_extra_payment(self):
        r = calc_by_house_price(20000, 5000, 2_000_000, 3.5, 30, 30, cpf_pmt=4000, extra_pmt=2000)
        assert r['raw_savings'] > 0
        assert r['extra_pmt'] > 0

    def test_no_cpf_all_cash(self):
        """cpf=0 → 全部算现金"""
        r = calc_by_house_price(15000, 5000, 1_000_000, 3.0, 30, 30, cpf_pmt=0)
        assert abs(r['raw_savings'] - (15000 - 5000 - r['total_pmt'])) < TIGHT

    def test_cpf_zero_interest(self):
        """零利率+公积金"""
        r = calc_by_house_price(15000, 5000, 1_000_000, 0, 30, 30, cpf_pmt=3000)
        assert r['loan_amount'] == 700_000
        assert r['total_pmt'] > 0


# ═══════════════════════════════════════════════════════════════
# 六、20年完美卡点反推房价（gap≈0）
# ═══════════════════════════════════════════════════════════════

class TestFindPerfectPrice:
    """find_perfect_house_price: 搜索 gap≈0 的房价"""

    def test_returns_valid_price(self):
        price, gap = find_perfect_house_price(15500, 5000, 5000, 3.0, 30)
        assert price is not None
        assert price > 0

    def test_gap_near_zero(self):
        """gap 应非常接近0"""
        price, gap = find_perfect_house_price(15500, 5000, 5000, 3.0, 30)
        assert abs(gap) < PERFECT_GAP_MAX

    def test_result_is_perfect_match(self):
        """代入计算应为完美卡点"""
        income, expenses, cpf_pmt = 15500, 5000, 5000
        price, gap = find_perfect_house_price(income, expenses, cpf_pmt, 3.0, 30)
        r = calc_by_house_price(income, expenses, price, 3.0, 30, 20, cpf_pmt)
        assert r['tag'] == 'perfect'
        assert abs(r['gap']) < PERFECT_GAP_MAX

    def test_with_extra_payment(self):
        price, gap = find_perfect_house_price(15500, 5000, 5000, 3.0, 30, extra_pmt=2000)
        assert price is not None
        assert abs(gap) < PERFECT_GAP_MAX

    def test_impossible_scenario(self):
        """收入不够 → None"""
        price, gap = find_perfect_house_price(3000, 5000, 0, 3.0, 30)
        assert price is None
        assert gap is None

    def test_impossible_negative_savings(self):
        """开销>收入 → None"""
        price, gap = find_perfect_house_price(2000, 5000, 0, 3.0, 30)
        assert price is None

    @pytest.mark.parametrize("income,expected_direction", [
        (10000, "lower"),
        (20000, "higher"),
        (30000, "higher"),
    ])
    def test_income_sensitivity(self, income, expected_direction):
        """更高收入 → 更高房价"""
        base_price, _ = find_perfect_house_price(15000, 3000, 3000, 3.0, 30)
        price, _ = find_perfect_house_price(income, 3000, 3000, 3.0, 30)
        if expected_direction == "higher":
            assert price > base_price
        else:
            assert price < base_price

    @pytest.mark.parametrize("cpf", [2000, 4000, 6000, 8000])
    def test_cpf_sensitivity(self, cpf):
        """更高公积金 → 更高房价"""
        base_price, _ = find_perfect_house_price(15000, 3000, 2000, 3.0, 30)
        price, _ = find_perfect_house_price(15000, 3000, cpf, 3.0, 30)
        assert price >= base_price

    @pytest.mark.parametrize("rate", [2.0, 3.0, 4.0, 5.0])
    def test_rate_sensitivity(self, rate):
        """更高利率 → 更低房价"""
        base_price, _ = find_perfect_house_price(15000, 3000, 4000, 2.0, 30)
        price, _ = find_perfect_house_price(15000, 3000, 4000, rate, 30)
        assert price <= base_price

    @pytest.mark.parametrize("dp", [20, 30, 40, 50])
    def test_dp_ratio_sensitivity(self, dp):
        """更高首付 → 更高可承受总价"""
        base_price, _ = find_perfect_house_price(15000, 3000, 4000, 3.0, 20)
        price, _ = find_perfect_house_price(15000, 3000, 4000, 3.0, dp)
        assert price >= base_price

    def test_extra_payment_higher_price(self):
        """有额外月供 → 更高可承受房价"""
        p1, _ = find_perfect_house_price(15000, 3000, 4000, 3.0, 30, extra_pmt=0)
        p2, _ = find_perfect_house_price(15000, 3000, 4000, 3.0, 30, extra_pmt=3000)
        assert p2 > p1

    def test_precision_roundtrip(self):
        """找到的房价再算一次应得到相同gap"""
        income, expenses, cpf = 18000, 4000, 5000
        rate, dp = 3.5, 30
        price, gap = find_perfect_house_price(income, expenses, cpf, rate, dp)
        r = calc_by_house_price(income, expenses, price, rate, dp, 20, cpf)
        assert abs(r['gap'] - gap) < LOOSE

    def test_multiple_rates(self):
        """多种利率下都能找到"""
        for rate in [2.0, 3.0, 4.0, 5.0]:
            price, gap = find_perfect_house_price(15000, 3000, 4000, rate, 30)
            assert price is not None
            assert abs(gap) < PERFECT_GAP_MAX

    def test_multiple_dp_ratios(self):
        """多种首付下都能找到"""
        for dp in [20, 30, 40, 50]:
            price, gap = find_perfect_house_price(15000, 3000, 4000, 3.0, dp)
            assert price is not None
            assert abs(gap) < PERFECT_GAP_MAX


# ═══════════════════════════════════════════════════════════════
# 七、完整场景（按房价 + 按月供 交叉验证）
# ═══════════════════════════════════════════════════════════════

class TestFullScenarios:
    """完整业务场景"""

    def test_default_scenario(self):
        r = calc_by_monthly_payment(15500, 5000, 2000, 5000, 3.0, 30, 30)
        assert r['total_pmt'] == 7000
        assert r['loan_amount'] > 0

    def test_house_price_100wan_with_cpf(self):
        r = calc_by_house_price(15500, 5000, 1_000_000, 3.0, 30, 30, cpf_pmt=5000)
        assert r['loan_amount'] == 700_000
        assert abs(r['total_pmt'] - 2951.23) < 1.0
        # 公积金全覆盖，现金月供=0
        assert r['raw_savings'] == 10500

    def test_house_price_100wan_no_cpf(self):
        r = calc_by_house_price(15500, 5000, 1_000_000, 3.0, 30, 30, cpf_pmt=0)
        assert r['loan_amount'] == 700_000
        # 全部现金
        assert abs(r['raw_savings'] - (15500 - 5000 - r['total_pmt'])) < TIGHT

    def test_zero_interest(self):
        r = calc_by_house_price(15000, 5000, 1_000_000, 0, 30, 15, cpf_pmt=0)
        assert r['loan_amount'] == 700_000
        assert abs(r['total_pmt'] - 700_000 / 180) < TIGHT
        assert r['remaining_principal'] > 0

    @pytest.mark.parametrize("years", [10, 15, 20, 25, 30])
    def test_10year_remaining_ordering(self, years):
        """更长年限 → 更多剩余"""
        r = calc_by_house_price(15000, 5000, 1_000_000, 3.5, 30, years, cpf_pmt=0)
        if years == 10:
            assert r['remaining_principal'] == 0
        else:
            r_shorter = calc_by_house_price(15000, 5000, 1_000_000, 3.5, 30, years - 5, cpf_pmt=0)
            assert r['remaining_principal'] >= r_shorter['remaining_principal']

    def test_higher_rate_higher_payment(self):
        r_low = calc_by_house_price(15000, 5000, 1_000_000, 2.5, 30, 30)
        r_high = calc_by_house_price(15000, 5000, 1_000_000, 5.0, 30, 30)
        assert r_high['total_pmt'] > r_low['total_pmt']

    def test_higher_dp_lower_loan(self):
        r_low = calc_by_house_price(15000, 5000, 1_000_000, 3.0, 20, 30)
        r_high = calc_by_house_price(15000, 5000, 1_000_000, 3.0, 50, 30)
        assert r_high['loan_amount'] < r_low['loan_amount']

    def test_cross_mode_consistency(self):
        """按月供→房价→按房价，结果一致"""
        cpf = 5000
        r1 = calc_by_monthly_payment(15500, 5000, 2000, cpf, 3.0, 30, 20)
        r2 = calc_by_house_price(15500, 5000, r1['house_price'], 3.0, 30, 20, cpf)
        assert abs(r2['total_pmt'] - r1['total_pmt']) < TIGHT
        assert abs(r2['raw_savings'] - r1['raw_savings']) < TIGHT

    def test_cross_mode_20year_perfect(self):
        """20年完美卡点房价在两种模式下结果一致"""
        cpf = 5000
        price, gap = find_perfect_house_price(15500, 5000, cpf, 3.0, 30)
        r = calc_by_house_price(15500, 5000, price, 3.0, 30, 20, cpf)
        assert r['tag'] == 'perfect'
        assert abs(gap) < PERFECT_GAP_MAX

    @pytest.mark.parametrize("extra", [0, 1000, 2000, 5000])
    def test_extra_payment_in_house_price_mode(self, extra):
        r = calc_by_house_price(15000, 5000, 2_000_000, 3.5, 30, 30, cpf_pmt=0, extra_pmt=extra)
        if extra > 0:
            r0 = calc_by_house_price(15000, 5000, 2_000_000, 3.5, 30, 30, cpf_pmt=0, extra_pmt=0)
            assert r['remaining_principal'] <= r0['remaining_principal']

    def test_worst_case(self):
        r = calc_by_house_price(6000, 3000, 3_000_000, 5.0, 30, 30, cpf_pmt=0)
        assert r['tag'] == 'fail'

    def test_best_case(self):
        r = calc_by_house_price(50000, 5000, 500_000, 3.0, 50, 15, cpf_pmt=0)
        assert r['tag'] == 'success'

    def test_all_years_same_price(self):
        """同一房价，不同年限都应有结果"""
        for y in [10, 15, 20, 25, 30]:
            r = calc_by_house_price(15000, 5000, 1_500_000, 3.5, 30, y)
            assert r['house_price'] == 1_500_000
            assert r['loan_amount'] > 0
            assert r['total_pmt'] > 0

    def test_all_years_same_payment(self):
        """同一月供，不同年限都应有结果"""
        for y in [10, 15, 20, 25, 30]:
            r = calc_by_monthly_payment(15000, 5000, 2000, 5000, 3.0, 30, y)
            assert r['total_pmt'] == 7000
            assert r['loan_amount'] > 0


# ═══════════════════════════════════════════════════════════════
# 八、数学性质验证
# ═══════════════════════════════════════════════════════════════

class TestMathProperties:
    """数学恒等式与单调性"""

    @pytest.mark.parametrize("rate", [0, 2.0, 3.0, 4.5, 6.0])
    @pytest.mark.parametrize("years", [10, 15, 20, 25, 30])
    def test_pv_pmt_identity(self, rate, years):
        loan = 800_000
        r = rate / 100 / 12
        m = years * 12
        pmt = monthly_payment(loan, r, m)
        recovered = loan_from_payment(pmt, r, m)
        assert abs(recovered - loan) < TIGHT

    def test_total_interest_positive(self):
        pmt = monthly_payment(1_000_000, 0.04/12, 360)
        assert pmt * 360 > 1_000_000

    @pytest.mark.parametrize("loan", [500_000, 1_000_000, 2_000_000])
    def test_remaining_at_start(self, loan):
        rp = remaining_principal_standard(loan, 0.03/12, 360, 0)
        assert abs(rp - loan) < TIGHT

    def test_remaining_at_end(self):
        assert remaining_principal_standard(1_000_000, 0.03/12, 360, 360) == 0

    @pytest.mark.parametrize("dp", [10, 20, 30, 40, 50])
    def test_down_payment_bounds(self, dp):
        r = calc_by_house_price(15000, 5000, 1_000_000, 3.0, dp, 30, cpf_pmt=0)
        assert abs(r['loan_amount'] - 1_000_000 * (1 - dp / 100)) < TIGHT

    def test_savings_gap_identity(self):
        """savings - gap = remaining_principal"""
        r = judge_10year_payoff(12000, 3000, 3000, 1_500_000, 0.035/12, 360)
        if r['raw_savings'] > 0:
            assert abs(r['savings_10_years'] - r['gap'] - r['remaining_principal']) < TIGHT

    def test_total_pmt_times_months_gt_loan(self):
        """等额本息：总还款 > 贷款额（有利率时）"""
        for rate in [3.0, 4.0, 5.0]:
            r = calc_by_house_price(15000, 5000, 1_000_000, rate, 30, 30)
            assert r['total_pmt'] * 360 > r['loan_amount']

    def test_zero_interest_total_equals_loan(self):
        """零利率：总还款 = 贷款额"""
        r = calc_by_house_price(15000, 5000, 1_000_000, 0, 30, 30)
        assert abs(r['total_pmt'] * 360 - r['loan_amount']) < TIGHT


# ═══════════════════════════════════════════════════════════════
# 九、逐月模拟验证公式精确性
# ═══════════════════════════════════════════════════════════════

class TestMonthByMonthSimulation:
    """逐月摊销模拟 vs 闭式公式"""

    @pytest.mark.parametrize("extra", [0, 500, 1000, 2000, 5000])
    def test_with_extra(self, extra):
        loan = 600_000
        rate = 0.03 / 12
        months = 240
        pmt = monthly_payment(loan, rate, months)

        balance = loan
        for m in range(120):
            interest = balance * rate
            principal = pmt + extra - interest
            balance -= principal
            if balance < 0:
                balance = 0
                break

        rp_formula = remaining_principal_with_extra(loan, rate, months, 120, extra)
        assert abs(balance - rp_formula) < LOOSE

    @pytest.mark.parametrize("extra", [0, 1000, 2000])
    def test_zero_interest_with_extra(self, extra):
        loan = 500_000
        pmt = monthly_payment(loan, 0, 240)

        balance = loan
        for m in range(120):
            balance -= (pmt + extra)
            if balance < 0:
                balance = 0
                break

        rp_formula = remaining_principal_with_extra(loan, 0, 240, 120, extra)
        assert abs(balance - rp_formula) < LOOSE

    def test_full_amortization_with_extra(self):
        """额外月供应加速还清"""
        loan = 800_000
        rate = 0.035 / 12
        months = 240
        extra = 2000
        pmt = monthly_payment(loan, rate, months)

        balance = loan
        month_count = 0
        for m in range(months):
            if balance <= 0:
                break
            interest = balance * rate
            payment = min(pmt + extra, balance + interest)
            balance = balance + interest - payment
            month_count += 1

        assert month_count < months
        assert balance <= 0

    def test_standard_amortization_consistency(self):
        """标准摊销：逐月剩余 = 公式剩余（每个月）"""
        loan = 400_000
        rate = 0.04 / 12
        months = 240
        pmt = monthly_payment(loan, rate, months)

        balance = loan
        for m in range(1, 121):
            interest = balance * rate
            balance = balance + interest - pmt
            rp = remaining_principal_standard(loan, rate, months, m)
            assert abs(balance - rp) < LOOSE, f"第{m}月不一致: sim={balance}, formula={rp}"

    def test_extra_payment_interest_savings(self):
        """有额外月供应节省利息"""
        loan = 1_000_000
        rate = 0.04 / 12
        months = 360
        pmt = monthly_payment(loan, rate, months)

        def total_interest(extra):
            bal = loan
            total = 0
            for m in range(months):
                if bal <= 0:
                    break
                interest = bal * rate
                total += interest
                payment = min(pmt + extra, bal + interest)
                bal = bal + interest - payment
            return total

        ti_no_extra = total_interest(0)
        ti_with_extra = total_interest(2000)
        assert ti_with_extra < ti_no_extra


if __name__ == '__main__':
    pytest.main([__file__, '-v'])
