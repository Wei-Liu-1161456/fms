from flask import Flask
from flask import render_template
from flask import request
from flask import redirect
from flask import url_for
from flask import session
from datetime import date, datetime, timedelta
import mysql.connector
import connect

####### Required for the reset function to work both locally and in PythonAnywhere
from pathlib import Path

app = Flask(__name__)
app.secret_key = 'COMP636 S2'

start_date = datetime(2024,10,29)
pasture_growth_rate = 65    #kg DM/ha/day
stock_consumption_rate = 14 #kg DM/animal/day

db_connection = None
 
def getCursor():
    """Gets a new dictionary cursor for the database.
    If necessary, a new database connection is created here and used for all
    subsequent to getCursor()."""
    global db_connection
 
    if db_connection is None or not db_connection.is_connected():
        db_connection = mysql.connector.connect(user=connect.dbuser, \
            password=connect.dbpass, host=connect.dbhost,
            database=connect.dbname, autocommit=True)
       
    cursor = db_connection.cursor(buffered=False)   # returns a list
    # cursor = db_connection.cursor(dictionary=True, buffered=False)  # use a dictionary cursor if you prefer
    return cursor

####### New function - reads the date from the new database table
def get_date():
    cursor = getCursor()        
    qstr = "select curr_date from curr_date;"  
    cursor.execute(qstr)        
    curr_date = cursor.fetchone()[0]        
    return curr_date

####### Updated if statement with this line
@app.route("/")
def home():
    # This line:
    curr_date = get_date()
    # Replaces these lines:
    # if 'curr_date' not in session:
    #     session.update({'curr_date': start_date})
    return render_template("home.html", curr_date=curr_date)

####### New function to reset the simulation back to the beginning - replaces reset_date() and clear_date()
##  NOTE: This requires fms-reset.sql file to be in the same folder as app.py
@app.route("/reset")
def reset():
    """Reset data to original state."""
    THIS_FOLDER = Path(__file__).parent.resolve()
    with open(THIS_FOLDER / 'fms-reset.sql', 'r') as f:
        mqstr = f.read()
        for qstr in mqstr.split(";"):
            cursor = getCursor()
            cursor.execute(qstr)
    get_date()
    return redirect(url_for('paddocks'))  

@app.route("/mobs")
def mobs():
    """List the mob details (excludes the stock in each mob)."""
    cursor = getCursor()        
    qstr = "select id, name from mobs;" 
    cursor.execute(qstr)        
    mobs = cursor.fetchall()        
    return render_template("mobs.html", mobs=mobs)  

@app.route("/paddocks")
def paddocks():
    """List paddock details."""
    return render_template("paddocks.html")  


