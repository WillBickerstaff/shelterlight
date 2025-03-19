"""geocode.create.

Copyright (c) 2025 Will Bickerstaff
Licensed under the MIT License.
See LICENSE file in the root directory of this project.

Description: Convert the data in the GeoNames free Gazetteer Data into
    an sqlite db.
Author: Will Bickerstaff
Version: 0.

Data Used is the GeoNames Gazetteer cities5000.txt data dump
Data set is freely available at https://www.geonames.org/ and licensed under
a Creative Commons Attribution 4.0 License
(https://creativecommons.org/licenses/by/4.0/))
"""

import pandas as pd
import sqlite3

# Load the Tab separated txt file with specified data types
tsv_file_path = 'cities5000.txt'
df = pd.read_csv(
    tsv_file_path,
    sep='\t',
    usecols=[1, 4, 5, 8, 17],
    dtype={8: str, 1: str, 4: float, 5: float, 17: str},
    low_memory=False
)

# Rename columns to SQL-friendly names
df.columns = ['Place_Name', 'Lat', 'Lng', 'ISO_Country', 'Timezone']

# Connect to SQLite database (creates geocode.db if it doesn't exist)
conn = sqlite3.connect('geocode.db')
cursor = conn.cursor()

# Define the SQL CREATE TABLE statement directly with known data types
create_table_query = """
CREATE TABLE IF NOT EXISTS geocode_data (
    Place_Name TEXT,
    Lat REAL,
    Lng REAL,
    ISO_Country TEXT,
    Timezone TEXT,
    UNIQUE (ISO_Country, Place_Name) ON CONFLICT IGNORE
);
"""
cursor.execute(create_table_query)

# Write DataFrame to SQL table, enforcing uniqueness on the specified columns
df.to_sql('geocode_data', conn, if_exists='append', index=False)

# Select and display a random sample of 10 records
query = "SELECT * FROM geocode_data ORDER BY RANDOM() LIMIT 10;"
random_records = pd.read_sql_query(query, conn)
print(random_records)

# Commit and close the database connection
conn.commit()
conn.close()
