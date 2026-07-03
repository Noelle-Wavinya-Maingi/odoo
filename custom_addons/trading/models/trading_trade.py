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
        inverse='_inverse_sales_price',
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
        inverse='_inverse_sale_currency_id',
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
    
    current_price = fields.Float(
        string='Current/Market Price',
        help='Current market price for unrealized P&L calculation',
        digits=(16, 2),
        tracking=True
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
    
    product_uom = fields.Many2one(
        string="Unit of Measure",
        related="product_id.uom_id",
        store=False,
        readonly=True
    )

    # ═══════════════════ KANBAN/LIST GROUP ORDER ═════════════════════════
    @api.model
    def _group_expand_status(self, states, domain):
        """Force kanban/list group-by columns to follow the declared selection order (Draft, Confirmed, Closed) instead of the default alphabetical fallback ('closed' < 'confirmed' < 'draft')."""
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