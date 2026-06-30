from odoo import models, fields, api, _
from odoo.exceptions import ValidationError
import logging

_logger = logging.getLogger(__name__)

class TradingTrade(models.Model):
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
    price = fields.Monetary(string='Purchase Price', required=False)
    
    # Sales side fields
    sales_price = fields.Monetary(string="Sales Price")

    currency_id = fields.Many2one(
        'res.currency',
        string='Currency',
        default=lambda self: self.env.company.currency_id
    )

    status = fields.Selection(
        [('draft','Draft'),
         ('confirmed','Confirmed'),
         ('closed','Closed')],
        default='draft',
        tracking=True
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
    
    # Sales totals
    total_sold_quantity = fields.Float(
        string='Total Sold Quantity',
        compute='_compute_sales_totals',
        store=True,
        help='Total quantity sold across all sale orders'
    )
    
    total_sales_value = fields.Monetary(
        string='Total Sales Value',
        compute='_compute_sales_totals',
        store=True,
        currency_field='currency_id',
        help='Total value of all sales (based on sale order totals)'
    )
    
    average_sale_price = fields.Monetary(
        string='Average Sale Price',
        compute='_compute_sales_totals',
        store=True,
        currency_field='currency_id',
        help='Average price per unit from all sales'
    )
    
    # Position tracking
    open_position_quantity = fields.Float(
        string='Open Position Quantity',
        compute='_compute_position',
        store=True,
        help='Net open position: Purchase Qty - Sold Qty (positive = long, negative = short)'
    )
    
    is_fully_matched = fields.Boolean(
        string='Fully Matched',
        compute='_compute_position',
        store=True,
        help='Both purchase and sale exist and quantities match (position closed)'
    )
    
    # P&L calculations
    realized_pnl = fields.Monetary(
        string='Realized P&L',
        compute='_compute_pnl',
        store=True,
        currency_field='currency_id',
        help='Profit/Loss on matched portion (when both purchase and sale exist)'
    )
    
    unrealized_pnl = fields.Monetary(
        string='Unrealized P&L',
        compute='_compute_pnl',
        store=True,
        currency_field='currency_id',
        help='Profit/Loss on unmatched portion (open position)'
    )
    
    current_price = fields.Float(
        string='Current/Market Price',
        help='Current market price for unrealized P&L calculation',
        digits=(16, 2),
        tracking=True
    )
    
    total_pnl = fields.Monetary(
        string='Total P&L',
        compute='_compute_pnl',
        store=True,
        currency_field='currency_id',
        help='Total Profit/Loss (Realized + Unrealized)'
    )
    
    pnl_percentage = fields.Float(
        string='P&L %',
        compute='_compute_pnl',
        store=True,
        help='Profit/Loss Percentage'
    )
    
    # Value calculations
    total_purchase_cost = fields.Monetary(
        string='Total Purchase Cost',
        compute='_compute_costs',
        store=True,
        currency_field='currency_id',
        help='Total cost of purchase (Quantity × Purchase Price)'
    )
    
    total_sales_cost_basis = fields.Monetary(
        string='Total Sales Cost Basis',
        compute='_compute_costs',
        store=True,
        currency_field='currency_id',
        help='Cost basis for sold items (Sold Qty × Purchase Price)'
    )
    
    # Performance metrics
    win_rate = fields.Float(
        string='Win Rate (%)',
        compute='_compute_performance',
        store=True,
        help='Percentage of profitable trades'
    )
    
    # Computed fields
    on_hand_quantity = fields.Float(
        string='On Hand Quantity',
        compute='_compute_on_hand_quantity',
        store=True,
        help="Total quantity available across all lots (from stock)"
    )
    
    lot_count = fields.Integer(
        string='Number of Lots',
        compute='_compute_lot_count',
        store=False
    )
    
    product_uom = fields.Many2one(
        string="Unit of Measure",
        related="product_id.uom_id",
        store=False,
        readonly=True
    )
    
    sale_count = fields.Integer(
        string="Sale Orders Count",
        compute="_compute_sale_count"
    )
    
    purchase_count = fields.Integer(
        string="Purchase Orders",
        compute="_compute_purchase_count"
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
    
    invoice_count = fields.Integer(string='Invoice Count', compute='_compute_invoice_count')
    
    bill_count = fields.Integer(string='Bill Count', compute='_compute_invoice_count')
    
    @api.depends('quantity', 'total_sold_quantity', 'purchase_id', 'sale_order_ids', 'sale_order_ids.state')
    def _compute_position(self):
        """Calculate open position and check if fully matched."""
        for record in self:
        
            # Determine which sides actually exist based on linked documents
            has_purchase_doc = bool(record.purchase_id)
            has_sale_docs = bool(record.sale_order_ids.filtered(lambda so: so.state in ['sale', 'done']))
        
            # CORRECTED LOGIC: Open position depends on what exists
            if has_purchase_doc and not has_sale_docs:
                # Only purchase exists = LONG position
                open_qty = record.quantity
                _logger.warning(f"   → Only purchase: LONG position of {open_qty}")
            elif has_sale_docs and not has_purchase_doc:
                # Only sale exists = SHORT position
                open_qty = -record.total_sold_quantity
            elif has_purchase_doc and has_sale_docs:
                # Both exist: net position
                open_qty = record.quantity - record.total_sold_quantity
            else:
                open_qty = 0
        
            record.open_position_quantity = open_qty
        
            # Determine has_purchase and has_sale for matching logic
            has_purchase = has_purchase_doc and record.quantity > 0
            has_sale = has_sale_docs and record.total_sold_quantity > 0
            quantities_match = abs(open_qty) < 0.001 if has_purchase and has_sale else False
        
            record.is_fully_matched = has_purchase and has_sale and quantities_match
        

    @api.depends('total_sales_value', 'total_sales_cost_basis', 'open_position_quantity', 'current_price', 'trade_type', 'quantity', 'total_sold_quantity','additional_costs', 'additional_revenue')
    def _compute_pnl(self):
        """Calculate P&L - Realized when both sides exist, Unrealized for open position"""
        for record in self:
        
            # Determine which sides exist (use same logic as _compute_position)
            has_purchase_doc = bool(record.purchase_id) and record.quantity > 0
            has_sale_docs = bool(record.sale_order_ids.filtered(lambda so: so.state in ['sale', 'done'])) and record.total_sold_quantity > 0

            # Calculate average cost including additional costs
            avg_cost_per_unit = 0
            if record.quantity > 0:
                total_cost = (record.quantity * record.price) + record.additional_costs
                avg_cost_per_unit = total_cost / record.quantity

            # REALIZED P&L: Only when BOTH purchase AND sale exist
            if has_purchase_doc and has_sale_docs:
                matched_qty = min(record.quantity, record.total_sold_quantity)

                if record.trade_type == 'long':
                    realized_value = 0.0
                    for order in record.sale_order_ids.filtered(lambda so: so.state in ['sale', 'done']):
                        for line in order.order_line:
                            if line.product_id == record.product_id:
                                realized_value += line.price_unit * line.product_uom_qty
                    # Use avg_cost_per_unit so additional costs are included
                    record.realized_pnl = realized_value - (matched_qty * avg_cost_per_unit)
                else:
                    # Short: sales value minus cost basis (including additional costs)
                    record.realized_pnl = record.total_sales_value - (matched_qty * avg_cost_per_unit)
            else:
                record.realized_pnl = 0.0
            # UNREALIZED P&L: Calculate based on open position
            if record.open_position_quantity != 0:
                open_qty = abs(record.open_position_quantity)

                if record.open_position_quantity > 0:
                    # LONG position (own more than sold)
                    if avg_cost_per_unit > 0 and record.current_price > 0:
                        # Market price set — proper unrealized P&L vs total cost basis
                        record.unrealized_pnl = open_qty * (record.current_price - avg_cost_per_unit)
                    elif avg_cost_per_unit > 0:
                        # No market price — show negative of total cost (money spent)
                        record.unrealized_pnl = -(open_qty * avg_cost_per_unit)
                    else:
                        record.unrealized_pnl = 0.0
                else:
                    # SHORT position (sold more than owned)
                    # Use sales_price if available, otherwise average_sale_price
                    sale_price_to_use = record.sales_price if record.sales_price > 0 else record.average_sale_price
                    if sale_price_to_use > 0 and record.current_price > 0:
                        record.unrealized_pnl = open_qty * (sale_price_to_use - record.current_price)
                        _logger.info(f"   SHORT Unrealized P&L: {open_qty} * ({sale_price_to_use} - {record.current_price}) = {record.unrealized_pnl}")
                    elif sale_price_to_use > 0:
                        # No market price — show positive of sale value received
                        record.unrealized_pnl = open_qty * sale_price_to_use
                    else:
                        record.unrealized_pnl = 0.0
            else:
                record.unrealized_pnl = 0.0

            # TOTAL P&L
            record.total_pnl = (record.realized_pnl + record.unrealized_pnl + record.additional_revenue)
            # P&L PERCENTAGE
            if record.trade_type == 'long':
                # Long: return on total cost (including additional costs)
                total_cost_base = (record.quantity * record.price) + record.additional_costs
                if total_cost_base > 0:
                    record.pnl_percentage = (record.total_pnl / total_cost_base) * 100
                else:
                    record.pnl_percentage = 0.0
            elif record.trade_type == 'short':
                # Short: gross margin on total revenue (including additional revenue)
                total_revenue_base = record.total_sales_value + record.additional_revenue
                if total_revenue_base > 0:
                    record.pnl_percentage = (record.total_pnl / total_revenue_base) * 100
                else:
                    record.pnl_percentage = 0.0
            else:
                record.pnl_percentage = 0.0
        
            # AUTO-CLOSE
            if record.is_fully_matched and record.status == 'confirmed':
                record.status = 'closed'
            
    @api.depends('sale_order_ids', 'sale_order_ids.state', 'sale_order_ids.order_line')
    def _compute_sales_totals(self):
        """Compute sales totals from confirmed sale orders"""
        for record in self:
            confirmed_orders = record.sale_order_ids.filtered(lambda so: so.state in ['sale', 'done'])
            
            total_qty = 0.0
            total_value = 0.0
            
            for order in confirmed_orders:
                for line in order.order_line:
                    if line.product_id == record.product_id:
                        total_qty += line.product_uom_qty
                        total_value += line.price_unit * line.product_uom_qty
            
            record.total_sold_quantity = total_qty
            record.total_sales_value = total_value
            record.average_sale_price = total_value / total_qty if total_qty > 0 else 0.0
            
            if total_qty > 0 and record.trade_type == 'long':
                record.sales_price = record.average_sale_price
            

    @api.depends('quantity', 'price', 'total_sold_quantity', 'additional_costs', 'additional_revenue')
    def _compute_costs(self):
        """Compute purchase costs and sales cost basis"""
        for record in self:
            if record.quantity > 0 and record.price > 0:
                record.total_purchase_cost = record.quantity * record.price
                # Cost basis for sold items = sold quantity * purchase price
                record.total_sales_cost_basis = record.total_sold_quantity * record.price
            else:
                record.total_purchase_cost = 0.0
                record.total_sales_cost_basis = 0.0
                
    @api.depends('sale_order_ids', 'sale_order_ids.state', 'sale_order_ids.order_line', 'price')
    def _compute_performance(self):
        """Compute win rate based on realized P&L"""
        for record in self:
            if record.realized_pnl > 0:
                record.win_rate = 100.0
            elif record.realized_pnl < 0:
                record.win_rate = 0.0
            else:
                record.win_rate = 0.0

    @api.depends('lot_ids', 'lot_ids.product_qty')
    def _compute_total_lot_quantity(self):
        """Compute total quantity from all lots"""
        for record in self:
            total = 0.0
            for lot in record.lot_ids:
                total += lot.product_qty
            record.total_lot_quantity = total

    @api.depends('lot_ids', 'lot_ids.quant_ids', 'lot_ids.quant_ids.quantity')
    def _compute_on_hand_quantity(self):
        """Compute total on-hand quantity from all lots"""
        for record in self:
            total_qty = 0.0
            if record.lot_ids:
                for lot in record.lot_ids:
                    quant_qty = sum(lot.quant_ids.filtered(lambda q: q.location_id.usage == 'internal').mapped('quantity'))
                    total_qty += quant_qty
            record.on_hand_quantity = total_qty

    @api.depends('lot_ids')
    def _compute_lot_count(self):
        """Compute number of lots associated with this trade"""
        for record in self:
            record.lot_count = len(record.lot_ids)

    def _compute_purchase_count(self):
        for record in self:
            record.purchase_count = 1 if record.purchase_id else 0

    def _compute_sale_count(self):
        for record in self:
            record.sale_count = len(record.sale_order_ids)

    def _compute_all_trade_fields(self):
        """Trigger recomputation of all computed fields"""
        for record in self:
            record._compute_sales_totals()
            record._compute_position()
            record._compute_costs()
            record._compute_pnl()
            record._compute_performance()
            record._compute_on_hand_quantity()
            record._compute_total_lot_quantity()
            record._compute_invoice_count()
    
    @api.depends('invoice_ids', 'invoice_ids.move_type', 'invoice_ids.state')
    def _compute_invoice_count(self):
        for record in self:
            moves = self.env['account.move'].search([('trade_id', '=', record.id)])
        
            invoices = moves.filtered(lambda m: m.move_type in ['out_invoice', 'out_refund'])
            bills = moves.filtered(lambda m: m.move_type in ['in_invoice', 'in_refund'])
        
        
            record.invoice_count = len(invoices)
            record.bill_count = len(bills)
        
    def action_view_purchase(self):
        self.ensure_one()
        if not self.purchase_id:
            return False
        return {
            'type': 'ir.actions.act_window',
            'name': 'Purchase Order',
            'res_model': 'purchase.order',
            'view_mode': 'form',
            'res_id': self.purchase_id.id,
            'target': 'current',
        }
    
    def action_view_lots(self):
        """View all lots associated with this trade"""
        self.ensure_one()
        if not self.lot_ids:
            return False
        
        action = self.env.ref('stock.action_production_lot_form').read()[0]
        if len(self.lot_ids) == 1:
            action['views'] = [(False, 'form')]
            action['res_id'] = self.lot_ids.id
        else:
            action['domain'] = [('id', 'in', self.lot_ids.ids)]
        return action
        
    def action_view_sales(self):
        self.ensure_one()
        if not self.sale_order_ids:
            return False
        action = self.env.ref('sale.action_orders').read()[0]
        if len(self.sale_order_ids) == 1:
            action['views'] = [(False, 'form')]
            action['res_id'] = self.sale_order_ids.id
        else:
            action['domain'] = [('id', 'in', self.sale_order_ids.ids)]
        return action
    
    def action_view_invoices(self):
        self.ensure_one()
        return {
            'type': 'ir.actions.act_window',
            'name': 'Invoices',
            'res_model': 'account.move',
            'view_mode': 'list,form',
            'domain': [('trade_id', '=', self.id), ('move_type', 'in', ['out_invoice', 'out_refund'])],
            'context': {'default_trade_id': self.id, 'default_move_type': 'out_invoice'},
        }
        
    def action_view_bills(self):
        self.ensure_one()
        return {
            'type': 'ir.actions.act_window',
            'name': 'Bills',
            'res_model': 'account.move',
            'view_mode': 'list,form',
            'domain': [('trade_id', '=', self.id), ('move_type', 'in', ['in_invoice', 'in_refund'])],
            'context': {'default_trade_id': self.id, 'default_move_type': 'in_invoice'},
        }
    
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
        if any(field in vals for field in ['quantity', 'price', 'current_price', 'lot_ids', 'sale_order_ids', 'purchase_id']):
            self._compute_all_trade_fields()
        
        return result