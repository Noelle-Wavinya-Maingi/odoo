import pandas as pd
import ast

# Read the CSV file
input_file = '/Users/noellemaingi/Desktop/order.csv'
output_file = '/Users/noellemaingi/Desktop/orders.csv'

# Load the CSV into a DataFrame
df = pd.read_csv(input_file)

# Convert 'date_order' to datetime format (handles microseconds)
df['date_order'] = pd.to_datetime(df['date_order'], errors='coerce')

df['date_order'] = df['date_order'].dt.date

# Mapping incoterm codes to full names
incoterm_name_map = {
    'EXW': 'EX WORKS',
    'FCA': 'FREE CARRIER',
    'FAS': 'FREE ALONGSIDE SHIP',
    'FOB': 'FREE ON BOARD',
    'CFR': 'COST AND FREIGHT',
    'CIF': 'COST, INSURANCE AND FREIGHT',
    'CPT': 'CARRIAGE PAID TO',
    'CIP': 'CARRIAGE AND INSURANCE PAID TO',
    'DPU': 'DELIVERED AT PLACE UNLOADED',
    'DAP': 'DELIVERED AT PLACE',
    'DDP': 'DELIVERED DUTY PAID',
}

# Mapping full Odoo payment term names to simplified names
payment_term_name_map = {
    'Same day': 'Immediate Payment',
    '15 Days': '15 Days',
    '30 Days': '30 Days',
    '45 Days': '45 Days',
    '60 Days': '30% Now, Balance 60 Days',
}

# Fix for extracting 'en_US' and removing spaces
def extract_payment_term(val):
    if isinstance(val, str) and val.strip().startswith('{'):
        try:
            parsed = ast.literal_eval(val.strip())
            return parsed.get('en_US', '').strip()
        except Exception:
            return val
    return val.strip() if isinstance(val, str) else val

df['payment_term_id'] = df['payment_term_id'].apply(extract_payment_term)
df['payment_term_id'] = df['payment_term_id'].map(payment_term_name_map)

# Replace incoterm codes with full names
df['incoterm_id'] = df['incoterm_id'].map(incoterm_name_map)

df['port_of_loading'] = df['port_of_loading'].str.capitalize()

df['port_of_dispatch'] = df['port_of_dispatch'].str.capitalize()

# Save the cleaned file
df.to_csv(output_file, index=False)

print(f"✅ CSV is now ready for Odoo import. Output: {output_file}")
