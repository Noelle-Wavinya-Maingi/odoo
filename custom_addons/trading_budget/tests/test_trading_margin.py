# -*- coding: utf-8 -*-
from odoo.tests.common import TransactionCase
from odoo.tests import tagged


@tagged('post_install', '-at_install')
class TestTradingMargin(TransactionCase):
    """Tests for the trade target margin and budget calculation engine.

    Covers the core formulas used to derive a trade's budgeted cost and
    revenue from its trade type, quoted price, quantity, and target margin.
    """

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.product = cls.env['product.product'].create({
            'name': 'Test Commodity',
            'type': 'consu',
        })

    def _create_trade(self, trade_type, **vals):
        base_vals = {
            'trade_type': trade_type,
            'product_id': self.product.id,
        }
        base_vals.update(vals)
        return self.env['trading.trade'].create(base_vals)

    # ------------------------------------------------------------------
    # Long trade: cost is known/quoted, revenue is derived from margin.
    # ------------------------------------------------------------------
    def test_long_trade_target_sales_price(self):
        """Long trade: known cost, target sale price should be cost * (1 + margin)."""
        trade = self._create_trade(
            'long',
            quantity=100.0,
            price=1000.0,
            target_margin_percent=10.0,
        )
        trade._compute_all_trade_fields()

        # avg_cost_per_unit = 1000 (no additional_costs), target margin 10%
        # target_sales_price should be 1000 * 1.10 = 1100
        self.assertAlmostEqual(trade.target_sales_price, 1100.0, places=2)

    def test_long_trade_budgeted_revenue_uses_markup_not_discount(self):
        """Long trade's budgeted revenue must be cost * (1 + margin) -- i.e.
        strictly greater than cost at a positive target margin. Revenue can
        never legitimately be lower than cost for a profitable target."""
        trade = self._create_trade(
            'long',
            quantity=100.0,
            price=1000.0,
            target_margin_percent=10.0,
        )
        budget = self.env['trading.trade.budget'].create({
            'trade_id': trade.id,
            'currency_id': trade.currency_id.id,
        })

        self.assertAlmostEqual(budget.total_budgeted_cost, 100000.0, places=2)
        self.assertGreater(budget.total_budgeted_revenue, budget.total_budgeted_cost)
        self.assertAlmostEqual(budget.total_budgeted_revenue, 110000.0, places=2)

    # ------------------------------------------------------------------
    # Short trade: revenue is known/quoted, cost is derived from margin.
    # ------------------------------------------------------------------
    def test_short_trade_budgeted_cost_is_not_zero(self):
        """Short trade: budgeted cost must be a real, derived, non-zero
        number whenever a quantity, sales price, and target margin are set."""
        trade = self._create_trade(
            'short',
            quantity=50.0,
            sales_price=200.0,
            target_margin_percent=25.0,
        )
        budget = self.env['trading.trade.budget'].create({
            'trade_id': trade.id,
            'currency_id': trade.currency_id.id,
        })

        # Revenue is the known/quoted side for a short trade.
        self.assertAlmostEqual(budget.total_budgeted_revenue, 10000.0, places=2)

        self.assertNotAlmostEqual(budget.total_budgeted_cost, 0.0, places=2)
        self.assertAlmostEqual(budget.total_budgeted_cost, 8000.0, places=2)

    def test_short_trade_cost_derived_from_revenue_and_margin(self):
        """Short trade: budgeted cost = quoted_revenue / (1 + margin_fraction)."""
        trade = self._create_trade(
            'short',
            quantity=10.0,
            sales_price=100.0,
            target_margin_percent=20.0,
        )
        budget = self.env['trading.trade.budget'].create({
            'trade_id': trade.id,
            'currency_id': trade.currency_id.id,
        })

        # quoted_revenue = 10 * 100 = 1000
        # quoted_cost = 1000 / 1.20 = 833.33...
        self.assertAlmostEqual(budget.total_budgeted_revenue, 1000.0, places=2)
        self.assertAlmostEqual(budget.total_budgeted_cost, 833.33, places=2)

    # ------------------------------------------------------------------
    # Basic P&L sanity check (no sales yet -- should not error or produce
    # nonsensical figures on a freshly created, unconfirmed trade).
    # ------------------------------------------------------------------
    def test_fresh_long_trade_has_zero_realized_pnl(self):
        """A trade with a purchase but no sale yet should show 0 realized P&L,
        not an error or a stale/garbage value."""
        trade = self._create_trade(
            'long',
            quantity=20.0,
            price=500.0,
        )
        trade._compute_all_trade_fields()

        self.assertAlmostEqual(trade.realized_pnl, 0.0, places=2)