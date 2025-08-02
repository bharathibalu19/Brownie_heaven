import os
import random
import sqlite3
import string
from datetime import timedelta

from flask import Flask, render_template, request, redirect, url_for, flash, jsonify, session, make_response
from flask_sqlalchemy import SQLAlchemy
from flask_cors import CORS
from flask_bcrypt import Bcrypt
from flask_jwt_extended import (
    JWTManager, create_access_token, jwt_required,
    verify_jwt_in_request, get_jwt, unset_jwt_cookies
)
from flask_migrate import Migrate
from sqlalchemy import text, asc, desc

from extensions import db  # ✅ SQLAlchemy instance
from models import Product, Customer, Order, User, OrderItem  # ✅ All models from models.py

print("Connected DB path:", os.path.abspath("users.db"))


bcrypt = Bcrypt()
jwt = JWTManager()
migrate = Migrate()
cors = CORS()

app = Flask(__name__,
            template_folder=os.path.join(os.path.dirname(__file__), '../templates'),
            static_folder=os.path.join(os.path.dirname(__file__), '../static'))

basedir = os.path.abspath(os.path.dirname(__file__))

# Configuration
app.config['SECRET_KEY'] = 'super-secret'
app.config['JWT_SECRET_KEY'] = 'super-secret'
app.config['SQLALCHEMY_DATABASE_URI'] = 'sqlite:///' + os.path.join(basedir, 'users.db')
app.config['JWT_TOKEN_LOCATION'] = ['cookies']
app.config['JWT_ACCESS_COOKIE_NAME'] = 'access_token_cookie'
app.config['JWT_COOKIE_SECURE'] = False  # Change to True in prod
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False
app.config['JWT_ACCESS_TOKEN_EXPIRES'] = timedelta(hours=1)

# Initialize extensions with app
db.init_app(app)
bcrypt.init_app(app)
jwt.init_app(app)
migrate.init_app(app, db)
cors.init_app(app)

if not os.path.exists('users.db'):
    with app.app_context():
        db.create_all()

with app.app_context():
    db.create_all()  # Create tables if not exist
    print(Customer.query.all())
    # Check if admin exists
    admin_email = 'admin123@example.com'
    admin_password = 'admin123'
    existing_admin = User.query.filter_by(email=admin_email, role='admin').first()
    if not existing_admin:
        hashed_pw = bcrypt.generate_password_hash(admin_password).decode('utf-8')
        admin = User(name='Admin', email=admin_email, password=hashed_pw, role='admin')
        db.session.add(admin)
        db.session.commit()

@app.route('/')
def index():
    user_name = None
    try:
        verify_jwt_in_request(optional=True)
        claims = get_jwt()
        user_name = claims.get('name')
    except Exception as e:
        featured_products = Product.query.limit(4).all()
        return render_template('index.html', products=featured_products)

    # ✅ Now also return the same for authenticated users
    featured_products = Product.query.limit(4).all()
    return render_template('index.html', products=featured_products, user_name=user_name)





DATABASE = os.path.join(os.path.dirname(__file__), 'users.db')

def get_db():
    conn = sqlite3.connect(DATABASE)
    conn.row_factory = sqlite3.Row
    return conn



@app.route('/login', methods=['GET', 'POST'])
def login():
    if request.method == 'GET':
        return render_template('login.html')

    email = request.form.get('email')
    password = request.form.get('password')
    role = request.form.get('role')

    if not email or not password or not role:
        return render_template('login.html', error="All fields are required.")

    if role == 'admin':
        user = User.query.filter_by(email=email, role='admin').first()
        if user and bcrypt.check_password_hash(user.password, password):
            token = create_access_token(
                identity=user.email,  # must be a string
                additional_claims={
                    'role': user.role,
                    'name': user.name  # Send only first name here
                }
            )
            resp = make_response(redirect(url_for('admin_dashboard')))
            resp.set_cookie('access_token_cookie', token, httponly=True)
            return resp
        return render_template('login.html', error="Invalid admin credentials")

    user = User.query.filter_by(email=email, role='customer').first()
    if user and bcrypt.check_password_hash(user.password, password):
        token = create_access_token(
            identity=user.email,  # must be a string
            additional_claims={
                'role': user.role,
                'name': user.name  # Send only first name here
            }
        )
        resp = make_response(redirect(url_for('customer_dashboard')))
        resp.set_cookie('access_token_cookie', token, httponly=True)
        return resp

    return render_template('login.html', error="Invalid customer credentials")

# routes/admin.py or your main app file

@app.route('/register', methods=['GET'])
def register_form():
    return render_template('register.html')



@app.route('/register', methods=['POST'])
def register():
    data = request.json
    email = data.get('email')
    name = data.get('name')
    password = data.get('password')
    role = 'customer'  # Default to customer

    if not email or not name or not password:
        return jsonify({'msg': 'All fields are required'}), 400

    hashed_pw = bcrypt.generate_password_hash(password).decode('utf-8')

    try:
        # Add to 'user' table
        user = User(name=name, email=email, password=hashed_pw, role=role)
        db.session.add(user)

        # Also add to 'customer' table
        customer = Customer(name=name, email=email, password=hashed_pw)
        db.session.add(customer)

        db.session.commit()
        return jsonify({'msg': 'Customer registered successfully'}), 201

    except Exception as e:
        db.session.rollback()
        if 'UNIQUE constraint failed' in str(e):
            return jsonify({'msg': 'Email already exists'}), 409
        return jsonify({'msg': 'Registration failed'}), 500


def debug_tables():
    conn = get_db()
    cur = conn.cursor()
    cur.execute("SELECT name FROM sqlite_master WHERE type='table'")
    tables = cur.fetchall()
    print("🛠 Available tables:", [t[0] for t in tables])

# Call this after get_db()
debug_tables()

@app.route('/customer/dashboard')
def customer_dashboard():
    db = get_db()
    
    # You might want to handle session-based login here if needed
    user = db.execute("SELECT * FROM user WHERE email = ?", ("guest@example.com",)).fetchone()
    
    products = Product.query.filter(Product.stock_quantity > 0).all()
    return render_template('customer_dashboard.html', user=user, products=products)

@app.route("/explore")
def explore():

    products = Product.query.filter(Product.stock_quantity > 0).all()

    return render_template("explore.html", products=products)

@app.route('/update_profile', methods=['POST'])
@jwt_required()
def update_profile():
    claims = get_jwt()
    if claims['role'] != 'customer':
        return redirect('/login')

    name = request.form['name']
    db = get_db()
    db.execute("UPDATE user SET name = ? WHERE email = ?", (name, claims['sub']))
    db.commit()
    flash("Profile updated.")
    return redirect(url_for('customer_dashboard'))

@app.route('/change_password', methods=['POST'])
@jwt_required()
def change_password():
    claims = get_jwt()
    if claims['role'] != 'customer':
        return redirect('/login')

    current = request.form['current_password']
    new = request.form['new_password']
    confirm = request.form['confirm_password']

    if new != confirm:
        flash("Passwords do not match.")
        return redirect(url_for('customer_dashboard'))

    db = get_db()
    user = db.execute("SELECT * FROM user WHERE email = ?", (claims['sub'],)).fetchone()

    if not bcrypt.check_password_hash(user['password'], current):
        flash("Current password is incorrect.")
        return redirect(url_for('customer_dashboard'))

    hashed = bcrypt.generate_password_hash(new).decode('utf-8')
    db.execute("UPDATE user SET password = ? WHERE email = ?", (hashed, claims['sub']))
    db.commit()
    flash("Password changed.")
    return redirect(url_for('customer_dashboard'))


@app.route('/create-view_product-table')
def create_view_product_table():
    conn = sqlite3.connect('users.db')
    cursor = conn.cursor()
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS view_product (
            id INTEGER PRIMARY KEY,
            name TEXT NOT NULL,
            description TEXT,
            price INTEGER,
            image TEXT
        )
    ''')
    conn.commit()
    conn.close()
    return "Products table created!"


@app.route('/insert-test-view_product')
def insert_test_view_product():
    # conn = sqlite3.connect('backend/users.db')
    conn = sqlite3.connect('users.db')

    cursor = conn.cursor()
    products = [
        (1, 'Dark Chocolate Brownie', 'Rich and fudgy brownie with dark chocolate.', 350, 'static/Fudgy_Dark_Chocolate.jpg'),
        (2, 'Fudge Brownie', 'Brownie with crunchy walnut pieces.', 400, 'static/featured_brownie.jpg'),
        (3, 'Nutty Delight', 'Fudgy brownie with caramel swirls.', 420, 'static/Almond_Flour_Chocolate_Brownies.jpg'),
        (4, 'Boozy Brownie Box', 'Brownie with a hint of rum.', 350, 'static/boozy_brownie.webp'),
        (5, 'Roasted Nuts Brownie', 'Brownie with roasted nuts.', 400, 'static/RoastedNutsBrownie.webp'),
        (6, 'Red Velvet Brownie', 'Brownie with red velvet.', 420, 'static/RedVelvetBrownie.webp'),
        (7, 'Choco Hazelnut Spread Brownie', 'Brownie with choco hazelnut spread.', 350, 'static/choco.jpg'),
        (8,'Eggless Choco Hazelnut Spread Brownie', 'Eggless brownie with choco hazelnut spread.', 400, 'static/EgglessChoco.webp'),
        (9,'Brownie Slab', 'Rich and fudgy brownie with dark chocolate.', 700, 'static/BrownieSlab.webp'),
        (10,'Choco Hazelnut Crunch', 'Rich and fudgy brownie with dark chocolate.', 1150, 'static/crunchhazelnut_600x.jpg'),
        (11,'Heart Unlock Brownie Cake', 'Rich and fudgy brownie with dark chocolate.',400, 'static/heartunlock_600x.jpg'),
        (12,'Nutty Professor Brownie', 'Rich and fudgy brownie with dark chocolate.', 420, 'static/nutty_600x.jpg'),
        (13,'Oreo Brownie', 'Rich and fudgy brownie with dark chocolate.', 350, 'static/OreoBrownie_600x.webp'),
        (14,'Salted Caramel Fudge Brownie', 'Rich and fudgy brownie with dark chocolate.', 400, 'static/SaltedCaramelBrownie_600x.webp'),
        (15,'Triple Chocolate Brownie', 'Rich and fudgy brownie with dark chocolate.', 420, 'static/TripleChocolateBrownie_600x.webp'),
    ]
    for p in products:
        try:
            cursor.execute("INSERT INTO view_product (id, name, description, price, image) VALUES (?, ?, ?, ?, ?)", p)
        except sqlite3.IntegrityError:
            continue  # skip if already inserted
    conn.commit()
    conn.close()
    return "Test products inserted!"

@app.route('/admin/products/test-insert')
def insert_test_products():
    conn = sqlite3.connect('users.db')
    cursor = conn.cursor()

    product = [
        (1, 'Dark Chocolate Brownie', 'Rich and fudgy brownie with dark chocolate.', 350, 'static/Fudgy_Dark_Chocolate.jpg','Brownies'),
        (2, 'Fudge Brownie', 'Brownie with crunchy walnut pieces.', 400, 'static/featured_brownie.jpg','Brownies'),
        (3, 'Nutty Delight', 'Fudgy brownie with caramel swirls.', 420, 'static/Almond_Flour_Chocolate_Brownies.jpg','Cakes'),
        (4, 'Boozy Brownie Box', 'Brownie with a hint of rum.', 350, 'static/boozy_brownie.webp','Cakes'),
        (5, 'Roasted Nuts Brownie', 'Brownie with roasted nuts.', 400, 'static/RoastedNutsBrownie.webp','Cakes'),
        (6, 'Red Velvet Brownie', 'Brownie with red velvet.', 420, 'static/RedVelvetBrownie.webp','Brownies'),
        (7, 'Choco Hazelnut Spread Brownie', 'Brownie with choco hazelnut spread.', 350, 'static/choco.jpg','Cakes'),
        (8,'Eggless Choco Hazelnut Spread Brownie', 'Eggless brownie with choco hazelnut spread.', 400, 'static/EgglessChoco.webp','Brownies'),
        (9,'Brownie Slab', 'Rich and fudgy brownie with dark chocolate.', 700, 'static/BrownieSlab.webp','Cakes'),
        (10,'Choco Hazelnut Crunch', 'Rich and fudgy brownie with dark chocolate.', 1150, 'static/crunchhazelnut_600x.jpg','Cakes'),
        (11,'Heart Unlock Brownie Cake', 'Rich and fudgy brownie with dark chocolate.',400, 'static/heartunlock_600x.jpg','Cakes'),
        (12,'Nutty Professor Brownie', 'Rich and fudgy brownie with dark chocolate.', 420, 'static/nutty_600x.jpg','Brownies'),
        (13,'Oreo Brownie', 'Rich and fudgy brownie with dark chocolate.', 350, 'static/OreoBrownie_600x.webp','Brownies'),
        (14,'Salted Caramel Fudge Brownie', 'Rich and fudgy brownie with dark chocolate.', 400, 'static/SaltedCaramelBrownie_600x.webp','Brownies'),
        (15,'Triple Chocolate Brownie', 'Rich and fudgy brownie with dark chocolate.', 420, 'static/TripleChocolateBrownie_600x.webp','Brownies'),
    ]

    for p in product:
        try:
            cursor.execute("""
                INSERT INTO product (id, name, description, price, stock_quantity, image_url, category)
                VALUES (?, ?, ?, ?, ?, ?, ?)
            """, p)
        except sqlite3.IntegrityError:
            continue  # skip duplicates

    conn.commit()
    conn.close()
    return "Test products inserted!"


@app.route('/create-product-table')
def create_products_table():
    conn = sqlite3.connect('users.db')
    cursor = conn.cursor()
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS product (
            id INTEGER PRIMARY KEY,
            name TEXT NOT NULL,
            description TEXT,
            price INTEGER,
            image TEXT
        )
    ''')
    conn.commit()
    conn.close()
    return "Products table created!"
create_products_table()




@app.route('/product/<int:product_id>')

def product_detail(product_id):
    conn = sqlite3.connect('users.db')
    cursor = conn.cursor()
    cursor.execute("SELECT id, name, description, price, image FROM view_product WHERE id=?", (product_id,))
    row = cursor.fetchone()
    conn.close()

    if row:
        product = {
            'id': row[0],
            'name': row[1],
            'description': row[2],
            'price': row[3],
            'image_url': row[4]
        }
        return render_template('product_details.html', product=product)
    else:
        return "Product not found", 404



@app.route('/debug-product')
def debug_products():
    conn = sqlite3.connect('users.db')
    cursor = conn.cursor()
    cursor.execute("SELECT * FROM product")
    rows = cursor.fetchall()
    conn.close()
    return {"product": rows}


# Add Product Route
@app.route('/admin/product/add', methods=['POST'])
def add_product():
    data = request.form
    name = data.get("name")
    description = data.get("description")
    price = data.get("price")
    stock_quantity = data.get("stock_quantity")
    image_url = data.get("image_url")
    category = data.get("category")

    conn = sqlite3.connect('users.db')
    cursor = conn.cursor()
    cursor.execute('''
        INSERT INTO product (name, description, price, stock_quantity, image_url, category)
        VALUES (?, ?, ?, ?, ?, ?)
    ''', (name, description, price, stock_quantity, image_url, category))
    conn.commit()
    conn.close()

    flash('Product added successfully!', 'success')
    return redirect(url_for('admin_dashboard'))
@app.route('/admin/dashboard')
def admin_dashboard():
    page = request.args.get('page', 1, type=int)
    search = request.args.get('search', '')
    sort_by = request.args.get('sort', 'name')
    direction = request.args.get('direction', 'asc')

    query = Product.query
    if search:
        query = query.filter(Product.name.ilike(f"%{search}%"))

    column = getattr(Product, sort_by, Product.name)
    query = query.order_by(column.desc() if direction == 'desc' else column.asc())

    pagination = query.paginate(page=page, per_page=10, error_out=False)

    def serialize_product(product):
        return {
            "id": product.id,
            "name": product.name,
            "description": product.description,
            "price": product.price,
            "stock": product.stock_quantity,
            "image_url": product.image_url,
            "category": product.category
        }

    products = [serialize_product(p) for p in pagination.items]
    total_products = Product.query.count()
    total_customers = Customer.query.count()

    customers = Customer.query.all()  # or however you're loading customers

    return render_template(
        'admin_dashboard.html',
        products=products,
        pagination=pagination,
        search=search,
        customers=customers,
        total_products=total_products,
        total_customers=total_customers

    )


@app.route('/admin/products/data')
def get_products_data():
    page = request.args.get('page', 1, type=int)
    search = request.args.get('search', '')
    sort_by = request.args.get('sort', 'name')
    direction = request.args.get('direction', 'asc')

    query = Product.query

    if search:
        query = query.filter(Product.name.ilike(f"%{search}%"))

    if direction == 'asc':
        query = query.order_by(asc(getattr(Product, sort_by)))
    else:
        query = query.order_by(desc(getattr(Product, sort_by)))

    pagination = query.paginate(page=page, per_page=20)
    
    return jsonify({
        'products': [{
            'id': p.id,
            'name': p.name,
            'price': p.price,
            'stock_quantity': p.stock_quantity,
            'description': p.description
        } for p in pagination.items],
        'total_pages': pagination.pages,
        'current_page': pagination.page
    })

# Product List with Pagination, Search, and Sort
@app.route('/admin/product')
def admin_products():
    page = request.args.get('page', 1, type=int)
    search = request.args.get('search', '')
    sort_by = request.args.get('sort', 'name')
    direction = request.args.get('direction', 'asc')

    customers = db.execute("SELECT * FROM user WHERE role = 'customer'").fetchall()

    query = Product.query

    if search:
        query = query.filter(Product.name.ilike(f"%{search}%"))

    if direction == 'asc':
        query = query.order_by(asc(getattr(Product, sort_by)))
    else:
        query = query.order_by(desc(getattr(Product, sort_by)))

    pagination = query.paginate(page=page, per_page=20)
    return render_template('admin_dashboard.html',customers=customers, products=pagination.items, pagination=pagination, search=search, sort_by=sort_by, direction=direction)


@app.route('/admin/products/edit/<int:product_id>', methods=['POST'])
def edit_product(product_id):
    try:
        product = Product.query.get_or_404(product_id)
        product.name = request.form['name']
        product.description = request.form['description']
        product.price = float(request.form['price'])
        product.stock_quantity = int(request.form['stock_quantity'])
        product.category = request.form.get('category', '')
        product.image_url = request.form.get('image_url', '')

        db.session.commit()
        return redirect('/admin')
    except Exception as e:
        db.session.rollback()
        return f"An error occurred: {str(e)}", 500



# Delete Product
@app.route('/admin/products/delete/<int:product_id>', methods=['POST'])
def delete_product(product_id):
    product = Product.query.get_or_404(product_id)
    db.session.delete(product)
    db.session.commit()
    flash("Product deleted!", "info")
    return redirect(url_for('admin_products'))



@app.route('/admin/customers')
def admin_customers():
    search = request.args.get('search', '')
    status_filter = request.args.get('status', 'all')

    query = Customer.query

    if search:
        query = query.filter(
            (Customer.name.ilike(f'%{search}%')) |
            (Customer.email.ilike(f'%{search}%'))
        )

    if status_filter != 'all':
        active_status = True if status_filter == 'active' else False
        query = query.filter(Customer.active == active_status)

    customers = query.all()
    return render_template('customers.html', customers=customers)

@app.route('/admin/customer/<int:customer_id>')
def view_customer(customer_id):
    customer = Customer.query.get_or_404(customer_id)
    orders = Order.query.filter_by(customer_id=customer.id).all()
    return render_template('customer_profile.html', customer=customer, orders=orders)

@app.route('/admin/customer/toggle/<int:customer_id>')
def toggle_customer_status(customer_id):
    customer = Customer.query.get_or_404(customer_id)
    customer.active = not customer.active
    db.session.commit()
    return redirect(url_for('admin_customers'))

@app.route('/admin/customer/delete/<int:customer_id>', methods=['POST'])
def delete_customer(customer_id):
    customer = Customer.query.get_or_404(customer_id)
    db.session.delete(customer)
    db.session.commit()
    flash('Customer deleted successfully.')
    return redirect(url_for('admin_customers'))

@app.route('/admin/customer/reset_password/<int:customer_id>', methods=['POST'])
def reset_password(customer_id):
    customer = Customer.query.get_or_404(customer_id)
    temp_password = ''.join(random.choices(string.ascii_letters + string.digits, k=8))
    hashed = bcrypt.generate_password_hash(temp_password).decode('utf-8')
    customer.password = hashed
    db.session.commit()
    flash(f"Temporary password: {temp_password}")
    return redirect(url_for('view_customer', customer_id=customer_id))

@app.route('/admin/customer/impersonate/<int:customer_id>')
def impersonate_customer(customer_id):
    customer = Customer.query.get_or_404(customer_id)
    session['impersonated_customer_id'] = customer.id
    session['original_admin'] = True
    return redirect('/customer/dashboard')  # Assume you have customer dashboard

@app.route('/admin/stop_impersonation')
def stop_impersonation():
    session.pop('impersonated_customer_id', None)
    session.pop('original_admin', None)
    return redirect('/admin/dashboard')


@app.route('/admin/orders')
def admin_orders():
    orders = Order.query.all()  # Assuming you have an Order model
    return render_template('orders.html')

@app.route('/logout')
def logout():
    response = make_response(redirect(url_for('index')))  # Redirect to homepage or wherever you want
    unset_jwt_cookies(response)  # Clear the JWT cookies
    return response


@app.route('/admin/settings', methods=['GET', 'POST'])
def admin_settings():
    if request.method == 'POST':
        html_content = request.form.get('editor_html')
        print("Received HTML content from Quill Editor:\n", html_content)
        # TODO: Save to DB if needed
        return redirect(url_for('admin_settings'))

    return render_template('settings.html')

@app.route('/place-order', methods=['POST'])
def place_order():
    email = request.form['email']
    name = request.form['name']

    cart = session.get('cart', {})  # {'1': 2, '3': 1}
    total = 0
    order_items = []

    for product_id, quantity in cart.items():
        product = Product.query.get(int(product_id))
        subtotal = product.price * quantity
        total += subtotal
        order_items.append((product.id, quantity, subtotal))

    # Check if customer exists
    customer = Customer.query.filter_by(email=email).first()
    if not customer:
        # Provide a default password
        customer = Customer(email=email, name=name, password='guest', active=True)
        db.session.add(customer)
        db.session.commit()

    # Create order with customer_id
    order = Order(customer_id=customer.id, status="Pending")
    db.session.add(order)
    db.session.commit()

    # Add order items
    for pid, qty, sub in order_items:
        item = OrderItem(order_id=order.id, product_id=pid, quantity=qty, subtotal=sub)
        db.session.add(item)

        product = Product.query.get(pid)
        product.stock_quantity -= qty

    db.session.commit()

    flash("Order placed successfully!", "success")
    return redirect(url_for('payment'))



@app.route('/add-to-cart/<int:product_id>')
def add_to_cart(product_id):
    cart = session.get('cart', {})

    if str(product_id) in cart:
        cart[str(product_id)] += 1
    else:
        cart[str(product_id)] = 1

    session['cart'] = cart
    return redirect(url_for('checkout'))

@app.route('/checkout')
def checkout():
    cart = session.get('cart', {})
    items = []
    total = 0

    for pid_str, qty in cart.items():
        product = Product.query.get(int(pid_str))
        subtotal = product.price * qty
        items.append({'product': product, 'quantity': qty, 'subtotal': subtotal})
        total += subtotal

    discount = 0
    tax = round(0.05 * total, 2)
    grand_total = total - discount + tax

    return render_template('card.html', items=items, total=total, discount=discount, tax=tax, grand_total=grand_total)

@app.route('/payment')
def payment():
    return render_template('payment.html')


if __name__ == '__main__':
    
    app.run(debug=True)
