from odoo import models, fields, api, _
from odoo.exceptions import ValidationError
import logging

_logger = logging.getLogger(__name__)

class TradingTrade(models.Model):
    """Core model definition: fields, sequencing, status workflow."""
    _name = 'trading.trade'
    _description = 'Trading Trade'
    _inherit = ['mail.thread', 'mail.activity.mixin']

    name = fields.Char(
        string="Trade Name",
        required=True,
        copy=False,
        default="New",
        readonly=True,
    )

    trade_type = fields.Selection(
        [('short', 'Short'), ('long', 'Long')],
        string="Trade Type",
        required=True
    )

    # Many2many to support multiple lots with quantity tracking
    lot_ids = fields.Many2many(
        'stock.lot',
        string="Lots",
        help="Lots associated with this trade (automatically set when receiving goods)"
    )
    
    # Track total quantity from all lots
    total_lot_quantity = fields.Float(
        string='Total Lot Quantity',
        compute='_compute_total_lot_quantity',
        store=True,
        help='Total quantity from all linked lots'
    )

    # Purchase side fields (can be 0 if no purchase yet)
    quantity = fields.Float(string='Purchase Quantity', required=False, default=0.0)
    price = fields.Monetary(string='Purchase Price', required=False, currency_field='purchase_currency_id')
    purchase_currency_id = fields.Many2one('res.currency', string='Purchase Currency', default=lambda self: self.env.company.currency_id)
    purchase_date = fields.Date(string='Purchase Date', default=fields.Date.context_today, help='Used to look up the FX rate when converting to reporting currency')
    
    # Sales side fields
    sales_price = fields.Monetary(
        string="Sales Price",
        currency_field='sale_currency_id',
        compute='_compute_sales_price_and_currency',
        store=True,
        readonly=False,
        help="Actual sale price per unit, in its original sale currency. "
             "Auto-filled from confirmed Sale Orders for long trades; "
             "editable manually otherwise (e.g. short trades)."
    )
    sale_currency_id = fields.Many2one(
        'res.currency',
        string='Sale Currency',
        compute='_compute_sales_price_and_currency',
        store=True,
        readonly=False,
        default=lambda self: self.env.company.currency_id,
    )

    # ── Reporting currency — all P&L expressed in this ───────────────────
    currency_id = fields.Many2one(
        'res.currency',
        string='Currency',
        default=lambda self: self.env.company.currency_id
    )

    # ── Converted prices in reporting currency ────────────────────────────
    price_in_base_currency = fields.Monetary(
        string='Purchase Price (Reporting Currency)',
        compute='_compute_currency_conversions',
        store=True,
        currency_field='currency_id',
    )
    sales_price_in_base_currency = fields.Monetary(
        string='Sales Price (Reporting Currency)',
        compute='_compute_currency_conversions',
        store=True,
        currency_field='currency_id',
    )

    # ── Company (needed for _convert()) ──────────────────────────────────
    company_id = fields.Many2one(
        'res.company',
        string='Company',
        default=lambda self: self.env.company,
    )

    status = fields.Selection(
        [('draft','Draft'),
         ('confirmed','Confirmed'),
         ('closed','Closed')],
        default='draft',
        tracking=True,
        group_expand='_group_expand_status'
    )
    
    product_id = fields.Many2one(
        'product.product',
        string='Product',
        required=True,
        help="Product associated with this trade"
    )
    
    # Sale Orders linked to this trade
    sale_order_ids = fields.Many2many(
        'sale.order',
        string='Sale Orders',
        help="Sale orders that have sold from this trade"
    )
    
    # Purchase Order linked to this trade
    purchase_id = fields.Many2one('purchase.order', string='Purchase Order', ondelete='set null')
    
    # NOTE: Monetary fields take their decimal precision from the linked
    # currency, not a 'digits' kwarg -- Float is the only field type that
    # accepts 'digits' directly. Passing it here is a no-op that Odoo 19
    # warns about on every load.
    current_price = fields.Monetary(
        string='Current/Market Price',
        currency_field='current_price_currency_id',
        help='Current market price for unrealized P&L calculation, in its own currency.',
        tracking=True
    )
    
    current_price_currency_id = fields.Many2one(
        'res.currency',
        string="Market Price Currency",
        default=lambda self: self.env.company.currency_id
    )
    
    current_price_in_base_currency = fields.Monetary(
        string="Current/Market Price (Reporting Currency)",
        compute="_compute_currency_conversions",
        store=True,
        currency_field='currency_id',
    )
    
    additional_costs = fields.Float(
        string="Additional Costs",
        default = 0.0
    )
    
    additional_revenue = fields.Float(
        string="Additional Revenue",
        default = 0.0
    )
    
    invoice_ids = fields.One2many('account.move', 'trade_id', string='Invoices')

    # NOTE: Trade Budgets (budget_ids, budget_id, budget_state,
    # action_create_budget, action_view_budget) are an OPTIONAL feature and
    # deliberately do NOT live here. Core trading has no dependency on
    # 'trading.trade.budget' at all -- that model, and every field/method
    # referencing it, lives in the separate 'trading_budget' bridge module
    # (see trading_budget/models/trading_trade.py, an _inherit extension of
    # this same model), so that Trade Budgets can be installed/uninstalled
    # independently of Trading itself.
    #
    # has_budget IS kept here, but as a plain non-computed field defaulting
    # to False -- this is a stub purely so that trading_trade_views.xml's
    # invisible="has_budget" conditions (on cards that fall back to showing
    # unconditionally when no budget exists) always validate, even if
    # 'trading_budget' is never installed. 'trading_budget' overrides this
    # same field, turning it into a real compute based on budget_ids.
    has_budget = fields.Boolean('Has Budget', default=False)

    product_uom = fields.Many2one(
        string="Unit of Measure",
        related="product_id.uom_id",
        store=False,
        readonly=True
    )

    # ═══════════════════ KANBAN/LIST GROUP ORDER ═════════════════════════
    @api.model
    def _group_expand_status(self, states, domain):
        """Force kanban/list group-by columns to follow the declared selection order (Draft, Confirmed, Closed) instead of the defaultalphabetical fallback ('closed' < 'confirmed' < 'draft')."""
        return [key for key, _label in self._fields['status'].selection]

    # ═══════════════════ CRUD / WORKFLOW ══════════════════════════════════
    @api.model_create_multi
    def create(self, vals_list):
        for vals in vals_list:
            if vals.get('name', 'New') == 'New':
                trade_type = vals.get('trade_type')
                if trade_type == 'long':
                    seq_code = 'trading.trade.long'
                elif trade_type == 'short':
                    seq_code = 'trading.trade.short'
                else:
                    seq_code = 'trading.trade.long'
                vals['name'] = self.env['ir.sequence'].next_by_code(seq_code) or 'New'

            # Ensure product_id is set
            if 'product_id' not in vals or not vals.get('product_id'):
                _logger.warning(f"Creating trade without product_id!")
                
        return super().create(vals_list)

    def action_confirm(self):
        """Open the trade for trading"""
        for trade in self:
            if trade.status == 'draft':
                _logger.info(f"🌼 Confirming trade {trade.name}")
                trade.write({'status': 'confirmed'})
                trade._compute_all_trade_fields()
        return True

    def write(self, vals):
        """Override write to trigger recomputation when needed"""
        result = super().write(vals)
        
        # Trigger recomputation if relevant fields changed
        if any(field in vals for field in ['quantity', 'price', 'current_price', 'lot_ids', 'sale_order_ids', 'purchase_id', 'purchase_currency_id', 'purchase_date',]):
            self._compute_all_trade_fields()
        
        return result

    def _sync_budget_line_for_move(self, move, field_name, amount):
        """No-op by default -- overridden by 'trading_budget' if installed.

        account_move_lifecycle.py calls this unconditionally whenever a
        move's contribution to additional_costs/additional_revenue changes,
        regardless of whether the optional Trade Budget feature is present.
        Keeping a harmless no-op here means core Trading never breaks if
        'trading_budget' isn't installed; the bridge module's _inherit
        override supplies the real budget-line-syncing behavior.
        """
        return

    def _remove_budget_line_for_move(self, move):
        """No-op by default -- overridden by 'trading_budget' if installed.
        See _sync_budget_line_for_move for why this stub exists in core."""
        return

    def _compute_all_trade_fields(self):
        """Trigger recomputation of all computed fields."""
        for record in self:
            record._compute_sales_price_and_currency()
            record._compute_currency_conversions()
            record._compute_sales_totals()
            record._compute_position()
            record._compute_costs()
            record._compute_pnl()
            record._compute_performance()
            record._compute_on_hand_quantity()
            record._compute_total_lot_quantity()
            record._compute_invoice_count()