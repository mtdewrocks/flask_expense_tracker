import os
from datetime import datetime, timedelta

from flask import (
    Flask, render_template_string, request,
    redirect, url_for
)
from flask_login import (
    LoginManager, login_user, login_required,
    logout_user, current_user, UserMixin
)
from werkzeug.security import generate_password_hash, check_password_hash

from sqlalchemy import (
    create_engine, Column, Integer, String,
    Float, DateTime, ForeignKey
)
from sqlalchemy.orm import sessionmaker, declarative_base, relationship

import pandas as pd
from dash import Dash, dcc, html, Input, Output
import plotly.express as px

# ============================================================
#  CONFIG
# ============================================================


# Use a different DB path on Render so it can live on the mounted disk
DB_PATH = "/var/data/expenses.db"

app = Flask(__name__)
app.secret_key = os.environ.get("SECRET_KEY", "dev-secret")

Base = declarative_base()

# ============================================================
#  DATABASE MODELS
# ============================================================

class User(Base, UserMixin):
    __tablename__ = "users"

    id = Column(Integer, primary_key=True)
    username = Column(String(50), unique=True, nullable=False)
    password_hash = Column(String(255), nullable=False)
    is_admin = Column(Integer, default=0)

    expenses = relationship("Expense", back_populates="user")
    budgets = relationship("Budget", back_populates="user")
    debts = relationship("Debt", back_populates="user")
    allocations = relationship("Allocation", back_populates="user")

    def set_password(self, password):
        self.password_hash = generate_password_hash(password)

    def check_password(self, password):
        return check_password_hash(self.password_hash, password)


class Expense(Base):
    __tablename__ = "expenses"

    id = Column(Integer, primary_key=True)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=False)
    amount = Column(Float, nullable=False)
    category = Column(String(50), nullable=False)
    description = Column(String(255), nullable=True)
    created_at = Column(DateTime, nullable=False, default=datetime.utcnow)

    user = relationship("User", back_populates="expenses")


class Budget(Base):
    __tablename__ = "budgets"

    id = Column(Integer, primary_key=True)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=False)
    category = Column(String(50), nullable=False)
    month = Column(String(7), nullable=False)  # "YYYY-MM"
    amount = Column(Float, nullable=False)

    user = relationship("User", back_populates="budgets")


class Debt(Base):
    __tablename__ = "debts"

    id = Column(Integer, primary_key=True)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=False)

    name = Column(String(100), nullable=False)
    original_balance = Column(Float, nullable=False)
    current_balance = Column(Float, nullable=False)
    interest_rate = Column(Float, nullable=False)  # APR as percent (e.g., 18.5)

    created_at = Column(DateTime, default=datetime.utcnow)

    user = relationship("User", back_populates="debts")

class Allocation(Base):
    __tablename__ = "allocations"

    id = Column(Integer, primary_key=True)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=False)
    category = Column(String(50), nullable=False)
    amount = Column(Float, nullable=False)
    created_at = Column(DateTime, default=datetime.utcnow)

    user = relationship("User", back_populates="allocations")
# ============================================================
#  DATABASE SETUP
# ============================================================

def get_engine():
    return create_engine(f"sqlite:///{DB_PATH}", echo=False, future=True)

engine = get_engine()
Base.metadata.create_all(engine)

SessionLocal = sessionmaker(bind=engine, autoflush=False, autocommit=False)

# ============================================================
#  LOGIN MANAGER
# ============================================================

login_manager = LoginManager()
login_manager.init_app(app)
login_manager.login_view = "login"

@login_manager.user_loader
def load_user(user_id):
    session = SessionLocal()
    try:
        return session.get(User, int(user_id))
    finally:
        session.close()

# ============================================================
#  CATEGORY LIST (Alphabetized, your custom categories)
# ============================================================

DEFAULT_CATEGORIES = [
    "Amazon Music",
    "Amazon Prime",
    "ATT",
    "Car Insurance",
    "Car Payment",
    "Car Repairs",
    "Car Taxes",
    "Cat Needs",
    "Child Support",
    "Clothing",
    "Credit Cards",
    "Dating",
    "Eating Out",
    "Education",
    "Electric",
    "Entertainment",
    "Gas",
    "Garbage",
    "Gifts",
    "Groceries",
    "Gym Membership",
    "HP Ink",
    "Household Needs",
    "Kid Needs",
    "Medical",
    "Miscellaneous",
    "Mom and David",
    "Mortgage",
    "NASA Personal Loan",
    "Personal Care",
    "Phone Bill",
    "Prosper",
    "Savings",
    "Snacks",
    "Spire",
    "Student Loans",
    "TSP",
    "Water"
]

# ============================================================
#  LOGIN TEMPLATE
# ============================================================

LOGIN_TEMPLATE = """
<!doctype html>
<html>
<head>
  <meta charset="utf-8">
  <title>Login</title>
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <style>
    body { font-family: system-ui; background:#f5f5f5; display:flex; align-items:center;
           justify-content:center; height:100vh; margin:0; }
    .box { background:#fff; padding:20px; border-radius:8px;
           box-shadow:0 1px 3px rgba(0,0,0,0.1); width:100%; max-width:320px; }
    h2 { margin-top:0; text-align:center; }
    label { font-size:14px; display:block; margin-bottom:4px; }
    input { width:100%; padding:8px; margin-bottom:10px; border-radius:4px;
            border:1px solid #ccc; box-sizing:border-box; }
    button { width:100%; padding:8px; border:none; border-radius:4px;
             background:#007bff; color:white; font-size:14px; cursor:pointer; }
    button:hover { background:#0056b3; }
    .error { color:#d9534f; font-size:13px; margin-bottom:8px; text-align:center; }
  </style>
</head>
<body>
  <div class="box">
    <h2>Login</h2>
    {% if error %}
    <div class="error">{{ error }}</div>
    {% endif %}
    <form method="post">
      <label>Username</label>
      <input name="username" autofocus>
      <label>Password</label>
      <input name="password" type="password">
      <button type="submit">Login</button>
    </form>
  </div>
</body>
</html>
"""

# ============================================================
#  ADMIN CREATE USER TEMPLATE
# ============================================================

ADMIN_CREATE_USER_TEMPLATE = """
<!doctype html>
<html>
<head>
  <meta charset="utf-8">
  <title>Create User</title>
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <style>
    body { font-family: system-ui; background:#f5f5f5; display:flex; align-items:center;
           justify-content:center; height:100vh; margin:0; }
    .box { background:#fff; padding:20px; border-radius:8px;
           box-shadow:0 1px 3px rgba(0,0,0,0.1); width:100%; max-width:340px; }
    h2 { margin-top:0; text-align:center; }
    label { font-size:14px; display:block; margin-bottom:4px; }
    input { width:100%; padding:8px; margin-bottom:10px; border-radius:4px;
            border:1px solid #ccc; box-sizing:border-box; }
    button { width:100%; padding:8px; border:none; border-radius:4px;
             background:#28a745; color:white; font-size:14px; cursor:pointer; }
    button:hover { background:#218838; }
    .msg { font-size:13px; margin-bottom:8px; text-align:center; }
    a { display:block; text-align:center; margin-top:10px; }
  </style>
</head>
<body>
  <div class="box">
    <h2>Create User</h2>
    {% if message %}
    <div class="msg">{{ message }}</div>
    {% endif %}
    <form method="post">
      <label>Username</label>
      <input name="username" required>
      <label>Password</label>
      <input name="password" type="password" required>
      <button type="submit">Create User</button>
    </form>
    <a href="{{ url_for('index') }}">Back to app</a>
  </div>
</body>
</html>
"""

# ============================================================
#  MAIN EXPENSE PAGE TEMPLATE
# ============================================================

TEMPLATE = """
<!doctype html>
<html>
<head>
  <meta charset="utf-8">
  <title>Expense Tracker</title>
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <style>
    body { font-family: system-ui; background:#f5f5f5; margin:0; padding:0; }
    .container { max-width:900px; margin:auto; padding:16px; }
    h1 { text-align:center; margin-bottom:16px; }
    form { background:#fff; padding:12px; border-radius:8px; margin-bottom:16px;
           box-shadow:0 1px 3px rgba(0,0,0,0.1); }
    .field-group { display:flex; flex-wrap:wrap; gap:8px; margin-bottom:8px; }
    .field { flex:1 1 120px; min-width:120px; }
    label { font-size:14px; display:block; margin-bottom:2px; }
    input, select { width:100%; padding:8px; border-radius:4px; border:1px solid #ccc; }
    button { background:#007bff; color:white; border:none; padding:8px 16px;
             border-radius:4px; cursor:pointer; }
    button:hover { background:#0056b3; }
    table { width:100%; border-collapse:collapse; background:#fff;
            box-shadow:0 1px 3px rgba(0,0,0,0.1); }
    th, td { padding:8px; border-bottom:1px solid #eee; }
    th { background:#f0f0f0; }
    .amount { text-align:right; }
    .icon-btn { background:none; border:none; cursor:pointer; padding:0 6px; font-size:16px; }
    .delete-btn { color:#d9534f; }
    .edit-btn { color:#0275d8; }
    .summary { background:#fff; padding:12px; border-radius:8px; margin-bottom:16px; }
    .summary-grid { display:flex; flex-wrap:wrap; gap:8px; }
    .summary-item { flex:1 1 120px; background:#f8f9fa; padding:8px; border-radius:4px; }
    .top-bar { display:flex; justify-content:space-between; margin-bottom:8px; }
    .nav-links a { margin-left:12px; text-decoration:none; color:#007bff; }
  </style>
</head>
<body>
  <div class="container">

    <div class="top-bar">
      <div>
        Logged in as <strong>{{ current_user.username }}</strong>
        {% if current_user.is_admin %}
          <span style="color:#28a745;">(admin)</span>
          &middot; <a href="{{ url_for('admin_create_user') }}">Create user</a>
        {% endif %}
      </div>
      <div class="nav-links">
        <a href="/">Expenses</a>
        <a href="/budgets">Budgets</a>
        <a href="/dashboard/">Dashboard</a>
        <a href="/logout">Logout</a>
      </div>
    </div>

    <h1>Expense Tracker</h1>

    <form method="post" action="{{ url_for('add_expense') }}">
      <div class="field-group">
        <div class="field">
          <label>Amount</label>
          <input type="number" step="0.01" name="amount" required>
        </div>
        <div class="field">
          <label>Category</label>
          <select name="category" required>
            {% for cat in categories %}
            <option value="{{ cat }}">{{ cat }}</option>
            {% endfor %}
          </select>
        </div>
        <div class="field">
          <label>Description</label>
          <input type="text" name="description">
        </div>
      </div>
      <button type="submit">Add Expense</button>
    </form>

    <div class="summary">
      <h2>Summary (last 30 days)</h2>
      <div class="summary-grid">
        <div class="summary-item">
          <strong>Total Spent</strong>
          ${{ "%.2f"|format(total_spent) }}
        </div>
        {% for cat, amt in category_totals.items() %}
        <div class="summary-item">
          <strong>{{ cat }}</strong>
          ${{ "%.2f"|format(amt) }}
        </div>
        {% endfor %}
      </div>
    </div>

    <table>
      <thead>
        <tr>
          <th>Date</th>
          <th>Category</th>
          <th>Description</th>
          <th class="amount">Amount</th>
          <th>Actions</th>
        </tr>
      </thead>
      <tbody>
        {% for e in expenses %}
        {% if editing_id == e.id %}
        <tr>
          <form method="post" action="{{ url_for('edit_expense', expense_id=e.id) }}">
            <td>{{ e.created_at.strftime("%Y-%m-%d %H:%M") }}</td>
            <td>
              <select name="category">
                {% for cat in categories %}
                <option value="{{ cat }}" {% if cat == e.category %}selected{% endif %}>{{ cat }}</option>
                {% endfor %}
              </select>
            </td>
            <td><input type="text" name="description" value="{{ e.description }}"></td>
            <td><input type="number" step="0.01" name="amount" value="{{ e.amount }}"></td>
            <td>
              <button class="icon-btn edit-btn">Save</button>
              <a href="/" class="icon-btn">Cancel</a>
            </td>
          </form>
        </tr>
        {% else %}
        <tr>
          <td>{{ e.created_at.strftime("%Y-%m-%d %H:%M") }}</td>
          <td>{{ e.category }}</td>
          <td>{{ e.description }}</td>
          <td class="amount">${{ "%.2f"|format(e.amount) }}</td>
          <td>
            <form method="post" action="{{ url_for('start_edit_expense', expense_id=e.id) }}" style="display:inline;">
              <button class="icon-btn edit-btn">&#9998;</button>
            </form>
            <form method="post" action="{{ url_for('delete_expense', expense_id=e.id) }}" style="display:inline;">
              <button class="icon-btn delete-btn">&times;</button>
            </form>
          </td>
        </tr>
        {% endif %}
        {% endfor %}
      </tbody>
    </table>

  </div>
</body>
</html>
"""

# ============================================================
#  BUDGET PAGE TEMPLATE
# ============================================================

BUDGET_TEMPLATE = """
<!doctype html>
<html>
<head>
  <meta charset="utf-8">
  <title>Budgets</title>
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <style>
    body { font-family: system-ui; background:#f5f5f5; margin:0; padding:0; }
    .container { max-width:700px; margin:auto; padding:16px; }
    h1 { text-align:center; margin-bottom:16px; }
    form { background:#fff; padding:16px; border-radius:8px; }
    table { width:100%; border-collapse:collapse; margin-top:16px; }
    th, td { padding:8px; border-bottom:1px solid #eee; }
    th { background:#f0f0f0; }
    input { width:100%; padding:6px; border-radius:4px; border:1px solid #ccc; }
    button { margin-top:16px; width:100%; padding:10px; background:#28a745;
             color:white; border:none; border-radius:4px; cursor:pointer; }
    .nav a { margin-right:12px; text-decoration:none; color:#007bff; }
  </style>
</head>
<body>
  <div class="container">

    <div class="nav">
      <a href="/">Expenses</a>
      <a href="/dashboard/">Dashboard</a>
      <a href="/logout">Logout</a>
    </div>

    <h1>Monthly Budgets</h1>

    <form method="post">

      <label>Select Month</label>
      <input type="month" name="month" value="{{ selected_month }}"
             onchange="window.location='?month=' + this.value">

      <table>
        <thead>
          <tr>
            <th>Category</th>
            <th>Budget Amount ($)</th>
          </tr>
        </thead>
        <tbody>
          {% for cat in categories %}
          <tr>
            <td>{{ cat }}</td>
            <td>
              <input type="number" step="0.01"
                     name="budget_{{ cat }}"
                     value="{{ budget_map.get(cat, 0.0) }}">
            </td>
          </tr>
          {% endfor %}
        </tbody>
      </table>

      <button type="submit">Save Budgets</button>
    </form>

  </div>
</body>
</html>
"""


DEBT_TEMPLATE = """
<!doctype html>
<html>
<head>
<meta charset="utf-8">
<title>Debt Tracker</title>
<meta name="viewport" content="width=device-width, initial-scale=1">
<style>
body { font-family: system-ui; background:#f5f5f5; margin:0; padding:0; }
.container { max-width:800px; margin:auto; padding:16px; }
table { width:100%; border-collapse:collapse; background:#fff; }
th, td { padding:8px; border-bottom:1px solid #eee; }
th { background:#f0f0f0; }
form { background:#fff; padding:16px; border-radius:8px; margin-bottom:16px; }
input { width:100%; padding:8px; margin-bottom:8px; }
button { padding:10px; background:#007bff; color:white; border:none; border-radius:4px; cursor:pointer; }
</style>
</head>
<body>
<div class="container">

<h1>Debt Tracker</h1>

<form method="post">
<input name="name" placeholder="Debt Name" required>
<input name="original_balance" type="number" step="0.01" placeholder="Original Balance" required>
<input name="current_balance" type="number" step="0.01" placeholder="Current Balance" required>
<input name="interest_rate" type="number" step="0.01" placeholder="Interest Rate (%)" required>
<button type="submit">Add Debt</button>
</form>

<table>
<thead>
<tr>
<th>Name</th>
<th>Original</th>
<th>Current</th>
<th>APR</th>
<th>Weighted APR</th>
</tr>
</thead>
<tbody>
{% for d in debts %}
<tr>
<td>{{ d.name }}</td>
<td>${{ "%.2f"|format(d.original_balance) }}</td>
<td>${{ "%.2f"|format(d.current_balance) }}</td>
<td>{{ "%.2f"|format(d.interest_rate) }}%</td>
<td>{{ "%.2f"|format(d.weighted_apr) }}%</td>
</tr>
{% endfor %}
</tbody>
</table>

</div>
</body>
</html>
"""

ALLOCATE_TEMPLATE = """
<!doctype html>
<html>
<head>
<title>Allocate Paycheck</title>
<meta name="viewport" content="width=device-width, initial-scale=1">
<style>
body { font-family: system-ui; background:#f5f5f5; }
.container { max-width:700px; margin:auto; padding:16px; }
table { width:100%; border-collapse:collapse; background:#fff; }
th, td { padding:8px; border-bottom:1px solid #eee; }
th { background:#f0f0f0; }
input { width:100%; padding:8px; }
button { margin-top:16px; width:100%; padding:10px; background:#28a745; color:white; border:none; border-radius:4px; }
</style>
</head>
<body>
<div class="container">

<h1>Allocate Paycheck</h1>

<form method="post">
<table>
<thead><tr><th>Category</th><th>Amount</th></tr></thead>
<tbody>
{% for cat in categories %}
<tr>
<td>{{ cat }}</td>
<td><input type="number" step="0.01" name="alloc_{{ cat }}"></td>
</tr>
{% endfor %}
</tbody>
</table>
<button type="submit">Save Allocation</button>
</form>

</div>
</body>
</html>
"""

BALANCES_TEMPLATE = """
<!doctype html>
<html>
<head>
<title>Category Balances</title>
<meta name="viewport" content="width=device-width, initial-scale=1">
<style>
body { font-family: system-ui; background:#f5f5f5; }
.container { max-width:700px; margin:auto; padding:16px; }
table { width:100%; border-collapse:collapse; background:#fff; }
th, td { padding:8px; border-bottom:1px solid #eee; }
th { background:#f0f0f0; }
</style>
</head>
<body>
<div class="container">

<h1>Category Balances</h1>

<table>
<thead><tr><th>Category</th><th>Balance</th></tr></thead>
<tbody>
{% for cat, bal in balances.items() %}
<tr>
<td>{{ cat }}</td>
<td>${{ "%.2f"|format(bal) }}</td>
</tr>
{% endfor %}
</tbody>
</table>

</div>
</body>
</html>
"""
# ============================================================
#  DASH APP INITIALIZATION
# ============================================================

dash_app = Dash(
    __name__,
    server=app,
    url_base_pathname="/dashboard/",
    suppress_callback_exceptions=True
)

dash_app.layout = html.Div(
    style={"maxWidth": "900px", "margin": "0 auto", "padding": "16px"},
    children=[
        html.H2("Spending Dashboard"),
        html.Label("Select Month"),
        dcc.Dropdown(id="month-dropdown", options=[], value=None),
        html.Label("Select Category"),
        dcc.Dropdown(id="category-dropdown", options=[], value=None),
        html.H3("Spending by Category"),
        dcc.Graph(id="category-chart"),
        html.H3("Budget vs Actual"),
        dcc.Graph(id="budget-chart"),
        html.H3("Debt Progress"),
        dcc.Graph(id="debt-chart")
    ]
)

# ============================================================
#  DASH ACCESS CONTROL
# ============================================================

@dash_app.server.before_request
def protect_dash():
    if request.path.startswith("/dashboard") and not current_user.is_authenticated:
        return redirect(url_for("login"))

# ============================================================
#  DASH CALLBACKS
# ============================================================

@dash_app.callback(
    Output("month-dropdown", "options"),
    Output("category-dropdown", "options"),
    Input("month-dropdown", "id")
)
def load_dropdowns(_):
    if not current_user.is_authenticated:
        return [], []

    session = SessionLocal()
    try:
        dates = (
            session.query(Expense.created_at)
            .filter(Expense.user_id == current_user.id)
            .all()
        )
        months = sorted({dt.strftime("%Y-%m") for (dt,) in dates})
        return (
            [{"label": m, "value": m} for m in months],
            [{"label": c, "value": c} for c in DEFAULT_CATEGORIES]
        )
    finally:
        session.close()


@dash_app.callback(
    Output("category-chart", "figure"),
    Input("month-dropdown", "value"),
    Input("category-dropdown", "value")
)
def update_category_chart(month, category):
    if not month:
        return px.bar(title="Select a month")

    session = SessionLocal()
    try:
        start = datetime.strptime(month + "-01", "%Y-%m-%d")
        end = (start + timedelta(days=40)).replace(day=1)

        q = (
            session.query(Expense)
            .filter(Expense.user_id == current_user.id)
            .filter(Expense.created_at >= start, Expense.created_at < end)
        )
        df = pd.read_sql(q.statement, session.bind)

        if category:
            df = df[df["category"] == category]

        grouped = df.groupby("category")["amount"].sum().reset_index()

        return px.bar(grouped, x="category", y="amount", title="Spending by Category")
    finally:
        session.close()


@dash_app.callback(
    Output("budget-chart", "figure"),
    Input("month-dropdown", "value")
)
def update_budget_chart(month):
    if not month:
        return px.bar(title="Select a month")

    session = SessionLocal()
    try:
        start = datetime.strptime(month + "-01", "%Y-%m-%d")
        end = (start + timedelta(days=40)).replace(day=1)

        q_exp = (
            session.query(Expense)
            .filter(Expense.user_id == current_user.id)
            .filter(Expense.created_at >= start, Expense.created_at < end)
        )
        df_exp = pd.read_sql(q_exp.statement, session.bind)
        actual = df_exp.groupby("category")["amount"].sum().reset_index()

        q_bud = (
            session.query(Budget)
            .filter(Budget.user_id == current_user.id)
            .filter(Budget.month == month)
        )
        df_bud = pd.read_sql(q_bud.statement, session.bind)
        df_bud = df_bud.rename(columns={"amount": "budget"})

        merged = pd.merge(actual, df_bud, on="category", how="outer").fillna(0)

        return px.bar(
            merged,
            x="category",
            y=["amount", "budget"],
            barmode="group",
            title="Actual vs Budget"
        )
    finally:
        session.close()
    
@dash_app.callback(
    Output("debt-chart", "figure"),
    Input("month-dropdown", "id")
)
def update_debt_chart(_):
    session = SessionLocal()
    debts = session.query(Debt).filter(Debt.user_id == current_user.id).all()
    session.close()

    if not debts:
        return px.bar(title="No debts yet")

    df = pd.DataFrame([{
        "name": d.name,
        "paid": d.original_balance - d.current_balance,
        "outstanding": d.current_balance
    } for d in debts])

    return px.bar(
        df,
        x="name",
        y=["paid", "outstanding"],
        barmode="stack",
        title="Debt Paid vs Outstanding"
    )
# ============================================================
#  FLASK ROUTES
# ============================================================

@app.route("/login", methods=["GET", "POST"])
def login():
    if request.method == "POST":
        username = request.form.get("username", "").strip()
        password = request.form.get("password", "").strip()

        session = SessionLocal()
        try:
            user = session.query(User).filter(User.username == username).first()
            if user and user.check_password(password):
                login_user(user)
                return redirect(url_for("index"))
            return render_template_string(LOGIN_TEMPLATE, error="Invalid credentials")
        finally:
            session.close()

    return render_template_string(LOGIN_TEMPLATE, error=None)


@app.route("/logout")
@login_required
def logout():
    logout_user()
    return redirect(url_for("login"))


@app.route("/")
@login_required
def index():
    session = SessionLocal()
    try:
        expenses = (
            session.query(Expense)
            .filter(Expense.user_id == current_user.id)
            .order_by(Expense.created_at.desc())
            .all()
        )

        cutoff = datetime.utcnow() - timedelta(days=30)
        recent = (
            session.query(Expense)
            .filter(Expense.user_id == current_user.id)
            .filter(Expense.created_at >= cutoff)
            .all()
        )

        total_spent = sum(e.amount for e in recent)
        category_totals = {}
        for e in recent:
            category_totals[e.category] = category_totals.get(e.category, 0.0) + e.amount

    finally:
        session.close()

    editing_id = request.args.get("editing_id", type=int)

    return render_template_string(
        TEMPLATE,
        expenses=expenses,
        categories=DEFAULT_CATEGORIES,
        total_spent=total_spent,
        category_totals=category_totals,
        editing_id=editing_id
    )


@app.route("/add", methods=["POST"])
@login_required
def add_expense():
    amount_raw = request.form.get("amount", "").strip()
    category = request.form.get("category", "").strip()
    description = request.form.get("description", "").strip() or None

    try:
        amount = float(amount_raw)
    except ValueError:
        return redirect(url_for("index"))

    session = SessionLocal()
    try:
        exp = Expense(
            user_id=current_user.id,
            amount=amount,
            category=category,
            description=description,
            created_at=datetime.utcnow()
        )
        session.add(exp)
        session.commit()
    finally:
        session.close()

    return redirect(url_for("index"))


@app.route("/edit/start/<int:expense_id>", methods=["POST"])
@login_required
def start_edit_expense(expense_id):
    return redirect(url_for("index", editing_id=expense_id))


@app.route("/edit/<int:expense_id>", methods=["POST"])
@login_required
def edit_expense(expense_id):
    amount_raw = request.form.get("amount", "").strip()
    category = request.form.get("category", "").strip()
    description = request.form.get("description", "").strip() or None

    try:
        amount = float(amount_raw)
    except ValueError:
        return redirect(url_for("index"))

    session = SessionLocal()
    try:
        exp = (
            session.query(Expense)
            .filter(Expense.id == expense_id, Expense.user_id == current_user.id)
            .first()
        )
        if exp:
            exp.amount = amount
            exp.category = category
            exp.description = description
            session.commit()
    finally:
        session.close()

    return redirect(url_for("index"))


@app.route("/delete/<int:expense_id>", methods=["POST"])
@login_required
def delete_expense(expense_id):
    session = SessionLocal()
    try:
        exp = (
            session.query(Expense)
            .filter(Expense.id == expense_id, Expense.user_id == current_user.id)
            .first()
        )
        if exp:
            session.delete(exp)
            session.commit()
    finally:
        session.close()

    return redirect(url_for("index"))

@app.route("/migrate")
def migrate():
    Base.metadata.create_all(engine)
    return "Migration complete"

@app.route("/admin/create_user", methods=["GET", "POST"])
@login_required
def admin_create_user():
    if not current_user.is_admin:
        return "Unauthorized", 403

    session = SessionLocal()
    message = None

    if request.method == "POST":
        username = request.form.get("username", "").strip()
        password = request.form.get("password", "").strip()

        existing = session.query(User).filter(User.username == username).first()
        if existing:
            message = "User already exists."
        else:
            new_user = User(username=username, is_admin=0)
            new_user.set_password(password)
            session.add(new_user)
            session.commit()
            message = "User created successfully."

    session.close()

    return render_template_string(ADMIN_CREATE_USER_TEMPLATE, message=message)


@app.route("/debts", methods=["GET", "POST"])
@login_required
def manage_debts():
    session = SessionLocal()

    if request.method == "POST":
        name = request.form.get("name")
        original = float(request.form.get("original_balance"))
        current = float(request.form.get("current_balance"))
        rate = float(request.form.get("interest_rate"))

        debt = Debt(
            user_id=current_user.id,
            name=name,
            original_balance=original,
            current_balance=current,
            interest_rate=rate
        )
        session.add(debt)
        session.commit()

    debts = session.query(Debt).filter(Debt.user_id == current_user.id).all()
    session.close()

    return render_template_string(DEBT_TEMPLATE, debts=debts)

@app.route("/allocate", methods=["GET", "POST"])
@login_required
def allocate_paycheck():
    session = SessionLocal()

    if request.method == "POST":
        for cat in DEFAULT_CATEGORIES:
            raw = request.form.get(f"alloc_{cat}", "").strip()
            if not raw:
                continue

            amount = float(raw)

            alloc = Allocation(
                user_id=current_user.id,
                category=cat,
                amount=amount
            )
            session.add(alloc)

        session.commit()

    session.close()

    return render_template_string(ALLOCATE_TEMPLATE, categories=DEFAULT_CATEGORIES)
# ============================================================
#  BUDGET PAGE ROUTE
# ============================================================

@app.route("/budgets", methods=["GET", "POST"])
@login_required
def manage_budgets():
    session = SessionLocal()

    selected_month = request.args.get("month")
    if not selected_month:
        selected_month = datetime.utcnow().strftime("%Y-%m")

    if request.method == "POST":
        for cat in DEFAULT_CATEGORIES:
            field_name = f"budget_{cat}"
            raw_val = request.form.get(field_name, "").strip()

            try:
                amount = float(raw_val) if raw_val else 0.0
            except ValueError:
                amount = 0.0

            existing = (
                session.query(Budget)
                .filter(
                    Budget.user_id == current_user.id,
                    Budget.category == cat,
                    Budget.month == selected_month
                )
                .first()
            )

            if existing:
                existing.amount = amount
            else:
                new_bud = Budget(
                    user_id=current_user.id,
                    category=cat,
                    month=selected_month,
                    amount=amount
                )
                session.add(new_bud)

        session.commit()

    budgets = (
        session.query(Budget)
        .filter(
            Budget.user_id == current_user.id,
            Budget.month == selected_month
        )
        .all()
    )

    session.close()

    budget_map = {b.category: b.amount for b in budgets}

    return render_template_string(
        BUDGET_TEMPLATE,
        categories=DEFAULT_CATEGORIES,
        selected_month=selected_month,
        budget_map=budget_map
    )

@app.route("/balances")
@login_required
def view_balances():
    session = SessionLocal()

    # Total allocated per category
    allocs = (
        session.query(Allocation.category, func.sum(Allocation.amount))
        .filter(Allocation.user_id == current_user.id)
        .group_by(Allocation.category)
        .all()
    )
    alloc_map = {cat: amt for cat, amt in allocs}

    # Total spent per category
    spent = (
        session.query(Expense.category, func.sum(Expense.amount))
        .filter(Expense.user_id == current_user.id)
        .group_by(Expense.category)
        .all()
    )
    spent_map = {cat: amt for cat, amt in spent}

    # Compute balances
    balances = {}
    for cat in DEFAULT_CATEGORIES:
        a = alloc_map.get(cat, 0)
        s = spent_map.get(cat, 0)
        balances[cat] = a - s

    session.close()

    return render_template_string(BALANCES_TEMPLATE, balances=balances)
# ============================================================
#  ADMIN: CREATE INITIAL ADMIN USER
# ============================================================

@app.route("/create_initial_admin")
def create_initial_admin():
    session = SessionLocal()
    try:
        existing = session.query(User).filter(User.username == "shawn").first()
        if existing:
            return "Admin already exists."

        user = User(username="shawn", is_admin=1)
        user.set_password("change_this_password")
        session.add(user)
        session.commit()
    finally:
        session.close()

    return "Admin 'shawn' created. Change the password immediately."


###Unsure where to go
#@property
#def weighted_apr(self):
#    if self.original_balance == 0:
#        return 0
#    return self.interest_rate * (self.current_balance / self.original_balance)
# ============================================================
#  RUN APP
# ============================================================

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=5000, debug=True)
