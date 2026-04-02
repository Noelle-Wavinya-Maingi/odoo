"""
Utility module for filtering rates to return only one rate per company.

This module provides a reusable method that implements the following logic:
1. If multiple rates exist for the same company, return only the most recently updated rate (write_date)
2. If all rates for a company are expired, return the most recently updated expired rate
3. If a company has both expired and valid rates, return only the most recent valid rate
"""

from odoo import fields
from datetime import date, datetime


def filter_one_rate_per_company(rates, company_field='supplier_id', valid_until_field='valid_until', write_date_field='write_date'):
    """
    Filter rates to return only one rate per company based on the specified logic.
    
    Args:
        rates: Recordset of rates to filter (e.g., transport.rates or known.price records)
        company_field: Name of the field that identifies the company (default: 'supplier_id' for transport rates, use 'carrier_id' for known prices)
        valid_until_field: Name of the field containing the validity date (default: 'valid_until')
        write_date_field: Name of the field containing the write date (default: 'write_date')
    
    Returns:
        Recordset containing only one rate per company, filtered according to the logic
    """
    if not rates:
        return rates
    
    today = date.today()
    company_groups = {}
    
    # Group rates by company
    for rate in rates:
        company_id = getattr(rate, company_field, False)
        if not company_id:
            continue
        
        company_id = company_id.id if hasattr(company_id, 'id') else company_id
        
        if company_id not in company_groups:
            company_groups[company_id] = []
        company_groups[company_id].append(rate)
    
    # Filter each company's rates
    filtered_rate_ids = []
    
    for company_id, company_rates in company_groups.items():
        if len(company_rates) == 1:
            # Only one rate for this company, include it
            filtered_rate_ids.append(company_rates[0].id)
        else:
            # Multiple rates for this company, apply filtering logic
            valid_rates = []
            expired_rates = []
            
            # Separate valid and expired rates
            for rate in company_rates:
                valid_until = getattr(rate, valid_until_field, False)
                if valid_until:
                    # Handle both date and string formats
                    if isinstance(valid_until, str):
                        valid_until = fields.Date.from_string(valid_until)
                    elif isinstance(valid_until, datetime):
                        valid_until = valid_until.date()
                    elif not isinstance(valid_until, date):
                        valid_until = fields.Date.from_string(str(valid_until))
                    
                    if valid_until >= today:
                        valid_rates.append(rate)
                    else:
                        expired_rates.append(rate)
                else:
                    # If no valid_until date, treat as valid
                    valid_rates.append(rate)
            
            # Helper function to get write_date for comparison
            def get_write_date(rate):
                write_date = getattr(rate, write_date_field, False)
                if not write_date:
                    return datetime(1970, 1, 1, 0, 0, 0)
                if isinstance(write_date, str):
                    return fields.Datetime.from_string(write_date)
                return write_date
            
            # Apply selection logic
            if valid_rates:
                # If there are valid rates, select the most recent valid rate
                selected_rate = max(valid_rates, key=get_write_date)
            elif expired_rates:
                # If all rates are expired, select the most recent expired rate
                selected_rate = max(expired_rates, key=get_write_date)
            else:
                # Fallback: select the most recent rate overall
                selected_rate = max(company_rates, key=get_write_date)
            
            filtered_rate_ids.append(selected_rate.id)
    
    # Final deduplication check - ensure no duplicate rate_ids
    unique_filtered_rate_ids = []
    seen_ids = set()
    for rate_id in filtered_rate_ids:
        if rate_id not in seen_ids:
            seen_ids.add(rate_id)
            unique_filtered_rate_ids.append(rate_id)
    
    # Return filtered recordset
    return rates.browse(unique_filtered_rate_ids)

