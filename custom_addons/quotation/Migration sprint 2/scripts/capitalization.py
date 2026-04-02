import pandas as pd

# Read the original CSV
df = pd.read_csv('/Users/noellemaingi/Downloads/ports.csv')

# Capitalize the 'port_city' column only
df['name'] = df['name'].str.capitalize()

# Save the updated data to a new CSV
df.to_csv('/Users/noellemaingi/Downloads/ports_updated.csv', index=False)

print("✅ 'name' column capitalized. Data saved to 'ports_updated.csv'.")
