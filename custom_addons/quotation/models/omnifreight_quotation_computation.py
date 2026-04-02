import re
from .route_price_logic import RoutePriceLogic
from odoo import api, models
import logging
_logger = logging.getLogger(__name__)

class OmnifreightQuotationComputation(models.AbstractModel):
    _name = 'omnifreight.quotation.computation'
    _description = 'Omnifreight Quotations'
    
    @api.depends('service_country_id', 'service_country_id.subregion_id', 'city_id', 'city_id.country_id', 'city_id.country_id.subregion_id')
    def _compute_pickup_region(self):
        """
        Compute the pickup region for the sale order based on the related city or country.
        - If a city is provided and that city's country has a subregion, use that subregion name.
        - Otherwise, if only a service country is provided and it has a subregion, use that.
        - If neither is available, set the pickup region to False.
        """
        for record in self:
            if record.city_id and record.city_id.country_id and record.city_id.country_id.subregion_id:
                record.pickup_region = record.city_id.country_id.subregion_id.name
            elif record.service_country_id and record.service_country_id.subregion_id:
                record.pickup_region = record.service_country_id.subregion_id.name
            else:
                record.pickup_region = False
            
    @api.depends('fob_special_costs_id', 'fob_special_costs_id.price', 'fob_special_costs_id.currency_id', 'currency_id')
    def _compute_fob_misc_costs(self):
        """
        Compute the miscellaneous FOB cost by summing up the price of all special costs
        linked to the sale order, converting each to quotation currency.
        """
        for record in self:
            total_fob_misc_cost = 0.0
            for cost in record.fob_special_costs_id:
                cost_amount = float(cost.price or 0.0)
                if cost_amount > 0:
                    # Convert each special cost from its currency to quotation currency
                    if cost.currency_id and cost.currency_id != record.currency_id:
                        converted_amount = record.convert_rate_amount(
                            cost_amount, 
                            cost.currency_id
                        )
                    else:
                        converted_amount = cost_amount
                    total_fob_misc_cost += converted_amount
            record.fob_misc_cost = total_fob_misc_cost
    
    @api.depends('package_details_id')
    def _compute_package_details(self):
        """Automatically compute the values from the linked package details when the quotation is loaded"""
        for order in self:
            if order.package_details_id:
                order.container_type = order.package_details_id.container_type
                order.contents = order.package_details_id.contents
                order.content_classification = order.package_details_id.content_classification

   # In the OmnifreightQuotation class (sale.order model)

    @api.depends('rate_link_ids', 'rate_link_ids.fob_total', 'rate_link_ids.currency_id', 'currency_id')
    def _compute_fob_selected_haulier(self):
        """Update haulier cost based on the selected transport rate's total.
        Stores original value for display. Conversion happens in totals computation.
        """
        for rec in self:
            selected = rec.rate_link_ids.filtered(lambda link: link.is_selected_fob)

            if len(selected) == 1:
                # Store original value for display (conversion happens in totals)
                rec.fob_selected_haulage = selected.fob_total or 0.0
                rec.fob_selected_haulage_currency = selected.currency_id or rec.currency_id
            elif len(selected) > 1:
                _logger.warning(f"Multiple selected hauliers: {[l.id for l in selected]}")
                # Store original value for display (conversion happens in totals)
                rec.fob_selected_haulage = selected[0].fob_total or 0.0
                rec.fob_selected_haulage_currency = selected[0].currency_id or rec.currency_id
            else:
                rec.fob_selected_haulage = 0.0
                rec.fob_selected_haulage_currency = rec.currency_id
    
            
    @api.depends('transport_rates', 'distance', 'is_fob')
    def _compute_transport_rate_total(self):
        """
        Compute the total transport rate cost for FOB.
        Iterates over all transport rates and calculates each rate's cost based on
        the sale order's distance using RoutePriceLogic, then sums up these computed values.
        """
        for order in self:
            total = 0.0
            if order.distance and order.is_fob:
                # Filter rates for FOB only
                for rate in order.transport_rates:
                    # Compute the rate using the provided function and the sale order's distance
                    computed_rate = RoutePriceLogic.compute_route_rate_for_distance(rate, order.distance)
                    total += computed_rate
            order.transport_rate_total = total
            
    @api.depends('client_class')
    def _compute_fob_risk_percentage(self):
        """
        Compute the risk percentage for FOB based on the client class.
        Different client classes (easy, neutral, challenging) have different risk percentages.
        Defaults to 0.1 if none of the conditions match.
        """
        for record in self:
            if record.client_class == 'easy':
                record.fob_risk_percentage = 0.05
            elif record.client_class == 'neutral':
                record.fob_risk_percentage = 0.1
            elif record.client_class == 'challenging':
                record.fob_risk_percentage = 0.15
            else:
                record.fob_risk_percentage = 0.1

    @api.depends('port_of_loading', 'port_of_dispatch')
    def _compute_route(self):
        """
        Compute the route for the sale order based on the selected ports:
        - Searches for a route record that matches the departure port (POL) and the arrival port (POD).
        - If found, sets the route_id on the sale order.
        - If either port is missing or no matching route is found, route_id is set to False.
        """
        for order in self:
            if order.port_of_loading and order.port_of_dispatch:
                route = self.env['omnifreight.route'].search([
                    ('departure_port_id', '=', order.port_of_loading.id),
                    ('arrival_port_id', '=', order.port_of_dispatch.id)
                ], limit=1)
                order.route_id = route.id
            else:
                order.route_id = False
                
    @api.onchange('rate_link_ids')
    def _onchange_rate_link_selected(self):
        # whenever any child toggles, ensure only one stays True for both FOB and LOD
        for order in self:

            # Handle FOB selection
            selected_fob_links = order.rate_link_ids.filtered('is_selected_fob')
            if len(selected_fob_links) > 1:
                last_fob = selected_fob_links[-1]
                for link in selected_fob_links:
                    if link != last_fob:
                        link.is_selected_fob = False
            order._compute_fob_selected_haulier()
            
    @api.depends('selected_transport_rate_id', 'transport_rates.selected_for_sale_orders', 'transport_rates.is_selected_fob')
    def _compute_selected_transport_rate(self):
        for order in self:
            selected_rate = self.env['omnifreight.transport.rates'].search([
                ('selected_for_sale_orders', 'in', [order.id])
            ], limit=1)
            order.selected_transport_rate_id = selected_rate.id if selected_rate else False

    @api.depends('transport_rates', 'transport_rates.is_selected_fob', 'transport_rates.currency_id', 'currency_id')
    def _compute_transport_rate_total(self):
        for rec in self:
            selected_rate = rec.transport_rates.filtered(lambda r: r.is_selected_fob)
            if selected_rate:
                # Convert to quotation currency if different
                converted_total = rec.convert_rate_amount(
                    selected_rate[0].fob_total, 
                    selected_rate[0].currency_id
                )
                rec.transport_rate_total = converted_total
            else:
                rec.transport_rate_total = 0.0
                
    @api.depends('fob_misc_cost', 'fob_selected_haulage', 'fob_selected_haulage_currency', 'fob_risk_percentage', 'no_of_containers', 'currency_id')
    def _compute_fob_total_cost_est(self):
        """
        Computes the FOB (Free On Board) total cost estimate and margin:
        1. Gets the selected haulage cost (fob_selected_haulage)
        2. Converts to quotation currency if different
        3. Calculates margin multiplier: (1 + risk_percentage/100)
        4. Calculates base total: misc_costs + selected_haulage * no_of_containers
        5. Final cost = base_total * margin_multiplier
        6. Margin amount = final_cost - base_total
        """
        for record in self:
            # Convert FOB selected haulage from its currency to quotation currency
            if record.fob_selected_haulage and record.fob_selected_haulage > 0:
                converted_fob_total = record.convert_rate_amount(
                    record.fob_selected_haulage, 
                    record.fob_selected_haulage_currency
                )
            else:
                converted_fob_total = 0.0
            
            # Calculate FOB costs sum (misc costs + haulage * containers)
            record.fob_costs_sum = record.fob_misc_cost + converted_fob_total * record.no_of_containers
            
            # Calculate totals with margin
            margin = (1 + (record.fob_risk_percentage / 100))
            converted_totals = record.fob_misc_cost + converted_fob_total * record.no_of_containers
            record.fob_total_cost_est = round(converted_totals * margin, 0)
            record.fob_total_margin = round(record.fob_total_cost_est - converted_totals, 0)
            record.fob_base_cost = round(converted_totals, 0)

    @api.onchange('no_of_containers')
    def _compute_all_costs(self):
        for record in self:
            record._compute_fob_total_cost_est()
            