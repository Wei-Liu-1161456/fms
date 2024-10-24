from flask import Flask
from flask import render_template
from flask import request
from flask import redirect
from flask import url_for
from flask import session
from flask import flash
from datetime import date, datetime, timedelta
import mysql.connector
import connect

from pathlib import Path

app = Flask(__name__)
app.secret_key = 'COMP636 S2'

start_date = datetime(2024,10,29)
pasture_growth_rate = 65    # kg DM/ha/day
stock_consumption_rate = 14 # kg DM/animal/day

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
       
    cursor = db_connection.cursor(dictionary=True, buffered=False)  # use a dictionary cursor if you prefer
    return cursor

def get_date():
    cursor = getCursor()        
    qstr = "select curr_date from curr_date;"  
    cursor.execute(qstr)        
    curr_date = cursor.fetchone()['curr_date']        
    return curr_date

@app.route("/")
def home():
    """Renders the home page with the current date."""
    curr_date = get_date()
    return render_template("home.html", curr_date=curr_date)

@app.route("/mobs")
def mobs():
    """Retrieves all mobs with their associated paddock names and renders the mobs page."""
    cursor = getCursor()
    cursor.execute("""
        SELECT m.name, p.name AS paddock_name  # removed m.id
        FROM mobs m 
        JOIN paddocks p ON m.paddock_id = p.id 
        ORDER BY m.name
    """)
    mobs = cursor.fetchall()
    return render_template("mobs.html", mobs=mobs)

@app.route("/paddocks")
def paddocks():
    """Retrieves all paddocks with associated mob and stock information and renders the paddocks page."""
    cursor = getCursor()
    cursor.execute("""
        SELECT p.*, m.name AS mob_name, COUNT(s.id) AS stock_count
        FROM paddocks p
        LEFT JOIN mobs m ON p.id = m.paddock_id
        LEFT JOIN stock s ON m.id = s.mob_id
        GROUP BY p.id
        ORDER BY p.name
    """)
    paddocks = cursor.fetchall()
    return render_template("paddocks.html", paddocks=paddocks)

@app.route("/stock")
def stock():
    """
    Retrieves all stock (animals), grouped by mob, with mob details and animal details.
    Mobs are in alphabetical order, and animals are in ID order within each mob.
    """
    cursor = getCursor()
    cursor.execute("""
        SELECT 
            m.name AS mob_name, 
            p.name AS paddock_name,
            COUNT(s.id) AS stock_count,          -- Total count of animals in the mob
            AVG(s.weight) AS avg_weight,         -- Average weight of the mob
            s.id AS stock_id,                    -- Animal's stock ID
            s.dob,                               -- Animal's date of birth
            s.weight                             -- Animal's weight
        FROM mobs m
        JOIN paddocks p ON m.paddock_id = p.id
        LEFT JOIN stock s ON m.id = s.mob_id
        GROUP BY m.name, p.name, s.id, s.dob, s.weight  -- Group by mob and animal details
        ORDER BY m.name, s.id                        -- Order by mob name and then animal ID
    """)
    stock = cursor.fetchall()
    return render_template("stock.html", stock=stock, current_date=get_date())

@app.route("/next_day")
def next_day():
    """
    Advances the system to the next day, updating pasture levels and the current date.
    """
    cursor = getCursor()
    curr_date = get_date()
    new_date = curr_date + timedelta(days=1)
    
    try:
        # Update pasture levels
        cursor.execute("""
            UPDATE paddocks p
            LEFT JOIN mobs m ON p.id = m.paddock_id
            LEFT JOIN (SELECT mob_id, COUNT(*) as stock_count FROM stock GROUP BY mob_id) s ON m.id = s.mob_id
            SET p.total_dm = GREATEST(0, p.total_dm + (p.area * %s) - COALESCE(s.stock_count * %s, 0)),
                p.dm_per_ha = GREATEST(0, (p.total_dm + (p.area * %s) - COALESCE(s.stock_count * %s, 0)) / p.area)
        """, (pasture_growth_rate, stock_consumption_rate, pasture_growth_rate, stock_consumption_rate))
        
        # Update current date
        cursor.execute("UPDATE curr_date SET curr_date = %s", (new_date,))
        
        db_connection.commit()
        flash(f"Advanced to next day: {new_date.strftime('%d %B %Y')}", "success")
    except mysql.connector.Error as err:
        db_connection.rollback()
        flash(f"Failed to advance to next day: {err}", "error")
    
    return redirect(url_for('paddocks'))

@app.route("/reset")
def reset():
    """
    Resets the data to its original state using the SQL script in fms-reset.sql.
    """
    cursor = getCursor()
    THIS_FOLDER = Path(__file__).parent.resolve()
    try:
        with open(THIS_FOLDER / 'fms-reset.sql', 'r') as f:
            sql_script = f.read()
            for statement in sql_script.split(';'):
                if statement.strip():
                    cursor.execute(statement)
        db_connection.commit()
        current_date = get_date()
        flash(f"System has been reset to initial state. Current date is now {current_date.strftime('%d %B %Y')}.", "success")
    except Exception as e:
        db_connection.rollback()
        flash(f"Error resetting system: {str(e)}", "error")
    return redirect(url_for('paddocks'))

@app.route("/move_mob", methods=['GET', 'POST'])
def move_mob():
    """
    Handles the movement of a mob to a new paddock.
    GET: Displays the form for moving a mob.
    POST: Processes the form submission and moves the mob.
    """
    cursor = getCursor()
    if request.method == 'POST':
        mob_id = request.form['mob_id']
        new_paddock_id = request.form['new_paddock_id']
        
        # Check if the new paddock is empty
        cursor.execute("SELECT id FROM mobs WHERE paddock_id = %s", (new_paddock_id,))
        occupied = cursor.fetchone()
        if occupied:
            flash("Cannot move mob. The selected paddock is already occupied.", "error")
        else:
            # Move the mob
            try:
                cursor.execute("UPDATE mobs SET paddock_id = %s WHERE id = %s", (new_paddock_id, mob_id))
                db_connection.commit()
                flash("Mob moved successfully.", "success")
            except mysql.connector.Error as err:
                db_connection.rollback()
                flash(f"Failed to move mob: {err}", "error")
        return redirect(url_for('mobs'))
    
    # GET request: show the form
    cursor.execute("SELECT id, name FROM mobs")
    mobs = cursor.fetchall()
    cursor.execute("SELECT id, name FROM paddocks WHERE id NOT IN (SELECT paddock_id FROM mobs WHERE paddock_id IS NOT NULL)")
    available_paddocks = cursor.fetchall()
    return render_template("move_mob.html", mobs=mobs, paddocks=available_paddocks)

@app.route("/add_paddock", methods=['GET', 'POST'])
def add_paddock():
    """
    Handles the addition of a new paddock.
    GET: Displays the form for adding a new paddock.
    POST: Processes the form submission and adds the new paddock.
    """
    if request.method == 'POST':
        cursor = getCursor()
        name = request.form['name']
        try:
            area = float(request.form['area'])
            dm_per_ha = float(request.form['dm_per_ha'])
            if area <= 0 or dm_per_ha <= 0:
                raise ValueError("Area and DM per ha must be positive numbers")
            total_dm = area * dm_per_ha

            cursor.execute("""
                INSERT INTO paddocks (name, area, dm_per_ha, total_dm)
                VALUES (%s, %s, %s, %s)
            """, (name, area, dm_per_ha, total_dm))
            db_connection.commit()
            flash("New paddock added successfully.", "success")
        except ValueError as e:
            flash(str(e), "error")
        except mysql.connector.Error as err:
            db_connection.rollback()
            flash(f"Failed to add new paddock: {err}", "error")
        return redirect(url_for('paddocks'))

    return render_template("add_edit_paddock.html", paddock=None)

@app.route("/edit_paddock/<int:id>", methods=['GET', 'POST'])
def edit_paddock(id):
    """
    Handles the editing of an existing paddock.
    GET: Displays the form for editing a paddock.
    POST: Processes the form submission and updates the paddock.

    Args:
        id (int): The ID of the paddock to edit.
    """
    cursor = getCursor()
    if request.method == 'POST':
        name = request.form['name']
        try:
            area = float(request.form['area'])
            dm_per_ha = float(request.form['dm_per_ha'])
            if area <= 0 or dm_per_ha <= 0:
                raise ValueError("Area and DM per ha must be positive numbers")
            total_dm = area * dm_per_ha

            cursor.execute("""
                UPDATE paddocks
                SET name = %s, area = %s, dm_per_ha = %s, total_dm = %s
                WHERE id = %s
            """, (name, area, dm_per_ha, total_dm, id))
            db_connection.commit()
            flash("Paddock updated successfully.", "success")
        except ValueError as e:
            flash(str(e), "error")
        except mysql.connector.Error as err:
            db_connection.rollback()
            flash(f"Failed to update paddock: {err}", "error")
        return redirect(url_for('paddocks'))

    cursor.execute("SELECT * FROM paddocks WHERE id = %s", (id,))
    paddock = cursor.fetchone()
    if not paddock:
        flash("Paddock not found.", "error")
        return redirect(url_for('paddocks'))

    return render_template("add_edit_paddock.html", paddock=paddock)

@app.context_processor
def utility_processor():
    """
    Adds utility functions to the template context.
    """
    return dict(get_date=get_date)

if __name__ == '__main__':
    app.run(debug=True)