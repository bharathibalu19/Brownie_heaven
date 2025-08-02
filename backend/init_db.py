# import sqlite3

# conn = sqlite3.connect('users.db')  # Connects to users.db
# cursor = conn.cursor()

# cursor.execute('''
# CREATE TABLE IF NOT EXISTS user (
#     id INTEGER PRIMARY KEY AUTOINCREMENT,
#     name TEXT,
#     email TEXT UNIQUE NOT NULL,
#     password TEXT NOT NULL,
#     role TEXT CHECK(role IN ('admin', 'customer')) NOT NULL
# );
# ''')

# conn.commit()
# conn.close()

# print("✅ 'user' table created successfully.")
import sqlite3

conn = sqlite3.connect('users.db')
cursor = conn.cursor()

# Drop the old products table if it exists
cursor.execute("DROP TABLE IF EXISTS products")

# Create a new products table with required columns
cursor.execute("""
    CREATE TABLE product (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        name TEXT NOT NULL,
        description TEXT,
        price REAL NOT NULL,
        stock_quantity INTEGER NOT NULL,
        image_url TEXT,
        category TEXT
    )
""")

conn.commit()
conn.close()

print("✅ Table 'products' recreated successfully.")
