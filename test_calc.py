"""
房贷计算逻辑测试
覆盖：基础公式、逐月模拟精确性、结清判定、按房价/按月供模式、完美卡点反推
"""
import pytest
from calc import (
    monthly_payment, loan_from_payment,
    simulate_remaining_principal, simulate_payoff, judge_payoff,
    calc_by_monthly_payment, calc_by_house_price,
    find_perfect_house_price,
)

# 精度常量
TIGHT = 1.0
LOOSE = 100.0
SIM_TOLERANCE = 500


# ═══════════════════════════════════════════════════════════════
# 一、基础公式验证
# ═══════════════════════════════════════════════════════════════

class TestMonthlyPayment:
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

    def test_high_rate(self):
        pmt = monthly_payment(500_000, 0.20/12, 60)
        assert pmt > 10000

    def test_very_long_term(self):
        pmt = monthly_payment(1_000_000, 0.03/12, 600)
        assert pmt > 0
        assert pmt < monthly_payment(1_000_000, 0.03/12, 360)


class TestLoanFromPayment:
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


# ═══════════════════════════════════════════════════════════════
# 二、逐月模拟剩余本金
# ═══════════════════════════════════════════════════════════════

class TestSimulateRemainingPrincipal:
    @pytest.mark.parametrize("annual_rate", [0, 2.0, 3.0, 4.0, 5.0, 6.0])
    @pytest.mark.parametrize("years", [10, 15, 20, 25, 30])
    def test_matches_closed_form(self, annual_rate, years):
        loan = 1_000_000
        rate = annual_rate / 100 / 12
        months = years * 12
        rp = simulate_remaining_principal(loan, rate, months, 120)
        pmt = monthly_payment(loan, rate, months)
        remaining = months - 120
        if remaining <= 0:
            expected = 0.0
        elif rate > 0:
            expected = pmt * ((1 - (1 + rate) ** (-remaining)) / rate)
        else:
            expected = pmt * remaining
        assert abs(rp - expected) < SIM_TOLERANCE

    def test_zero_elapsed(self):
        rp = simulate_remaining_principal(800_000, 0.03/12, 240, 0)
        assert abs(rp - 800_000) < TIGHT

    def test_full_term_paid_off(self):
        rp = simulate_remaining_principal(500_000, 0.03/12, 240, 240)
        assert rp == 0.0

    def test_beyond_full_term(self):
        rp = simulate_remaining_principal(500_000, 0.03/12, 240, 300)
        assert rp == 0.0

    def test_monotonically_decreasing(self):
        loan = 1_000_000
        rate = 0.04 / 12
        months = 360
        prev = loan
        for m in range(1, 361):
            rp = simulate_remaining_principal(loan, rate, months, m)
            assert rp < prev + SIM_TOLERANCE
            prev = rp
        assert prev < SIM_TOLERANCE


# ═══════════════════════════════════════════════════════════════
# 三、simulate_payoff 时间线数据
# ═══════════════════════════════════════════════════════════════

class TestSimulatePayoff:
    def test_returns_correct_length(self):
        result = simulate_payoff(500_000, 0.03/12, 240, 3000)
        assert len(result['months']) == 241  # 0 to 240
        assert len(result['remaining_principal']) == 241
        assert len(result['cumulative_savings']) == 241

    def test_starts_at_zero(self):
        result = simulate_payoff(500_000, 0.03/12, 240, 3000)
        assert result['months'][0] == 0
        assert result['remaining_principal'][0] == 500_000
        assert result['cumulative_savings'][0] == 0.0

    def test_ends_at_zero_balance(self):
        result = simulate_payoff(500_000, 0.03/12, 240, 3000)
        assert result['remaining_principal'][-1] < SIM_TOLERANCE

    def test_savings_linear_growth(self):
        raw = 5000
        result = simulate_payoff(500_000, 0.03/12, 240, raw)
        for i, s in enumerate(result['cumulative_savings']):
            assert abs(s - raw * i) < TIGHT

    def test_remaining_monotonically_decreasing(self):
        result = simulate_payoff(1_000_000, 0.04/12, 360, 5000)
        for i in range(1, len(result['remaining_principal'])):
            assert result['remaining_principal'][i] <= result['remaining_principal'][i-1] + TIGHT

    def test_zero_savings(self):
        result = simulate_payoff(500_000, 0.03/12, 240, 0)
        assert all(s == 0 for s in result['cumulative_savings'])


# ═══════════════════════════════════════════════════════════════
# 四、结清判定逻辑
# ═══════════════════════════════════════════════════════════════

class TestJudgement:
    def test_monthly_pmt_exceeds_income(self):
        r = judge_payoff(5000, 2000, 4000, 500_000, 0.03/12, 360)
        assert r['tag'] == 'fail'
        assert '月供超出收入' in r['status']
        assert r['raw_savings'] < 0

    def test_monthly_pmt_equals_surplus(self):
        r = judge_payoff(10000, 3000, 7000, 1_000_000, 0.03/12, 360)
        assert r['tag'] == 'fail'
        assert r['raw_savings'] == 0

    def test_easy_payoff(self):
        r = judge_payoff(30000, 5000, 4000, 500_000, 0.03/12, 360)
        assert r['tag'] == 'success'
        assert r['gap'] > 50000

    def test_funding_gap(self):
        r = judge_payoff(10000, 3000, 4000, 2_000_000, 0.04/12, 360)
        assert r['tag'] == 'fail'
        assert '资金缺口' in r['status']

    @pytest.mark.parametrize("years", [10, 8, 5, 3])
    def test_short_loan_no_remaining(self, years):
        r = judge_payoff(15000, 5000, 5000, 500_000, 0.03/12, years * 12)
        assert r['remaining_principal'] == 0

    def test_remark_contains_key_info(self):
        r = judge_payoff(15000, 5000, 3000, 800_000, 0.03/12, 360)
        assert '闲钱' in r['remark']
        assert '累计' in r['remark']

    def test_savings_gap_identity(self):
        r = judge_payoff(12000, 3000, 3000, 1_500_000, 0.035/12, 360)
        if r['raw_savings'] > 0:
            assert abs(r['savings_target'] - r['gap'] - r['remaining_principal']) < SIM_TOLERANCE

    def test_gap_decreases_with_higher_price(self):
        r_low = judge_payoff(15000, 5000, 2000, 500_000, 0.03/12, 360)
        r_high = judge_payoff(15000, 5000, 6000, 2_000_000, 0.03/12, 360)
        assert r_low['gap'] > r_high['gap']

    def test_perfect_price_gives_perfect_tag(self):
        income, expenses, cpf = 15500, 5000, 5000
        price, gap = find_perfect_house_price(income, expenses, cpf, 3.0, 30)
        assert price is not None
        r = calc_by_house_price(income, expenses, price, 3.0, 30, 30, cpf, target_years=20)
        assert r['tag'] == 'perfect'
        assert 0 <= r['gap'] <= 50000


# ═══════════════════════════════════════════════════════════════
# 五、不同目标年限
# ═══════════════════════════════════════════════════════════════

class TestTargetYears:
    """验证不同目标结清年限的判定逻辑"""

    @pytest.mark.parametrize("target", [5, 8, 10, 12, 15, 20])
    def test_different_target_years(self, target):
        r = judge_payoff(15000, 5000, 3000, 1_000_000, 0.03/12, 360, target_years=target)
        assert r['savings_target'] == r['raw_savings'] * target * 12
        assert 'tag' in r

    def test_shorter_target_easier_to_pass(self):
        """更短的目标年限 → 更容易结清（剩余本金更多但存款时间更短，需看具体场景）"""
        r5 = judge_payoff(20000, 5000, 3000, 800_000, 0.03/12, 360, target_years=5)
        r15 = judge_payoff(20000, 5000, 3000, 800_000, 0.03/12, 360, target_years=15)
        # 5年时剩余本金高但存款少，15年时剩余本金低但存款多
        assert r5['remaining_principal'] > r15['remaining_principal']
        assert r5['savings_target'] < r15['savings_target']

    def test_longer_target_more_savings(self):
        r = judge_payoff(15000, 5000, 3000, 1_000_000, 0.03/12, 360, target_years=20)
        assert r['savings_target'] == r['raw_savings'] * 240

    def test_calc_by_house_price_with_target_years(self):
        r = calc_by_house_price(15000, 5000, 1_000_000, 3.0, 30, 30, cpf_pmt=0,
                                target_years=15)
        assert r['years'] == 30
        assert r['savings_target'] == r['raw_savings'] * 180

    def test_calc_by_monthly_payment_with_target_years(self):
        r = calc_by_monthly_payment(15000, 5000, 2000, 5000, 3.0, 30, 20,
                                    target_years=8)
        assert r['years'] == 20
        assert r['savings_target'] == r['raw_savings'] * 96

    def test_find_perfect_with_different_targets(self):
        """不同目标年限都应能找到完美卡点房价"""
        for target in [5, 10, 15, 20]:
            price, gap = find_perfect_house_price(15500, 5000, 5000, 3.0, 30,
                                                  target_years=target)
            assert price is not None
            assert price > 0

    def test_shorter_target_lower_price(self):
        """更短目标年限 → 可承受更低房价（攒钱时间短）"""
        p5, _ = find_perfect_house_price(15500, 5000, 5000, 3.0, 30, target_years=5)
        p20, _ = find_perfect_house_price(15500, 5000, 5000, 3.0, 30, target_years=20)
        assert p5 < p20


# ═══════════════════════════════════════════════════════════════
# 六、按房价模式公积金抵扣
# ═══════════════════════════════════════════════════════════════

class TestHousePriceModeCPF:
    def test_cpf_reduces_cash_pmt(self):
        r0 = calc_by_house_price(15000, 5000, 1_000_000, 3.0, 30, 30, cpf_pmt=0)
        r3k = calc_by_house_price(15000, 5000, 1_000_000, 3.0, 30, 30, cpf_pmt=3000)
        assert abs(r0['total_pmt'] - r3k['total_pmt']) < TIGHT
        assert r3k['raw_savings'] > r0['raw_savings']
        assert r3k['gap'] > r0['gap']

    def test_cpf_covers_entire_payment(self):
        r = calc_by_house_price(15000, 5000, 500_000, 3.0, 30, 30, cpf_pmt=10000)
        assert r['raw_savings'] == 10000

    @pytest.mark.parametrize("cpf", [0, 1000, 3000, 5000, 8000])
    def test_cpf_monotonic_savings(self, cpf):
        r = calc_by_house_price(15000, 5000, 1_500_000, 3.5, 30, 30, cpf_pmt=cpf)
        r0 = calc_by_house_price(15000, 5000, 1_500_000, 3.5, 30, 30, cpf_pmt=0)
        assert r['raw_savings'] >= r0['raw_savings']

    def test_no_cpf_all_cash(self):
        r = calc_by_house_price(15000, 5000, 1_000_000, 3.0, 30, 30, cpf_pmt=0)
        assert abs(r['raw_savings'] - (15000 - 5000 - r['total_pmt'])) < TIGHT


# ═══════════════════════════════════════════════════════════════
# 七、完美卡点反推房价
# ═══════════════════════════════════════════════════════════════

class TestFindPerfectPrice:
    def test_returns_valid_price(self):
        price, gap = find_perfect_house_price(15500, 5000, 5000, 3.0, 30)
        assert price is not None
        assert price > 0

    def test_gap_near_zero(self):
        price, gap = find_perfect_house_price(15500, 5000, 5000, 3.0, 30)
        assert abs(gap) < SIM_TOLERANCE

    def test_result_is_perfect_match(self):
        income, expenses, cpf_pmt = 15500, 5000, 5000
        price, gap = find_perfect_house_price(income, expenses, cpf_pmt, 3.0, 30)
        r = calc_by_house_price(income, expenses, price, 3.0, 30, 30, cpf_pmt, target_years=20)
        assert r['tag'] == 'perfect'

    def test_impossible_scenario(self):
        price, gap = find_perfect_house_price(3000, 5000, 0, 3.0, 30)
        assert price is None
        assert gap is None

    @pytest.mark.parametrize("income,expected_direction", [
        (10000, "lower"),
        (20000, "higher"),
        (30000, "higher"),
    ])
    def test_income_sensitivity(self, income, expected_direction):
        base_price, _ = find_perfect_house_price(15000, 3000, 3000, 3.0, 30)
        price, _ = find_perfect_house_price(income, 3000, 3000, 3.0, 30)
        if expected_direction == "higher":
            assert price > base_price
        else:
            assert price < base_price

    @pytest.mark.parametrize("cpf", [2000, 4000, 6000, 8000])
    def test_cpf_sensitivity(self, cpf):
        base_price, _ = find_perfect_house_price(15000, 3000, 2000, 3.0, 30)
        price, _ = find_perfect_house_price(15000, 3000, cpf, 3.0, 30)
        assert price >= base_price

    @pytest.mark.parametrize("rate", [2.0, 3.0, 4.0, 5.0])
    def test_rate_sensitivity(self, rate):
        base_price, _ = find_perfect_house_price(15000, 3000, 4000, 2.0, 30)
        price, _ = find_perfect_house_price(15000, 3000, 4000, rate, 30)
        assert price <= base_price

    @pytest.mark.parametrize("dp", [20, 30, 40, 50])
    def test_dp_ratio_sensitivity(self, dp):
        base_price, _ = find_perfect_house_price(15000, 3000, 4000, 3.0, 20)
        price, _ = find_perfect_house_price(15000, 3000, 4000, 3.0, dp)
        assert price >= base_price

    def test_precision_roundtrip(self):
        income, expenses, cpf = 18000, 4000, 5000
        rate, dp = 3.5, 30
        price, gap = find_perfect_house_price(income, expenses, cpf, rate, dp)
        r = calc_by_house_price(income, expenses, price, rate, dp, 30, cpf, target_years=20)
        assert abs(r['gap'] - gap) < LOOSE


# ═══════════════════════════════════════════════════════════════
# 八、完整场景（按房价 + 按月供 交叉验证）
# ═══════════════════════════════════════════════════════════════

class TestFullScenarios:
    def test_default_scenario(self):
        r = calc_by_monthly_payment(15500, 5000, 2000, 5000, 3.0, 30, 30)
        assert r['total_pmt'] == 7000
        assert r['loan_amount'] > 0

    def test_house_price_100wan_with_cpf(self):
        r = calc_by_house_price(15500, 5000, 1_000_000, 3.0, 30, 30, cpf_pmt=5000)
        assert r['loan_amount'] == 700_000
        assert abs(r['total_pmt'] - 2951.23) < 1.0
        assert r['raw_savings'] == 10500

    def test_house_price_100wan_no_cpf(self):
        r = calc_by_house_price(15500, 5000, 1_000_000, 3.0, 30, 30, cpf_pmt=0)
        assert r['loan_amount'] == 700_000
        assert abs(r['raw_savings'] - (15500 - 5000 - r['total_pmt'])) < TIGHT

    def test_zero_interest(self):
        r = calc_by_house_price(15000, 5000, 1_000_000, 0, 30, 15, cpf_pmt=0)
        assert r['loan_amount'] == 700_000
        assert abs(r['total_pmt'] - 700_000 / 180) < TIGHT
        assert r['remaining_principal'] > 0

    @pytest.mark.parametrize("years", [10, 15, 20, 25, 30])
    def test_10year_remaining_ordering(self, years):
        r = calc_by_house_price(15000, 5000, 1_000_000, 3.5, 30, years, cpf_pmt=0)
        if years == 10:
            assert r['remaining_principal'] < SIM_TOLERANCE
        else:
            r_shorter = calc_by_house_price(15000, 5000, 1_000_000, 3.5, 30,
                                            years - 5, cpf_pmt=0)
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
        cpf = 5000
        r1 = calc_by_monthly_payment(15500, 5000, 2000, cpf, 3.0, 30, 20)
        r2 = calc_by_house_price(15500, 5000, r1['house_price'], 3.0, 30, 20, cpf)
        assert abs(r2['total_pmt'] - r1['total_pmt']) < TIGHT
        assert abs(r2['raw_savings'] - r1['raw_savings']) < TIGHT

    def test_all_years_same_price(self):
        for y in [10, 15, 20, 25, 30]:
            r = calc_by_house_price(15000, 5000, 1_500_000, 3.5, 30, y)
            assert r['house_price'] == 1_500_000
            assert r['loan_amount'] > 0

    def test_all_years_same_payment(self):
        for y in [10, 15, 20, 25, 30]:
            r = calc_by_monthly_payment(15000, 5000, 2000, 5000, 3.0, 30, y)
            assert r['total_pmt'] == 7000

    def test_worst_case(self):
        r = calc_by_house_price(6000, 3000, 3_000_000, 5.0, 30, 30, cpf_pmt=0)
        assert r['tag'] == 'fail'

    def test_best_case(self):
        r = calc_by_house_price(50000, 5000, 500_000, 3.0, 50, 15, cpf_pmt=0)
        assert r['tag'] == 'success'


# ═══════════════════════════════════════════════════════════════
# 九、数学性质验证
# ═══════════════════════════════════════════════════════════════

class TestMathProperties:
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

    @pytest.mark.parametrize("dp", [10, 20, 30, 40, 50])
    def test_down_payment_bounds(self, dp):
        r = calc_by_house_price(15000, 5000, 1_000_000, 3.0, dp, 30, cpf_pmt=0)
        assert abs(r['loan_amount'] - 1_000_000 * (1 - dp / 100)) < TIGHT

    def test_zero_interest_total_equals_loan(self):
        r = calc_by_house_price(15000, 5000, 1_000_000, 0, 30, 30)
        assert abs(r['total_pmt'] * 360 - r['loan_amount']) < TIGHT


# ═══════════════════════════════════════════════════════════════
# 十、逐月模拟精确性验证
# ═══════════════════════════════════════════════════════════════

class TestSimulationAccuracy:
    def test_standard_amortization_consistency(self):
        loan = 400_000
        rate = 0.04 / 12
        months = 240
        pmt = monthly_payment(loan, rate, months)
        balance = loan
        for m in range(1, 121):
            interest = balance * rate
            balance = balance + interest - pmt
            rp = simulate_remaining_principal(loan, rate, months, m)
            assert abs(balance - rp) < LOOSE

    @pytest.mark.parametrize("annual_rate", [0, 2.0, 3.0, 4.0, 5.0, 6.0])
    def test_10year_mark_accuracy(self, annual_rate):
        loan = 1_000_000
        rate = annual_rate / 100 / 12
        months = 360
        pmt = monthly_payment(loan, rate, months)
        balance = loan
        for _ in range(120):
            interest = balance * rate
            balance -= (pmt - interest)
        sim_result = max(balance, 0.0)
        remaining_months = months - 120
        if rate > 0:
            formula_result = pmt * ((1 - (1 + rate) ** (-remaining_months)) / rate)
        else:
            formula_result = pmt * remaining_months
        assert abs(sim_result - formula_result) < SIM_TOLERANCE

    def test_judge_result_consistent_with_simulation(self):
        income, expenses = 15000, 5000
        loan = 1_500_000
        rate = 0.035 / 12
        months = 360
        pmt = monthly_payment(loan, rate, months)
        r = judge_payoff(income, expenses, pmt, loan, rate, months)
        balance = loan
        for _ in range(120):
            interest = balance * rate
            balance -= (pmt - interest)
        expected_rp = max(balance, 0.0)
        assert abs(r['remaining_principal'] - expected_rp) < SIM_TOLERANCE

    def test_total_interest_tracking(self):
        loan = 800_000
        rate = 0.04 / 12
        months = 240
        pmt = monthly_payment(loan, rate, months)
        balance = loan
        total_paid = 0.0
        for _ in range(240):
            if balance <= 0:
                break
            interest = balance * rate
            payment = min(pmt, balance + interest)
            total_paid += payment
            balance = balance + interest - payment
        assert abs(total_paid - pmt * 240) < SIM_TOLERANCE


if __name__ == '__main__':
    pytest.main([__file__, '-v'])
