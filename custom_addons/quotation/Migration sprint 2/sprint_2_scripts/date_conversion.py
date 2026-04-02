import pandas as pd
import ast
import numpy as np

# Read the CSV file
input_file = '/Users/noellemaingi/Downloads/test.csv'
output_file = '/Users/noellemaingi/Desktop/orders.csv'

# Load the CSV into a DataFrame
df = pd.read_csv(input_file)

# Convert 'date_order' to datetime format (handles microseconds) and then extract date
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

container_name_map = {
    '20\' Dry': '20\' DV',
    '40\' HC': '40\' HC',
    '40\' Dry': '40\' DV',
    '20\' FL': '20\' FL',
    '40\' HC RF': '40\' HRF',
    '40\' FL': '40\' FL',
    '20\' OT': '20\' OT',
    '20\' RF': '20\' RF',
    '40\' OT': '40\' OT'
}

# Mapping full Odoo payment term names to simplified names
payment_term_name_map = {
    'Same day': 'Immediate Payment',
    '15 Days': '15 Days',
    '30 Days': '30 Days',
    '45 Days': '45 Days',
    '60 Days': '30% Now, Balance 60 Days',
}

# Function to extract payment term details from a string representation of a dictionary.
def extract_payment_term(val):
    if isinstance(val, str) and val.strip().startswith('{'):
        try:
            parsed = ast.literal_eval(val.strip())
            return parsed.get('en_US', '').strip()
        except Exception:
            return val
    return val.strip() if isinstance(val, str) else val

# Apply payment term mapping
df['payment_term_id'] = df['payment_term_id'].apply(extract_payment_term)
df['payment_term_id'] = df['payment_term_id'].map(payment_term_name_map)

# Replace incoterm codes with full names
df['incoterm_id'] = df['incoterm_id'].map(incoterm_name_map)

# Capitalize ports
df['port_of_loading'] = df['port_of_loading'].str.capitalize()
df['port_of_dispatch'] = df['port_of_dispatch'].str.capitalize()

df['container_type'] = df['container_type'].map(container_name_map)

# 🆕 Set order_status to 'sale' if invoice_number is present
df['state'] = df['state'].apply(lambda x: 'sale' if pd.notna(x) and str(x).strip() != '' else '')

# Initialize the new columns with np.nan to preserve column order; they'll be converted later.
df['is_fob'] = np.nan
df['is_lod'] = np.nan
df['is_freight'] = np.nan

# Define a helper function for determining if a field is empty (either NaN or empty string)
def is_empty(series):
    return series.isnull() | (series.astype(str).str.strip() == '')

# Create boolean series for empty checks
empty_loading = is_empty(df['port_of_loading'])
empty_dispatch = is_empty(df['port_of_dispatch'])

# Condition: Both ports are empty -> set all as 0
both_empty = empty_loading & empty_dispatch
df.loc[both_empty, ['is_fob', 'is_lod', 'is_freight']] = [0, 0, 0]

# Condition: Both ports are NOT empty -> set all as 1
both_not_empty = ~empty_loading & ~empty_dispatch
df.loc[both_not_empty, ['is_fob', 'is_lod', 'is_freight']] = [1, 1, 1]

# Condition: If port_of_loading is empty and port_of_dispatch is NOT empty
condition1 = empty_loading & ~empty_dispatch
df.loc[condition1, 'is_fob'] = 0
df.loc[condition1, 'is_lod'] = 1
df.loc[condition1, 'is_freight'] = 0

# Condition: If port_of_dispatch is empty and port_of_loading is NOT empty
condition2 = empty_dispatch & ~empty_loading
df.loc[condition2, 'is_fob'] = 1
df.loc[condition2, 'is_lod'] = 0
df.loc[condition2, 'is_freight'] = 0

# Convert the new columns to integers (fill any NaNs with 0 first, if any)
df['is_fob'] = df['is_fob'].fillna(0).astype(int)
df['is_lod'] = df['is_lod'].fillna(0).astype(int)
df['is_freight'] = df['is_freight'].fillna(0).astype(int)

# Save the cleaned file
df.to_csv(output_file, index=False)

print(f"✅ CSV is now ready for Odoo import. Output: {output_file}")
