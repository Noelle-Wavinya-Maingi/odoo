from odoo import models, fields, api
import logging

_logger = logging.getLogger(__name__)

class TradingFutures(models.Model):
    _name = 'trading.futures'
    _description = 'Trading Futures'
    _inherit = ['mail.thread', 'mail.activity.mixin']
    _order = 'trade_id, open_date, id'  # Add default ordering
    
    name = fields.Char(string='Future Name', copy=False, compute='_compute_name', store=True)
    trade_id = fields.Many2one('trading.trade', string='Trade', required=True, ondelete='cascade')
    contract_type = fields.Selection([('cocoa_future','Cocoa Future')], string='Contract Type', default='cocoa_future')
    contract_price = fields.Float(string='Contract Price', required=True, digits=(16, 2))
    contract_quantity = fields.Float(string='Contract Quantity', required=True, digits=(16, 2))
    open_date = fields.Date(string='Open Date', required=True, default=fields.Date.today)
    close_date = fields.Date(string='Close Date')
    status = fields.Selection([('open','Open'),('closed','Closed')], default='open', tracking=True)
    currency_id = fields.Many2one(related="trade_id.currency_id", store=True)
    product_uom = fields.Many2one(related="trade_id.product_uom", store=True, readonly=True)
    
    # P&L fields
    pnl = fields.Float(
        string='P&L',
        compute='_compute_pnl',
        store=True,
        digits=(16, 2),
        help='Profit and Loss'
    )
    
    pnl_percentage = fields.Float(
        string='P&L %',
        compute='_compute_pnl',
        store=True,
        digits=(16, 2),
        help='Profit and Loss Percentage'
    )
    
    current_price = fields.Float(
        string='Current/Market Price',
        help='Current market price for open positions',
        digits=(16, 2),
        default=lambda self: self._get_default_current_price(),
        tracking=True
    )
    
    # Delivery Tracking
    delivered_quantity = fields.Float(
        string='Delivered Quantity',
        default=0.0,
        digits=(16, 2),
        help='Total quantity delivered against this future'
    )
    
    # Balance Fields
    open_balance = fields.Float(
        string='Open Balance',
        compute='_compute_balances',
        store=True,
        digits=(16, 2),
        help='Remaining quantity to be delivered'
    )
    
    closed_balance = fields.Float(
        string='Closed Balance',
        compute='_compute_balances',
        store=True,
        digits=(16, 2),
        help='Quantity already delivered'
    )
    
    # Value Fields at Contract Price
    closed_value_at_contract = fields.Float(
        string='Closed Value (Contract)',
        compute='_compute_values',
        store=True,
        digits=(16, 2),
        help='Value of delivered portion at contract price'
    )
    
    open_value_at_contract = fields.Float(
        string='Open Value (Contract)',
        compute='_compute_values',
        store=True,
        digits=(16, 2),
        help='Value of undelivered portion at contract price'
    )
    
    total_contract_value = fields.Float(
        string='Total Contract Value',
        compute='_compute_values',
        store=True,
        digits=(16, 2),
        help='Total contract value (Quantity × Price)'
    )
    
    # Actual Sales Values (from sale orders, not deliveries)
    closed_sales_value = fields.Float(
        string='Closed Sales Value',
        compute='_compute_sales_values',
        store=True,
        digits=(16, 2),
        help='Actual sales value from confirmed sale orders'
    )
    
    # Net Value (actual sales value + open balance × contract price)
    net_value = fields.Float(
        string='Net Value',
        compute='_compute_net_value',
        store=True,
        digits=(16, 2),
        help='Actual value: (Sales value) + (Open at contract price)'
    )
    
    # Realized/Unrealized P&L
    realized_pnl = fields.Float(
        string='Realized P&L',
        compute='_compute_pnl_details',
        store=True,
        digits=(16, 2),
        help='Profit/Loss on sold portion (based on sale orders)'
    )
    
    unrealized_pnl = fields.Float(
        string='Unrealized P&L',
        compute='_compute_pnl_details',
        store=True,
        digits=(16, 2),
        help='Profit/Loss on open portion (based on current price)'
    )
    
    # For tracking deliveries with their individual sale prices
    # delivery_line_ids = fields.One2many(
    #     'trading.future.delivery.line',
    #     'future_id',
    #     string='Delivery Lines'
    # )
    
    # Sale Order relationship
    # sale_order_ids = fields.One2many(
    #     'sale.order',
    #     'futures_id',
    #     string='Sale Orders'
    # )
    
    # Add a sequence field for ordering
    sequence = fields.Integer(
        string='Sequence',
        default=10,
        help='Sequence for ordering futures under the same trade'
    )
    
    def _get_default_current_price(self):
        """Get default current price - you can customize this logic"""
        return self.contract_price
    
    @api.depends('contract_price', 'contract_quantity', 'current_price', 'status', 
                 'realized_pnl', 'unrealized_pnl', 'close_date')
    def _compute_pnl(self):
        for record in self:
            if record.status == 'closed':
                # For closed positions, P&L is just the realized P&L
                record.pnl = record.realized_pnl
            else:
                # For open positions, show total P&L (realized + unrealized)
                record.pnl = record.realized_pnl + record.unrealized_pnl
            
            # Calculate P&L percentage
            total_cost = record.contract_price * record.contract_quantity
            if total_cost != 0:
                record.pnl_percentage = (record.pnl / total_cost) * 100
            else:
                record.pnl_percentage = 0
                
    @api.depends('contract_quantity', 'delivered_quantity')
    def _compute_balances(self):
        for future in self:
            _logger.info(f"🫠 Computing balances for future {future.name}")
            future.closed_balance = sum(future.sale_order_ids.filtered(lambda so: so.state in ['sale', 'done']).mapped('order_line.product_uom_qty'))
            future.open_balance = future.contract_quantity - future.closed_balance
    
    @api.depends('contract_quantity', 'contract_price', 'closed_balance', 'open_balance')
    def _compute_values(self):
        for future in self:
            future.total_contract_value = future.contract_quantity * future.contract_price
            future.closed_value_at_contract = future.closed_balance * future.contract_price
            future.open_value_at_contract = future.open_balance * future.contract_price
    
    @api.depends()
    def _compute_sales_values(self):
        """Compute closed sales value from CONFIRMED sale orders only"""
        for future in self:
            # Only include confirmed/done sale orders
            confirmed_orders = future.sale_order_ids.filtered(lambda so: so.state in ['sale', 'done'])
            future.closed_sales_value = sum(confirmed_orders.mapped('amount_untaxed'))
            _logger.info(f"😎 Sales values computed from {len(confirmed_orders)} confirmed sale orders: {future.closed_sales_value}")
    
    @api.depends('closed_sales_value', 'open_balance', 'contract_price')
    def _compute_net_value(self):
        for future in self:
            open_value_contract = future.open_balance * future.contract_price
            future.net_value = future.closed_sales_value + open_value_contract
    
    @api.depends(
                 'closed_balance', 'contract_price', 'current_price')
    def _compute_pnl_details(self):
        for future in self:
            # Realized P&L = Sales Value - (Closed Balance × Contract Price)
            future.realized_pnl = future.closed_sales_value - (future.closed_balance * future.contract_price)
            
            # Unrealized P&L on open portion
            if future.status == 'open' and future.open_balance > 0:
                if future.trade_id.trade_type == 'long':
                    future.unrealized_pnl = future.open_balance * (future.current_price - future.contract_price)
                else:
                    future.unrealized_pnl = (future.contract_price - future.current_price) * future.open_balance
            else:
                future.unrealized_pnl = 0.0
    
    @api.depends('trade_id', 'contract_type', 'open_date', 'sequence')
    def _compute_name(self):
        """Generate unique names for futures under the same trade"""
        for record in self:
            if record.trade_id and record.contract_type:
                date_str = record.open_date.strftime('%Y-%m-%d') if record.open_date else ''
                
                # Count how many futures exist for this trade with the same open date
                domain = [
                    ('trade_id', '=', record.trade_id.id),
                    ('open_date', '=', record.open_date),
                    ('id', '<=', record.id)  # Include current and previous records
                ]
                
                # Get all futures for this trade with same date
                same_trade_futures = self.search(domain, order='id')
                
                # Find the index of the current record (1-based)
                index = 1
                for i, future in enumerate(same_trade_futures, 1):
                    if future.id == record.id:
                        index = i
                        break
                
                # If there are multiple futures with same date, add the index
                if len(same_trade_futures) > 1:
                    record.name = f"{record.trade_id.name} - {record.contract_type} - {date_str} - #{index}"
                else:
                    # Check if there are any other futures for this trade (different dates)
                    other_futures = self.search_count([
                        ('trade_id', '=', record.trade_id.id),
                        ('id', '!=', record.id)
                    ])
                    
                    if other_futures > 0:
                        # If there are other futures for this trade, add a sequence based on creation order
                        all_trade_futures = self.search([('trade_id', '=', record.trade_id.id)], order='id')
                        global_index = 1
                        for i, future in enumerate(all_trade_futures, 1):
                            if future.id == record.id:
                                global_index = i
                                break
                        record.name = f"{record.trade_id.name} - {record.contract_type} - {date_str} - #{global_index}"
                    else:
                        # First/only future for this trade
                        record.name = f"{record.trade_id.name} - {record.contract_type} - {date_str}"
            else:
                record.name = "New Future"
    
    @api.model_create_multi
    def create(self, vals_list):
        """Set sequence and name on creation"""
        for vals in vals_list:
            if vals.get('trade_id'):
                # Count existing futures for this trade
                future_count = self.search_count([('trade_id', '=', vals['trade_id'])])
                vals['sequence'] = future_count + 1
        return super().create(vals_list)
    
    def action_close_future(self):
        """Manually close a future"""
        for future in self:
            if future.status == 'open':
                future.write({
                    'status': 'closed',
                    'close_date': fields.Date.today()
                })
                future.message_post(
                    body="Future manually closed.",
                    subject="Future Closed"
                )
    
    def action_reopen_future(self):
        """Reopen a closed future"""
        for future in self:
            if future.status == 'closed':
                future.write({
                    'status': 'open',
                    'close_date': False
                })
                future.message_post(
                    body="Future reopened.",
                    subject="Future Reopened"
                )
    
    def write(self, vals):
        """Override write to ensure proper recomputation"""
        result = super().write(vals)
        
        # If status changed to closed, ensure close_date is set
        if vals.get('status') == 'closed' and not vals.get('close_date'):
            self.write({'close_date': fields.Date.today()})
        
        # If current_price changed, trigger P&L recomputation
        if 'current_price' in vals:
            self._compute_pnl_details()
            self._compute_pnl()
            _logger.info(f"😃 Current price updated, P&L recomputed for {self.name}")
        
        # If delivered_quantity changed, trigger recomputation
        if 'delivered_quantity' in vals:
            self._compute_balances()
            self._compute_values()
            self._compute_net_value()
            self._compute_pnl_details()
            self._compute_pnl()
            
        return result
    
    @api.onchange('close_date')
    def _onchange_contract_price(self):
        for record in self:
            if record.close_date:
                _logger.info(f"😃 Well i have been triggered.")


class TradingFutureDeliveryLine(models.Model):
    _name = 'trading.future.delivery.line'
    _description = 'Future Delivery Line'
    _order = 'delivery_date desc'
    
    future_id = fields.Many2one('trading.futures', string='Future', required=True, ondelete='cascade')
    picking_id = fields.Many2one('stock.picking', string='Delivery Order', required=True)
    lot_id = fields.Many2one('stock.lot', string='Lot/Serial Number')
    quantity = fields.Float(string='Quantity', required=True, digits=(16, 2))
    sale_price = fields.Float(string='Sale Price', digits=(16, 2), required=True)
    delivery_date = fields.Datetime(string='Delivery Date', default=fields.Datetime.now)
    
    # Computed fields for this delivery line
    contract_value = fields.Float(
        string='Contract Value',
        compute='_compute_values',
        digits=(16, 2),
        store=True
    )
    
    sales_value = fields.Float(
        string='Sales Value',
        compute='_compute_values',
        digits=(16, 2),
        store=True
    )
    
    realized_pnl = fields.Float(
        string='Realized P&L',
        compute='_compute_values',
        digits=(16, 2),
        store=True,
        help='Profit/Loss on this delivery'
    )
    
    # Related fields for context
    sale_order_id = fields.Many2one('sale.order', string='Sale Order', related='picking_id.sale_id', store=True)
    partner_id = fields.Many2one('res.partner', string='Customer', related='picking_id.partner_id', store=True)
    
    @api.depends('quantity', 'sale_price', 'future_id.contract_price')
    def _compute_values(self):
        for line in self:
            contract_price = line.future_id.contract_price or 0
            line.contract_value = line.quantity * contract_price
            line.sales_value = line.quantity * (line.sale_price or 0)
            line.realized_pnl = line.sales_value - line.contract_value
    
    def write(self, vals):
        """Override write to trigger future recomputation"""
        result = super().write(vals)
        
        # Trigger recomputation on related futures
        if any(field in vals for field in ['quantity', 'sale_price']):
            self.mapped('future_id')._compute_sales_values()
            self.mapped('future_id')._compute_net_value()
            self.mapped('future_id')._compute_pnl_details()
            self.mapped('future_id')._compute_pnl()
            
        return result
    
    @api.model_create_multi
    def create(self, vals_list):
        records = super().create(vals_list)
        
        # Trigger recomputation on related futures
        for record in records:
            if record.future_id:
                record.future_id._compute_sales_values()
                record.future_id._compute_net_value()
                record.future_id._compute_pnl_details()
                record.future_id._compute_pnl()
                
        return records