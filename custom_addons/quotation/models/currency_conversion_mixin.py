from odoo import models, fields, api
from odoo.exceptions import UserError

class OmniCurrencyConversion(models.AbstractModel):
    _name = 'omnifreight.currency.conversion'
    _description = 'Currency Conversion Utility'

  
    def convert_rate_amount(self, rate_amount, rate_currency):
        """
        Convert a rate amount from its currency to the quotation currency.
        
        Args:
            rate_amount (float): The amount to convert
            rate_currency (res.currency): The currency of the rate amount
            
        Returns:
            float: The converted amount in quotation currency
        """
        self.ensure_one()
        
        if not rate_amount or not rate_currency:
            return 0.0
            
        quotation_currency = self.currency_id
        today = fields.Date.context_today(self)

        if quotation_currency != rate_currency:
            try:
                converted_amount = rate_currency._convert(
                    rate_amount, 
                    quotation_currency, 
                    self.company_id, 
                    today, 
                    round=False
                )
                return converted_amount
            except Exception as e:
                raise UserError(f"Currency conversion failed: {str(e)}")
        else:
            return rate_amount



    
    