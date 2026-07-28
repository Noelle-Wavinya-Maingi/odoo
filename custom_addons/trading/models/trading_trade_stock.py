import logging
from odoo import models, fields, api

_logger = logging.getLogger(__name__)


class TradingTradeStock(models.Model):
    """Lot-linked and on-hand-quantity computations."""
    _inherit = 'trading.trade'

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

    @api.depends('lot_ids', 'lot_ids.product_qty')
    def _compute_total_lot_quantity(self):
        for record in self:
            total = 0.0
            for lot in record.lot_ids:
                total += lot.product_qty
            record.total_lot_quantity = total

    @api.depends('lot_ids', 'lot_ids.quant_ids', 'lot_ids.quant_ids.quantity')
    def _compute_on_hand_quantity(self):
        for record in self:
            total_qty = 0.0
            if record.lot_ids:
                for lot in record.lot_ids:
                    quant_qty = sum(lot.quant_ids.filtered(lambda q: q.location_id.usage == 'internal').mapped('quantity'))
                    total_qty += quant_qty
            record.on_hand_quantity = total_qty
            _logger.info(f"📦 {record.name}: on_hand_quantity = {record.on_hand_quantity} " f"from lots {[lot.name for lot in record.lot_ids]}")

    @api.depends('lot_ids')
    def _compute_lot_count(self):
        for record in self:
            record.lot_count = len(record.lot_ids)

    def action_view_lots(self):
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