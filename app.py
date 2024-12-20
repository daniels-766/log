from flask import Flask, render_template, request, redirect, url_for, flash, request
from flask_sqlalchemy import SQLAlchemy
from flask_login import LoginManager, UserMixin, login_user, login_required, logout_user, current_user
from werkzeug.security import generate_password_hash, check_password_hash
from models import db, User, Income, Expense
from flask import jsonify
from datetime import datetime
from sqlalchemy import extract
import requests
from flask_paginate import Pagination, get_page_parameter
from flask import send_file
import pandas as pd
from io import BytesIO

app = Flask(__name__)
app.config['SECRET_KEY'] = 'your_secret_key'
app.config['SQLALCHEMY_DATABASE_URI'] = 'mysql+pymysql://root:@localhost/login'
db.init_app(app)

login_manager = LoginManager()
login_manager.init_app(app)
login_manager.login_view = 'login'

@login_manager.user_loader
def load_user(user_id):
    return User.query.get(int(user_id))

@app.route('/register', methods=['GET', 'POST'])
def register():
    if request.method == 'POST':
        username = request.form.get('username')
        password = request.form.get('password')

        if not username or not password:
            flash('Username and password are required', 'warning')
            return redirect(url_for('register'))
        
        existing_user = User.query.filter_by(username=username).first()
        if existing_user:
            flash('Username already exists. Please choose a different one.', 'danger')
            return redirect(url_for('register'))

        hashed_password = generate_password_hash(password, method='pbkdf2:sha256')
        role = 'admin' if 'is_admin' in request.form else 'user'
        new_user = User(username=username, password=hashed_password, role=role)
        db.session.add(new_user)
        db.session.commit()
        
        flash('Registration successful!', 'success')
        return redirect(url_for('register'))
    return render_template('register.html')

@app.template_filter('format_currency')
def format_currency(value):
    if value is not None:
        return '{:,.0f}'.format(value).replace(',', '.').replace('.', ',', 1)
    return '0'


@app.route('/', methods=['GET', 'POST'])
def login():
    if request.method == 'POST':
        user = User.query.filter_by(username=request.form['username']).first()
        if user and check_password_hash(user.password, request.form['password']):
            login_user(user)
            return redirect(url_for('admin_dashboard' if user.role == 'admin' else 'user_dashboard'))
        flash('Login Unsuccessful. Please check username and password')
    return render_template('login.html')

@app.route('/admin-dashboard')
@login_required
def admin_dashboard():
    if current_user.role != 'admin':
        return redirect(url_for('user_dashboard'))

    total_users = User.query.filter_by(role='user').count()
    users = User.query.filter(User.role != 'admin').all()

    # Mengambil pengeluaran beserta nama pengguna
    expenses = db.session.query(
        Expense,
        User.username
    ).join(User).order_by(Expense.date.desc()).all()

    current_date = datetime.now().date()
    daily_expenses = Expense.query.filter(db.func.date(Expense.date) == current_date).all()
    total_daily_expenses = sum(expense.amount for expense in daily_expenses)

    current_month = datetime.now().month
    current_year = datetime.now().year
    monthly_expenses = Expense.query.filter(
        db.extract('month', Expense.date) == current_month,
        db.extract('year', Expense.date) == current_year
    ).all()
    total_monthly_expenses = sum(expense.amount for expense in monthly_expenses)

    total_transactions_today = len(daily_expenses)

    return render_template('admin_dashboard.html',
                           total_users=total_users,
                           total_daily_expenses=total_daily_expenses,
                           total_monthly_expenses=total_monthly_expenses,
                           total_transactions_today=total_transactions_today,
                           users=users,
                           expenses=expenses)  # Ganti ini dengan expenses yang baru

@app.template_filter('rupiah')
def format_rupiah(value):
    """Format angka menjadi format rupiah."""
    if value is None:
        return "Rp 0"
    return f'Rp {value:,.0f}'.replace(',', '.')


@app.route('/user-dashboard')
@login_required
def user_dashboard():
    current_date = datetime.now().date() 

    expenses_today = Expense.query.filter_by(user_id=current_user.id) \
                                   .filter(db.func.date(Expense.date) == current_date) \
                                   .order_by(Expense.date.desc()) \
                                   .limit(10).all()

    total_daily_expense = sum(expense.amount for expense in expenses_today) if expenses_today else 0

    current_month = datetime.now().month
    current_year = datetime.now().year
    incomes = Income.query.filter_by(user_id=current_user.id).filter(
        db.extract('month', Income.date) == current_month,
        db.extract('year', Income.date) == current_year
    ).all()

    total_income = sum(income.amount for income in incomes) if incomes else 0

    total_expense = sum(expense.amount for expense in expenses_today) if expenses_today else 0
    
    balance = total_income - total_expense
    transaction_count = len(expenses_today)  

    total_daily_expense = total_daily_expense or 0
    total_income = total_income or 0
    total_expense = total_expense or 0

    return render_template('user_dashboard.html', 
                           total_income=total_income, 
                           total_daily_expense=total_daily_expense,  
                           total_expense=total_expense,
                           balance=balance,
                           transaction_count=transaction_count,
                           expenses=expenses_today) 

@app.route('/get_monthly_expenses')
@login_required
def get_monthly_expenses():
    current_year = datetime.now().year 
    monthly_expenses = [0] * 12  

    expenses = Expense.query.filter_by(user_id=current_user.id).filter(extract('year', Expense.date) == current_year).all()
    
    for expense in expenses:
        if expense.date:
            month = expense.date.month 
            monthly_expenses[month - 1] += expense.amount 

    return jsonify(monthly_expenses)  
 
@app.route('/logout')
@login_required
def logout():
    logout_user()
    return redirect(url_for('login'))

@app.route('/dashboard')
@login_required
def dashboard():
    current_month = datetime.now().month
    current_year = datetime.now().year
    
    incomes = Income.query.filter_by(user_id=current_user.id).filter(db.extract('month', Income.date) == current_month, db.extract('year', Income.date) == current_year).all()
    expenses = Expense.query.filter_by(user_id=current_user.id).filter(db.extract('month', Expense.date) == current_month, db.extract('year', Expense.date) == current_year).all()

    total_income = sum(income.amount for income in incomes)
    total_expense = sum(expense.amount for expense in expenses)
    balance = total_income - total_expense
    transaction_count = len(expenses)  

    return render_template('user_dashboard.html', total_income=total_income, 
                       total_expense=total_expense, balance=balance,
                       transaction_count=transaction_count)

@app.route('/add-income', methods=['GET', 'POST'])
@login_required
def add_income():
    if request.method == 'POST':
        amount = request.form.get('amount')
        description = request.form.get('description')
        new_income = Income(user_id=current_user.id, amount=amount, description=description)
        db.session.add(new_income)
        db.session.commit()
        flash('Income added successfully!', 'success')
        return redirect(url_for('dashboard'))
    return render_template('add_income.html')

@app.route('/add-expense', methods=['POST'])
@login_required
def add_expense():
    name = request.form.get('name')
    amount = request.form.get('amount')
    description = request.form.get('description')
    method = request.form.get('method')
    
    new_expense = Expense(
        user_id=current_user.id,
        name=name,
        amount=amount,
        description=description,
        method=method,
        date=datetime.now()
    )
    
    db.session.add(new_expense)
    db.session.commit()

    flash('Pengeluaran berhasil ditambahkan!', 'success')
    return redirect(url_for('user_dashboard'))

@app.route('/export-expenses')
@login_required
def export_expenses():
    expenses = Expense.query.filter_by(user_id=current_user.id).all()
    data = {
        "Date": [expense.date.strftime('%Y-%m-%d') for expense in expenses],
        "Description": [expense.description for expense in expenses],
        "Amount": [expense.amount for expense in expenses],
        "Method": [expense.method for expense in expenses],
    }
    df = pd.DataFrame(data)
    
    # Simpan ke dalam buffer
    output = BytesIO()
    df.to_excel(output, index=False, engine='openpyxl')
    output.seek(0)

    return send_file(output, as_attachment=True, download_name='expenses.xlsx', mimetype='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet')


if __name__ == '__main__':
    with app.app_context():
        db.create_all()  
    app.run(debug=True)
