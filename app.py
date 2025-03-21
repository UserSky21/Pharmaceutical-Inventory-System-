from flask import Flask, render_template, request, redirect, url_for, flash, jsonify, make_response
from flask_sqlalchemy import SQLAlchemy
from flask_login import LoginManager, UserMixin, login_user, login_required, logout_user, current_user
from datetime import datetime, timedelta
import os
from dotenv import load_dotenv
import requests
import io
import csv
import secrets
import math
import logging
from werkzeug.security import generate_password_hash, check_password_hash

# Configure logging
logging.getLogger('werkzeug').setLevel(logging.ERROR)
logging.getLogger('sqlalchemy.engine').setLevel(logging.ERROR)

# Load environment variables
load_dotenv()

def generate_secret_key():
    return secrets.token_hex(32)

app = Flask(__name__)
app.config['SECRET_KEY'] = os.getenv('FLASK_SECRET_KEY', generate_secret_key())
app.config['SQLALCHEMY_DATABASE_URI'] = 'sqlite:///pharmacy.db'
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False
db = SQLAlchemy(app)
login_manager = LoginManager()
login_manager.init_app(app)
login_manager.login_view = 'login'

# Database Models
class User(UserMixin, db.Model):
    id = db.Column(db.Integer, primary_key=True)
    username = db.Column(db.String(80), unique=True, nullable=False)
    password = db.Column(db.String(120), nullable=False)
    role = db.Column(db.String(20), nullable=False)
    transactions = db.relationship('Transaction', backref='user', lazy=True)

    def set_password(self, password):
        self.password = generate_password_hash(password)

    def check_password(self, password):
        return check_password_hash(self.password, password)

class Product(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(100), nullable=False)
    description = db.Column(db.Text)
    quantity = db.Column(db.Integer, default=0)
    unit_price = db.Column(db.Float, nullable=False)
    reorder_level = db.Column(db.Integer, default=10)
    category = db.Column(db.String(50))
    barcode = db.Column(db.String(50), unique=True)
    expiry_date = db.Column(db.Date)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    transactions = db.relationship('Transaction', backref='product', lazy=True)

class Transaction(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    product_id = db.Column(db.Integer, db.ForeignKey('product.id'), nullable=False)
    quantity = db.Column(db.Integer, nullable=False)
    transaction_type = db.Column(db.String(20), nullable=False)  # 'in' or 'out'
    date = db.Column(db.DateTime, default=datetime.utcnow)
    user_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=False)

@login_manager.user_loader
def load_user(user_id):
    return db.session.get(User, int(user_id))

# Routes
@app.route('/')
@login_required
def index():
    products = Product.query.all()
    today = datetime.now().date()
    return render_template('products.html', products=products, today=today)

@app.route('/stock/in/<int:product_id>', methods=['GET', 'POST'])
@login_required
def stock_in(product_id):
    product = Product.query.get_or_404(product_id)
    if request.method == 'POST':
        try:
            quantity = int(request.form.get('quantity', 0))
            if quantity <= 0:
                flash('Quantity must be greater than 0', 'danger')
            else:
                product.quantity += quantity
                transaction = Transaction(
                    product_id=product_id,
                    quantity=quantity,
                    transaction_type='in',
                    user_id=current_user.id
                )
                db.session.add(transaction)
                db.session.commit()
                flash('Stock updated successfully', 'success')
                return redirect(url_for('dashboard'))
        except ValueError:
            flash('Invalid quantity', 'danger')
    return render_template('stock_in.html', product=product)

@app.route('/login', methods=['GET', 'POST'])
def login():
    if request.method == 'POST':
        username = request.form.get('username')
        password = request.form.get('password')
        user = User.query.filter_by(username=username).first()
        
        if user and user.check_password(password):
            login_user(user)
            return redirect(url_for('index'))
            
        flash('Invalid username or password', 'danger')
    return render_template('login.html')

@app.route('/logout')
@login_required
def logout():
    logout_user()
    return redirect(url_for('login'))

@app.route('/api/products', methods=['POST'])
@login_required
def add_product():
    try:
        data = request.get_json()
        
        # Validate required fields
        required_fields = ['name', 'category', 'unit_price', 'quantity', 'reorder_level']
        for field in required_fields:
            if field not in data or not str(data[field]).strip():
                return jsonify({'error': f'{field.title()} is required'}), 400
        
        # Validate numeric fields
        try:
            unit_price = float(data['unit_price'])
            quantity = int(data['quantity'])
            reorder_level = int(data['reorder_level'])
            
            if unit_price <= 0:
                return jsonify({'error': 'Unit price must be greater than 0'}), 400
            if quantity < 0:
                return jsonify({'error': 'Quantity cannot be negative'}), 400
            if reorder_level < 0:
                return jsonify({'error': 'Reorder level cannot be negative'}), 400
                
        except ValueError:
            return jsonify({'error': 'Invalid numeric values provided'}), 400
        
        # Validate expiry date
        expiry_date = None
        if data.get('expiry_date'):
            try:
                expiry_date = datetime.strptime(data['expiry_date'], '%Y-%m-%d').date()
                if expiry_date < datetime.now().date():
                    return jsonify({'error': 'Expiry date cannot be in the past'}), 400
            except ValueError:
                return jsonify({'error': 'Invalid expiry date format. Use YYYY-MM-DD'}), 400
        
        # Check if barcode already exists
        if data.get('barcode'):
            existing_product = Product.query.filter_by(barcode=data['barcode']).first()
            if existing_product:
                return jsonify({'error': 'Product with this barcode already exists'}), 400
        
        new_product = Product(
            name=data['name'],
            category=data['category'],
            description=data.get('description', ''),
            unit_price=unit_price,
            quantity=quantity,
            reorder_level=reorder_level,
            barcode=data.get('barcode'),
            expiry_date=expiry_date
        )
        
        db.session.add(new_product)
        db.session.commit()
        
        return jsonify({
            'message': 'Product added successfully',
            'id': new_product.id
        })
        
    except Exception as e:
        db.session.rollback()
        print(f"Error adding product: {str(e)}")  # For debugging
        return jsonify({'error': 'An error occurred while adding the product'}), 400

@app.route('/api/products/<int:product_id>', methods=['PUT'])
@login_required
def update_product(product_id):
    try:
        product = Product.query.get_or_404(product_id)
        data = request.get_json()
        
        product.name = data.get('name', product.name)
        product.category = data.get('category', product.category)
        product.description = data.get('description', product.description)
        product.unit_price = float(data.get('unit_price', product.unit_price))
        product.reorder_level = int(data.get('reorder_level', product.reorder_level))
        product.barcode = data.get('barcode', product.barcode)
        
        if data.get('expiry_date'):
            product.expiry_date = datetime.strptime(data['expiry_date'], '%Y-%m-%d').date()
        
        db.session.commit()
        return jsonify({'message': 'Product updated successfully'})
    except Exception as e:
        db.session.rollback()
        return jsonify({'error': str(e)}), 400

@app.route('/api/products/<int:product_id>/stock', methods=['POST'])
@login_required
def update_stock(product_id):
    try:
        product = Product.query.get_or_404(product_id)
        data = request.get_json()
        
        # Validate input data
        if not isinstance(data, dict):
            return jsonify({'error': 'Invalid request data'}), 400
            
        if 'quantity' not in data or 'operation' not in data:
            return jsonify({'error': 'Missing required fields'}), 400
            
        try:
            quantity = int(data['quantity'])
            if quantity <= 0:
                return jsonify({'error': 'Quantity must be greater than 0'}), 400
        except (ValueError, TypeError):
            return jsonify({'error': 'Invalid quantity value'}), 400
            
        operation = str(data['operation']).strip().lower()
        
        if operation not in ['add', 'remove']:
            return jsonify({'error': 'Invalid operation. Use "add" or "remove"'}), 400
        
        if operation == 'add':
            product.quantity += quantity
            transaction_type = 'in'
        else:  # operation == 'remove'
            if product.quantity < quantity:
                return jsonify({'error': 'Insufficient stock'}), 400
            product.quantity -= quantity
            transaction_type = 'out'
        
        # Record transaction
        transaction = Transaction(
            product_id=product_id,
            quantity=quantity,
            transaction_type=transaction_type,
            user_id=current_user.id
        )
        db.session.add(transaction)
        db.session.commit()
        
        return jsonify({
            'message': f'Stock {operation}ed successfully',
            'new_quantity': product.quantity
        })
    except Exception as e:
        db.session.rollback()
        return jsonify({'error': str(e)}), 400

@app.route('/api/products/<int:product_id>', methods=['DELETE'])
@login_required
def delete_product(product_id):
    try:
        product = Product.query.get_or_404(product_id)
        
        # Delete associated transactions first
        Transaction.query.filter_by(product_id=product_id).delete()
        
        # Now delete the product
        db.session.delete(product)
        db.session.commit()
        
        return jsonify({'message': 'Product deleted successfully'})
    except Exception as e:
        db.session.rollback()
        return jsonify({'error': str(e)}), 400

@app.route('/api/products/<int:product_id>/predict_restock', methods=['GET'])
@login_required
def predict_restock(product_id):
    try:
        product = Product.query.get_or_404(product_id)
        
        # Get last 30 days transactions
        thirty_days_ago = datetime.utcnow() - timedelta(days=30)
        transactions = Transaction.query.filter(
            Transaction.product_id == product_id,
            Transaction.date >= thirty_days_ago
        ).all()
        
        # Calculate daily average consumption
        total_out = sum(t.quantity for t in transactions if t.transaction_type == 'out')
        daily_avg = total_out / 30
        
        # Predict days until reorder level
        if daily_avg > 0:
            current_stock = product.quantity
            days_until_reorder = (current_stock - product.reorder_level) / daily_avg
            suggested_order = math.ceil(daily_avg * 30)  # 30 days supply
            
            return jsonify({
                'days_until_reorder': round(days_until_reorder),
                'suggested_order': suggested_order,
                'daily_average_consumption': round(daily_avg, 2)
            })
        else:
            return jsonify({
                'message': 'Insufficient transaction data for prediction'
            })
            
    except Exception as e:
        return jsonify({'error': str(e)}), 400

@app.route('/api/products/barcode/<barcode>', methods=['GET'])
@login_required
def get_product_by_barcode(barcode):
    try:
        product = Product.query.filter_by(barcode=barcode).first()
        if product:
            return jsonify({
                'product': {
                    'id': product.id,
                    'name': product.name,
                    'category': product.category,
                    'description': product.description,
                    'unit_price': product.unit_price,
                    'quantity': product.quantity,
                    'reorder_level': product.reorder_level,
                    'barcode': product.barcode,
                    'expiry_date': product.expiry_date.strftime('%Y-%m-%d') if product.expiry_date else None
                }
            })
        return jsonify({'product': None})
    except Exception as e:
        return jsonify({'error': str(e)}), 400

@app.route('/api/products/barcode/<barcode>/info', methods=['GET'])
@login_required
def get_product_info_by_barcode(barcode):
    try:
        # Fetch product information from Open Food Facts API
        response = requests.get(f'https://world.openfoodfacts.org/api/v0/product/{barcode}.json')
        data = response.json()
        
        if data['status'] == 1 and data['product']:
            product_data = data['product']
            return jsonify({
                'success': True,
                'product': {
                    'name': product_data.get('product_name', ''),
                    'category': product_data.get('categories', ''),
                    'description': product_data.get('generic_name', ''),
                    'brand': product_data.get('brands', ''),
                    'image_url': product_data.get('image_url', '')
                }
            })
        
        return jsonify({
            'success': False,
            'message': 'Product not found in database'
        })
        
    except Exception as e:
        return jsonify({
            'success': False,
            'message': str(e)
        }), 400

@app.route('/dashboard')
@login_required
def dashboard():
    today = datetime.now().date()
    thirty_days_ago = today - timedelta(days=30)
    
    # Get summary statistics
    total_products = Product.query.count()
    low_stock_products = Product.query.filter(Product.quantity <= Product.reorder_level).all()
    low_stock_count = len(low_stock_products)
    expiring_soon_count = Product.query.filter(
        Product.expiry_date <= today + timedelta(days=30),
        Product.expiry_date > today
    ).count()
    todays_transactions = Transaction.query.filter(
        Transaction.date >= today
    ).count()
    
    # Get category statistics
    categories = db.session.query(Product.category, db.func.count(Product.id)).group_by(Product.category).all()
    category_labels = [c[0] for c in categories]
    category_data = [c[1] for c in categories]
    
    # Get transaction history
    transaction_history = db.session.query(
        Transaction.date,  # Use Transaction.date directly instead of db.func.date()
        db.func.count(Transaction.id)
    ).filter(
        Transaction.date >= thirty_days_ago
    ).group_by(
        db.func.date(Transaction.date)  # Keep the grouping by date
    ).all()
    
    transaction_dates = [t[0].strftime('%Y-%m-%d') for t in transaction_history]
    transaction_counts = [t[1] for t in transaction_history]
    
    return render_template('dashboard.html',
        total_products=total_products,
        low_stock_count=low_stock_count,
        expiring_soon_count=expiring_soon_count,
        todays_transactions=todays_transactions,
        low_stock_products=low_stock_products,
        category_labels=category_labels,
        category_data=category_data,
        transaction_dates=transaction_dates,
        transaction_counts=transaction_counts
    )

@app.route('/transactions')
@login_required
def transactions():
    # Get filter parameters
    date_range = request.args.get('date', 'month')
    transaction_type = request.args.get('type', 'all')
    product_id = request.args.get('product', 'all')
    
    # Base query
    query = Transaction.query.join(Product).join(User)  # Join with related tables
    
    # Apply date filter
    today = datetime.now().date()
    if date_range == 'today':
        query = query.filter(db.func.date(Transaction.date) == today)
    elif date_range == 'week':
        week_ago = today - timedelta(days=7)
        query = query.filter(Transaction.date >= week_ago)
    elif date_range == 'month':
        month_ago = today - timedelta(days=30)
        query = query.filter(Transaction.date >= month_ago)
    
    # Apply type filter
    if transaction_type != 'all':
        query = query.filter(Transaction.transaction_type == transaction_type)
    
    # Apply product filter
    if product_id != 'all':
        query = query.filter(Transaction.product_id == int(product_id))
    
    # Get transactions with related data
    transactions = query.order_by(Transaction.date.desc()).all()
    products = Product.query.all()
    
    return render_template('transactions.html',
        transactions=transactions,
        products=products
    )

@app.route('/transactions/export')
@login_required
def export_transactions():
    try:
        # Get filter parameters
        date_range = request.args.get('date', 'month')
        transaction_type = request.args.get('type', 'all')
        product_id = request.args.get('product', 'all')
        
        # Base query
        query = Transaction.query.join(Product).join(User)
        
        # Apply date filter
        today = datetime.now().date()
        if date_range == 'today':
            query = query.filter(db.func.date(Transaction.date) == today)
        elif date_range == 'week':
            week_ago = today - timedelta(days=7)
            query = query.filter(Transaction.date >= week_ago)
        elif date_range == 'month':
            month_ago = today - timedelta(days=30)
            query = query.filter(Transaction.date >= month_ago)
        
        # Apply type filter
        if transaction_type != 'all':
            query = query.filter(Transaction.transaction_type == transaction_type)
        
        # Apply product filter
        if product_id != 'all':
            query = query.filter(Transaction.product_id == int(product_id))
        
        # Get transactions
        transactions = query.order_by(Transaction.date.desc()).all()
        
        # Create CSV
        output = io.StringIO()
        writer = csv.writer(output)
        
        # Write header
        writer.writerow(['Date', 'Product', 'Quantity', 'Type', 'User'])
        
        # Write data
        for t in transactions:
            writer.writerow([
                t.date.strftime('%Y-%m-%d %H:%M:%S'),
                t.product.name,
                t.quantity,
                t.transaction_type,
                t.user.username
            ])
        
        # Create response
        output.seek(0)
        return make_response(
            output.getvalue(),
            200,
            {
                'Content-Type': 'text/csv',
                'Content-Disposition': f'attachment; filename=transactions_{datetime.now().strftime("%Y%m%d")}.csv'
            }
        )
        
    except Exception as e:
        return jsonify({'error': str(e)}), 400

def reset_admin():
    # Delete existing admin user and their transactions
    admin = User.query.filter_by(username='admin').first()
    if admin:
        Transaction.query.filter_by(user_id=admin.id).delete()
        db.session.delete(admin)
        db.session.commit()
    
    # Create new admin user
    admin = User(
        username='admin',
        role='admin'
    )
    admin.set_password('admin123')
    db.session.add(admin)
    db.session.commit()

def create_sample_products():
    # First check if products already exist
    if Product.query.count() > 0:
        return

    sample_products = [
        {
            'name': 'Paracetamol 500mg',
            'category': 'Pain Relief',
            'description': 'Common pain reliever and fever reducer',
            'unit_price': 15.99,
            'quantity': 100,
            'reorder_level': 20,
            'barcode': '8901234567890',
            'expiry_date': datetime.now().date() + timedelta(days=365)
        },
        {
            'name': 'Amoxicillin 500mg',
            'category': 'Antibiotics',
            'description': 'Broad-spectrum antibiotic',
            'unit_price': 45.99,
            'quantity': 50,
            'reorder_level': 15,
            'barcode': '8901234567891',
            'expiry_date': datetime.now().date() + timedelta(days=180)
        },
        {
            'name': 'Omeprazole 20mg',
            'category': 'Gastrointestinal',
            'description': 'Proton pump inhibitor for acid reflux',
            'unit_price': 89.99,
            'quantity': 30,
            'reorder_level': 10,
            'barcode': '8901234567892',
            'expiry_date': datetime.now().date() + timedelta(days=270)
        },
        {
            'name': 'Metformin 500mg',
            'category': 'Diabetes',
            'description': 'Oral diabetes medication',
            'unit_price': 75.99,
            'quantity': 60,
            'reorder_level': 15,
            'barcode': '8901234567893',
            'expiry_date': datetime.now().date() + timedelta(days=240)
        },
        {
            'name': 'Cetirizine 10mg',
            'category': 'Antihistamine',
            'description': 'Antihistamine for allergies',
            'unit_price': 25.99,
            'quantity': 80,
            'reorder_level': 20,
            'barcode': '8901234567894',
            'expiry_date': datetime.now().date() + timedelta(days=300)
        }
    ]
    
    for product_data in sample_products:
        # Check if product with this barcode already exists
        existing_product = Product.query.filter_by(barcode=product_data['barcode']).first()
        if not existing_product:
            product = Product(**product_data)
            db.session.add(product)
    
    try:
        db.session.commit()
    except Exception as e:
        db.session.rollback()

if __name__ == '__main__':
    # Delete the database file if it exists
    if os.path.exists('pharmacy.db'):
        os.remove('pharmacy.db')
    
    with app.app_context():
        db.create_all()
        reset_admin()
        create_sample_products()
    
    print("Starting server at http://127.0.0.1:5000")
    app.run(host='127.0.0.1', port=5000, debug=False) 