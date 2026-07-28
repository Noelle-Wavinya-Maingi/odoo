# -*- coding: utf-8 -*-
from odoo import models, fields, api
import logging

_logger = logging.getLogger(__name__)


class CurrencyConversionMixin(models.AbstractModel):
    """Mixin for currency conversion utilities.
    
    Provides methods to convert amounts to a target currency (typically the model's currency_id).
    Models using this mixin should have:
    - currency_id: Many2one field to res.currency (target currency)
    - company_id: Many2one field to res.company (for conversion context)
    """
    _name = 'currency.conversion.mixin'
    _description = 'Currency Conversion Mixin'

    def _convert_to_target_currency(self, amount, from_currency, date=None):
        """Convert an amount from source currency to target currency (currency_id).
        
        Args:
            amount (float): Amount to convert
            from_currency (res.currency): Source currency
            date (date): Conversion date (defaults to today)
            
        Returns:
            float: Converted amount in target currency
        """
        if not amount or amount == 0.0:
            return 0.0
        
        if not from_currency or not self.currency_id:
            return amount
        
        if from_currency == self.currency_id:
            return amount
        
        if date is None:
            date = fields.Date.today()
        
        try:
            return from_currency._convert(
                amount,
                self.currency_id,
                self.company_id,
                date
            )
        except Exception as e:
            _logger.warning(
                "Currency conversion failed for %s %s: %s. Using original amount.",
                self._name, self.id, str(e)
            )
            return amount
    
    def _convert_budget_lines(self, budget_lines, amount_field='budgeted_amount', date_field='date_planned'):
        """Convert amounts from multiple budget lines to target currency.
        
        Args:
            budget_lines: Recordset of budget lines
            amount_field (str): Field name containing the amount to convert
            date_field (str): Field name containing the date for conversion
            
        Returns:
            float: Sum of converted amounts
        """
        total = 0.0
        for line in budget_lines:
            amount = getattr(line, amount_field, 0.0) or 0.0
            line_date = getattr(line, date_field, None) or fields.Date.today()
            converted = self._convert_to_target_currency(
                amount,
                line.currency_id,
                line_date
            )
            total += converted
        return total

