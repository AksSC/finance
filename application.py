import os

from cs50 import SQL
from flask import Flask, flash, redirect, render_template, request, session
from flask_session import Session
from tempfile import mkdtemp
from werkzeug.exceptions import default_exceptions, HTTPException, InternalServerError
from werkzeug.security import check_password_hash, generate_password_hash

from helpers import apology, login_required, lookup, usd

# Configure application
app = Flask(__name__)

# Ensure templates are auto-reloaded
app.config["TEMPLATES_AUTO_RELOAD"] = True


# Ensure responses aren't cached
@app.after_request
def after_request(response):
    response.headers["Cache-Control"] = "no-cache, no-store, must-revalidate"
    response.headers["Expires"] = 0
    response.headers["Pragma"] = "no-cache"
    return response


# Custom filter
app.jinja_env.filters["usd"] = usd

# Configure session to use filesystem (instead of signed cookies)
app.config["SESSION_PERMANENT"] = False
app.config["SESSION_TYPE"] = "filesystem"
Session(app)

# Configure CS50 Library to use SQLite database
db = SQL("sqlite:///finance.db")

# Make sure API key is set
if not os.environ.get("API_KEY"):
    raise RuntimeError("API_KEY not set")


@app.route("/")
@login_required
def index():
    cash = db.execute("SELECT cash FROM users WHERE id = ?", session["user_id"])
    stocks = db.execute("SELECT symbol, SUM(shares) as shares, operation FROM stocks WHERE userID = ? GROUP BY symbol HAVING (SUM(shares)) > 0;", session["user_id"])
    total_stocks = 0

    for stock in stocks:
        quote = lookup(stock["symbol"])
        stock["name"] = quote["name"]
        stock["price"] = quote["price"]
        stock["total"] = stock["price"]*stock["shares"]
        total_stocks = total_stocks + stock["total"]

    total_cash = total_stocks + cash[0]["cash"]
    return render_template("index.html", stocks=stocks, cash=cash[0], total_cash=total_cash)

@app.route("/buy", methods=["GET", "POST"])
@login_required
def buy():
    if request.method == "POST":
        quote = lookup(request.form.get("symbol"))
        shares = request.form.get("shares")

        if quote is None:
            return apology("Must provide valid symbol", 400)
        elif not shares:
            return apology("Must provide number of shares", 400)
        try:
            shares = int(shares)
        except:
            return apology("Must provide valid number of shares", 400)


        if shares < 1:
            return apology("Must provide positive number of shares", 400)
        else:
            cash = db.execute("SELECT cash FROM users WHERE id = ?", session["user_id"])[0]["cash"]
            price = shares*quote["price"]
            if price > cash:
                return apology("Insufficient cash", 400)
            else:
                db.execute("UPDATE users SET cash = cash - ? WHERE id = ?", price, session["user_id"])
                db.execute("INSERT INTO stocks (userID, symbol, shares, price, operation) VALUES (?, ?, ?, ?, ?)", session["user_id"], quote["symbol"].upper(), shares, quote["price"], "buy")

                flash("Transaction successful")
                return redirect("/")

    else:
        return render_template("buy.html")


@app.route("/history")
@login_required
def history():
    """Show history of transactions"""
    stocks = db.execute("SELECT * FROM stocks WHERE userID = ?", session["user_id"])
    return render_template("history.html", stocks=stocks)


@app.route("/login", methods=["GET", "POST"])
def login():
    """Log user in"""

    # Forget any user_id
    session.clear()

    # User reached route via POST (as by submitting a form via POST)
    if request.method == "POST":

        # Ensure username was submitted
        if not request.form.get("username"):
            return apology("must provide username", 403)

        # Ensure password was submitted
        elif not request.form.get("password"):
            return apology("must provide password", 403)

        # Query database for username
        rows = db.execute("SELECT * FROM users WHERE username = ?", request.form.get("username"))

        # Ensure username exists and password is correct
        if len(rows) != 1 or not check_password_hash(rows[0]["hash"], request.form.get("password")):
            return apology("invalid username and/or password", 403)

        # Remember which user has logged in
        session["user_id"] = rows[0]["id"]

        # Redirect user to home page
        return redirect("/")

    # User reached route via GET (as by clicking a link or via redirect)
    else:
        return render_template("login.html")


@app.route("/logout")
def logout():
    """Log user out"""

    # Forget any user_id
    session.clear()

    # Redirect user to login form
    return redirect("/")


@app.route("/quote", methods=["GET", "POST"])
@login_required
def quote():
    if request.method == "POST":
        quote = lookup(request.form.get("symbol"))
        if quote is None:
            return apology("Must provide valid symbol", 400)
        else:
            return render_template("quoted.html", name=quote["name"], symbol=quote["symbol"], price=quote["price"])
    # User clicked on a link(GET)
    else:
        return render_template("quote.html")


@app.route("/register", methods=["GET", "POST"])
def register():
    if request.method == "POST":
        username = request.form.get("username")
        password = request.form.get("password")
        confirmation = request.form.get("confirmation")

        rows = db.execute("SELECT * FROM users WHERE username = ?", username)

        if not username:
            return apology("Must provide Username", 400)
        elif len(rows) != 0:
            return apology("Username already exists", 400)
        elif not password:
            return apology("Must provide password", 400)
        elif not confirmation:
            return apology("Must provide confirmation for password", 400)
        elif password != confirmation:
            return apology("Passwords must match", 400)
        else:
            hash = generate_password_hash(password, method="pbkdf2:sha256", salt_length=8)

            db.execute("INSERT INTO users (username, hash) VALUES (?, ?)", username, hash)

            return redirect("/")

    else:
        return render_template("register.html")


@app.route("/sell", methods=["GET", "POST"])
@login_required
def sell():
    """Sell shares of stock"""
    if request.method == "POST":
        symbol = request.form.get("symbol")
        quote = lookup(symbol)
        shares = int(request.form.get("shares"))
        stocks = db.execute("SELECT SUM(shares) as shares FROM stocks WHERE userID = ? AND symbol = ?", session["user_id"], symbol)[0]

        if quote is None:
            return apology("Must provide valid symbol", 400)
        elif shares < 1:
            return apology("Must provide positive number of shares", 400)
        elif stocks["shares"] < shares:
            return apology("Too many shares", 400)
        else:
            value = quote["price"]*shares
            db.execute("INSERT INTO stocks (userID, symbol, shares, price, operation) VALUES (?, ?, ?, ?, ?)", session["user_id"], symbol.upper(), -shares, quote["price"], "sell")
            db.execute("UPDATE users SET cash = cash + ? WHERE id = ?", value, session["user_id"])
            flash("Sold!")
            return redirect("/")
    else:
        stocks = db.execute("SELECT symbol FROM stocks WHERE userID = ? GROUP BY symbol HAVING (SUM(shares)) > 0", session["user_id"])
        return render_template("sell.html", stocks=stocks)

@app.route("/change", methods=["GET", "POST"])
@login_required
def change():
    """Change Password"""
    if request.method == "POST":
        rows = db.execute("SELECT * FROM users WHERE id = ?", session["user_id"])
        current = request.form.get("current")
        new = request.form.get("new")
        confirmation = request.form.get("confirmation")

        if not current:
            return apology("Must provide current password", 400)
        elif not new:
            return apology("Must provide new password", 400)
        elif not confirmation:
            return apology("Must provide confirmation for new password", 400)
        elif not check_password_hash(rows[0]["hash"], current):
            return apology("Wrong password", 400)
        elif new != confirmation:
            return apology("New passwords don't match", 400)
        else:
            hash = generate_password_hash(new, method="pbkdf2:sha256", salt_length=8)
            db.execute("UPDATE users SET hash = ? WHERE id = ?", hash, session["user_id"])
            flash("Password updated!")
            return redirect("/")
    else:
        return render_template("change.html")

def errorhandler(e):
    """Handle error"""
    if not isinstance(e, HTTPException):
        e = InternalServerError()
    return apology(e.name, e.code)


# Listen for errors
for code in default_exceptions:
    app.errorhandler(code)(errorhandler)
