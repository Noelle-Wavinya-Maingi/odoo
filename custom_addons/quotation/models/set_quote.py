from odoo import fields, models
from odoo.exceptions import UserError

class SetQuote(models.AbstractModel):
    _name = 'omnifreight.set.quote'
    _description = 'Function to set the quote details depending on the quote type'

        # --- Main Quote Setup Logic ---
    def set_quote(self):
        self.ensure_one()

        if not self.quote_type:
            raise UserError("Please select a Service Scope before setting the quote.")

        # Get the single Freight Forwarding Service product
        freight_product = self.env['product.product'].search([
            ('name', '=', 'Freight Forwarding Service'),
            ('categ_id.name', '=', 'Omnifreight Services')
        ], limit=1)
        
        if not freight_product:
            raise UserError("Expected product 'Freight Forwarding Service' not found. Please create it in the Omnifreight Services category.")

        SaleOrderLine = self.env['sale.order.line']
        SERVICE_DESCRIPTIONS = {
            'fob': self.QUOTE_TYPE_MAP['fob_only']['description'],
            'freight': self.QUOTE_TYPE_MAP['freight_only']['description'],
            'lod': self.QUOTE_TYPE_MAP['lod_only']['description'],
            'fob_freight': self.QUOTE_TYPE_MAP['fob_freight']['description'],
            'fob_freight_lod': self.QUOTE_TYPE_MAP['fob_freight_lod']['description'],
            'freight_dap': self.QUOTE_TYPE_MAP['freight_dap']['description'],
        }

        config = self.QUOTE_TYPE_MAP.get(self.quote_type)
        if not config:
            return

        # Clear existing service lines
        self.order_line = self.order_line.filtered(
            lambda l: l.product_id.categ_id.name != 'Omnifreight Services'
        )

        new_lines = self.env['sale.order.line']

        if self.quote_line_mode == 'individual' and self.quote_type in ['fob_freight_lod', 'freight_dap', 'fob_freight']:
            service_lines_data = []
            if self.is_fob:
                service_lines_data.append({
                    'key': 'fob',
                    'price': getattr(self, 'fob_total_cost_est', 0.0),
                })
            if self.is_freight:
                service_lines_data.append({
                    'key': 'freight',
                    'price': getattr(self, 'total_cost_est', 0.0),
                })
            if self.is_lod:
                service_lines_data.append({
                    'key': 'lod',
                    'price': getattr(self, 'lod_total_cost_est', 0.0),
                })

            # Calculate total estimated cost for proportional distribution
            total_estimated_cost = sum(line_data['price'] for line_data in service_lines_data)

            # Calculate prices for all lines first to ensure exact total
            calculated_prices = []
            if self.full_service_cost and self.full_service_cost > 0 and total_estimated_cost > 0:
                # Use proportional distribution based on estimated costs
                # Calculate all prices first without rounding
                unrounded_prices = []
                for line_data in service_lines_data:
                    ratio = line_data['price'] / total_estimated_cost
                    price_unit = (self.full_service_cost * ratio) / self.no_of_containers
                    unrounded_prices.append(price_unit)
                
                # Round all prices and adjust the last one to ensure exact total
                total_rounded = 0.0
                for i, price in enumerate(unrounded_prices):
                    if i == len(unrounded_prices) - 1:
                        # Last line gets the exact remainder to ensure perfect total
                        price_unit = round(self.full_service_cost / self.no_of_containers - total_rounded, 2)
                    else:
                        price_unit = round(price, 2)
                        total_rounded += price_unit  # Add price per container, not total
                    calculated_prices.append(price_unit)
            else:
                # Use estimated costs if no custom price is set
                for line_data in service_lines_data:
                    price_unit = line_data['price'] / self.no_of_containers or 0.0
                    calculated_prices.append(round(price_unit, 2))

            for i, line_data in enumerate(service_lines_data):
                # Final display name (below the bold name)
                line_name = f"Freight Forwarding Service\n{SERVICE_DESCRIPTIONS[line_data['key']]}"

                vals = {
                    'product_id': freight_product.id,
                    'product_uom_qty': self.no_of_containers,
                    'product_uom_id': freight_product.uom_id.id,
                    'price_unit': calculated_prices[i],
                    'name': line_name,
                }
                new_lines |= SaleOrderLine.new(vals)
        elif self.quote_line_mode == 'single':
            # Single line quote
            line_name = f"Freight Forwarding Service\n{config['description']}"

            vals = {
                'product_id': freight_product.id,
                'product_uom_qty': self.no_of_containers,
                'product_uom_id': freight_product.uom_id.id,
                'price_unit': self.full_service_cost/self.no_of_containers or 0.0,
                'name': line_name,
            }
            new_lines |= SaleOrderLine.new(vals)
        elif self.quote_line_mode == 'dap+freight_fob':
            # Two lines: FOB+FREIGHT combined, and DAP

            # First line: FOB + Freight combined
            fob_freight_cost = (getattr(self, 'fob_total_cost_est', 0.0) +
                               getattr(self, 'total_cost_est', 0.0))
            lod_cost = getattr(self, 'lod_total_cost_est', 0.0)
            total_estimated_cost = fob_freight_cost + lod_cost

            # First line: Use service description for 'fob_freight'
            fob_freight_line_name = f"Freight Forwarding Service\n{SERVICE_DESCRIPTIONS['fob_freight']}"

            # Calculate prices based on whether user has set a custom price
            if self.full_service_cost and self.full_service_cost > 0:
                # Use proportional distribution based on estimated costs
                if total_estimated_cost > 0:
                    fob_freight_ratio = fob_freight_cost / total_estimated_cost
                    lod_ratio = lod_cost / total_estimated_cost
                    
                    fob_freight_price = (self.full_service_cost * fob_freight_ratio) / self.no_of_containers
                    lod_price = (self.full_service_cost * lod_ratio) / self.no_of_containers
                    
                    # Round first price and calculate exact remainder for second price
                    fob_freight_price = round(fob_freight_price, 2)
                    lod_price = round(self.full_service_cost / self.no_of_containers - fob_freight_price, 2)
                else:
                    # If no estimated costs, split evenly
                    fob_freight_price = round((self.full_service_cost * 0.5) / self.no_of_containers, 2)
                    lod_price = round(self.full_service_cost / self.no_of_containers - fob_freight_price, 2)
            else:
                # Use estimated costs if no custom price is set
                fob_freight_price = round(fob_freight_cost / self.no_of_containers or 0.0, 2)
                lod_price = round(lod_cost / self.no_of_containers or 0.0, 2)

            fob_freight_vals = {
                'product_id': freight_product.id,
                'product_uom_qty': self.no_of_containers,
                'product_uom_id': freight_product.uom_id.id,
                'price_unit': fob_freight_price,
                'name': fob_freight_line_name,
            }
            new_lines |= SaleOrderLine.new(fob_freight_vals)

            # Second line: DAP only
            # Second line: Use service description for 'lod'
            lod_line_name = f"Freight Forwarding Service\n{SERVICE_DESCRIPTIONS['lod']}"

            lod_vals = {
                'product_id': freight_product.id,
                'product_uom_qty': self.no_of_containers,
                'product_uom_id': freight_product.uom_id.id,
                'price_unit': lod_price,
                'name': lod_line_name,
            }
            new_lines |= SaleOrderLine.new(lod_vals)

        self.order_line |= new_lines