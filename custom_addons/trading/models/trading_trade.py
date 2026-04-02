from odoo import models, fields, api
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

    quantity = fields.Float(string='Purchase Quantity', required=True)
    price = fields.Monetary(string='Purchase Price', required=True)
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
    
    remaining_quantity = fields.Float(
        string='Remaining Quantity',
        compute='_compute_sales_totals',
        store=True,
        help='Quantity still available to sell (Purchase Qty - Sold Qty)'
    )
    
    # P&L calculations
    realized_pnl = fields.Monetary(
        string='Realized P&L',
        compute='_compute_pnl',
        store=True,
        currency_field='currency_id',
        help='Profit/Loss on sold portion (Sales Value - (Sold Qty × Purchase Price))'
    )
    
    unrealized_pnl = fields.Monetary(
        string='Unrealized P&L',
        compute='_compute_pnl',
        store=True,
        currency_field='currency_id',
        help='Profit/Loss on remaining quantity (based on current market price)'
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
        help='Profit/Loss Percentage based on total purchase cost'
    )
    
    # Value calculations
    total_purchase_cost = fields.Monetary(
        string='Total Purchase Cost',
        compute='_compute_purchase_cost',
        store=True,
        currency_field='currency_id',
        help='Total cost of purchase (Quantity × Purchase Price)'
    )
    
    sold_cost = fields.Monetary(
        string='Cost of Goods Sold',
        compute='_compute_purchase_cost',
        store=True,
        currency_field='currency_id',
        help='Cost of sold portion (Sold Qty × Purchase Price)'
    )
    
    remaining_cost = fields.Monetary(
        string='Remaining Cost',
        compute='_compute_purchase_cost',
        store=True,
        currency_field='currency_id',
        help='Cost of remaining quantity (Remaining Qty × Purchase Price)'
    )
    
    # Performance metrics
    win_rate = fields.Float(
        string='Win Rate (%)',
        compute='_compute_performance',
        store=True,
        help='Percentage of profitable sales'
    )
    
    total_profitable_sales = fields.Integer(
        string='Profitable Sales',
        compute='_compute_performance',
        store=True,
        help='Number of profitable sale orders'
    )
    
    total_loss_sales = fields.Integer(
        string='Loss Sales',
        compute='_compute_performance',
        store=True,
        help='Number of loss-making sale orders'
    )
    
    # Purchase order link
    purchase_id = fields.Many2one('purchase.order', string='Purchase Order', ondelete='cascade')
    purchase_count = fields.Integer(
        string="Purchase Orders",
        compute="_compute_purchase_count"
    )
    
    # Computed fields - Sums across all lots
    on_hand_quantity = fields.Float(
        string='On Hand Quantity',
        compute='_compute_on_hand_quantity',
        store=False,
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
        string="Sale Orders",
        compute="_compute_sale_count"
    )
    
    @api.depends('lot_ids', 'lot_ids.product_qty')
    def _compute_total_lot_quantity(self):
        """Compute total quantity from all lots"""
        for record in self:
            total = 0.0
            for lot in record.lot_ids:
                total += lot.product_qty
                _logger.info(f"Lot {lot.name}: product_qty = {lot.product_qty}")
            record.total_lot_quantity = total
            _logger.info(f"Trade {record.name}: Total lot quantity = {total}")

    @api.depends('sale_order_ids', 'sale_order_ids.state', 'sale_order_ids.order_line')
    def _compute_sales_totals(self):
        """Compute sales totals from confirmed sale orders"""
        for record in self:
            confirmed_orders = record.sale_order_ids.filtered(lambda so: so.state in ['sale', 'done'])
            
            total_qty = 0.0
            total_value = 0.0
            
            for order in confirmed_orders:
                for line in order.order_line:
                    total_qty += line.product_uom_qty
                    total_value += line.price_unit * line.product_uom_qty
            
            record.total_sold_quantity = total_qty
            record.total_sales_value = total_value
            record.average_sale_price = total_value / total_qty if total_qty > 0 else 0.0
            record.remaining_quantity = record.quantity - total_qty
            
            _logger.info(f"📊 Trade {record.name}: Sold {total_qty}/{record.quantity}, Sales Value: {total_value}")

    @api.depends('quantity', 'price', 'total_sold_quantity')
    def _compute_purchase_cost(self):
        """Compute purchase cost totals"""
        for record in self:
            record.total_purchase_cost = record.quantity * record.price
            record.sold_cost = record.total_sold_quantity * record.price
            record.remaining_cost = record.remaining_quantity * record.price

    @api.depends('total_sales_value', 'sold_cost', 'remaining_quantity', 'current_price', 'trade_type')
    def _compute_pnl(self):
        """Compute P&L calculations"""
        for record in self:
            # Realized P&L = Sales Value - Cost of Sold Goods
            record.realized_pnl = record.total_sales_value - record.sold_cost
            
            # Unrealized P&L = Remaining Quantity × (Current Price - Purchase Price)
            if record.remaining_quantity > 0 and record.current_price:
                if record.trade_type == 'long':
                    record.unrealized_pnl = record.remaining_quantity * (record.current_price - record.price)
                else:  # short
                    record.unrealized_pnl = record.remaining_quantity * (record.price - record.current_price)
            else:
                record.unrealized_pnl = 0.0
            
            # Total P&L
            record.total_pnl = record.realized_pnl + record.unrealized_pnl
            
            # P&L Percentage
            if record.total_purchase_cost > 0:
                record.pnl_percentage = (record.total_pnl / record.total_purchase_cost) * 100
            else:
                record.pnl_percentage = 0.0

    @api.depends('sale_order_ids', 'sale_order_ids.state', 'sale_order_ids.order_line', 'price')
    def _compute_performance(self):
        """Compute win rate and other performance metrics"""
        for record in self:
            profitable = 0
            loss = 0
            
            for order in record.sale_order_ids.filtered(lambda so: so.state in ['sale', 'done']):
                for line in order.order_line:
                    sale_value = line.price_unit * line.product_uom_qty
                    cost_value = line.product_uom_qty * record.price
                    pnl = sale_value - cost_value
                    
                    if pnl > 0:
                        profitable += 1
                    elif pnl < 0:
                        loss += 1
            
            record.total_profitable_sales = profitable
            record.total_loss_sales = loss
            
            total = profitable + loss
            record.win_rate = (profitable / total * 100) if total > 0 else 0.0

    @api.depends('lot_ids', 'lot_ids.product_qty')
    def _compute_on_hand_quantity(self):
        """Compute total on-hand quantity from all lots"""
        for record in self:
            if record.lot_ids:
                total_qty = 0.0
                for lot in record.lot_ids:
                    qty = lot.product_qty
                    total_qty += qty
                    _logger.info(f"   Lot {lot.name}: {qty} units on hand")
                record.on_hand_quantity = total_qty
                _logger.info(f"📊 Trade {record.name}: Total on-hand quantity across {len(record.lot_ids)} lots = {total_qty}")
            else:
                record.on_hand_quantity = 0.0
                _logger.info(f"📊 Trade {record.name}: No lots linked, on-hand quantity = 0")

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
            record._compute_total_lot_quantity()
            record._compute_sales_totals()
            record._compute_purchase_cost()
            record._compute_pnl()
            record._compute_performance()
            record._compute_on_hand_quantity()

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
    
    @api.onchange('on_hand_quantity')
    def _onchange_quantity(self):
        """Close a trade when the on-hand quantity is 0"""
        for record in self:
            if record.on_hand_quantity == 0 and record.status == 'confirmed':
                _logger.info(f"🏁 Trade {record.name} closed because on-hand quantity reached 0")
                record.status = 'closed'

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
        """Confirms the trade!"""
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
        if any(field in vals for field in ['quantity', 'price', 'current_price', 'lot_ids']):
            self._compute_all_trade_fields()
        
        return result