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
import re

from pathlib import Path

app = Flask(__name__)
app.secret_key = 'COMP636 S2'

start_date = datetime(2024,10,29)
pasture_growth_rate = 65    # kg DM/ha/day
stock_consumption_rate = 14  # kg DM/animal/day

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
       
    cursor = db_connection.cursor(dictionary=True, buffered=False)
    return cursor

def get_date():
    cursor = getCursor()        
    cursor.execute("SELECT curr_date FROM curr_date")        
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
        SELECT m.name, p.name AS paddock_name
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
        SELECT 
            p.*,
            m.name AS mob_name,
            COALESCE(s.stock_count, 0) AS stock_count
        FROM paddocks p
        LEFT JOIN mobs m ON p.id = m.paddock_id
        LEFT JOIN (
            SELECT mob_id, COUNT(*) as stock_count 
            FROM stock 
            GROUP BY mob_id
        ) s ON m.id = s.mob_id
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
            s.id AS stock_id,                    
            s.dob,                               
            s.weight,
            COUNT(*) OVER (PARTITION BY m.id) as stock_count,
            AVG(s.weight) OVER (PARTITION BY m.id) as avg_weight
        FROM mobs m
        JOIN paddocks p ON m.paddock_id = p.id
        LEFT JOIN stock s ON m.id = s.mob_id
        ORDER BY m.name, s.id
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
            SET p.total_dm = p.total_dm + (p.area * %s) - COALESCE(s.stock_count * %s, 0),
                p.dm_per_ha = p.total_dm / p.area""", (pasture_growth_rate, stock_consumption_rate))
        
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
            # Get mob and paddock details and perform move in one transaction
            try:
                cursor.execute("""
                    SELECT m.name as mob_name, 
                           p_old.name as old_paddock, 
                           p_new.name as new_paddock
                    FROM mobs m 
                    JOIN paddocks p_old ON m.paddock_id = p_old.id
                    JOIN paddocks p_new ON p_new.id = %s
                    WHERE m.id = %s
                """, (new_paddock_id, mob_id))
                move_details = cursor.fetchone()
                
                cursor.execute("UPDATE mobs SET paddock_id = %s WHERE id = %s", (new_paddock_id, mob_id))
                db_connection.commit()
                flash(f"{move_details['mob_name']} successfully moved from {move_details['old_paddock']} to {move_details['new_paddock']}.", "success")
            except mysql.connector.Error as err:
                db_connection.rollback()
                flash(f"Failed to move mob: {err}", "error")
        return redirect(url_for('mobs'))
    
    # GET request: show the form and current distribution
    cursor.execute("SELECT id, name FROM mobs")
    mobs = cursor.fetchall()
    
    cursor.execute("""
        SELECT id, name 
        FROM paddocks 
        WHERE id NOT IN (SELECT paddock_id FROM mobs WHERE paddock_id IS NOT NULL)
    """)
    available_paddocks = cursor.fetchall()
    
    cursor.execute("""
        SELECT 
            p.name AS paddock_name,
            p.dm_per_ha,
            m.name AS mob_name,
            COUNT(s.id) AS stock_count
        FROM paddocks p
        LEFT JOIN mobs m ON p.id = m.paddock_id
        LEFT JOIN stock s ON m.id = s.mob_id
        GROUP BY p.name, p.dm_per_ha, m.name
        ORDER BY p.name
    """)
    current_distribution = cursor.fetchall()

    return render_template(
        "move_mob.html", 
        mobs=mobs, 
        paddocks=available_paddocks,
        current_distribution=current_distribution
    )

@app.route("/add_paddock", methods=['GET', 'POST'])
def add_paddock():
    cursor = getCursor()
    
    if request.method == 'POST':
        name = request.form['name']
        try:
            area = float(request.form['area'])
            dm_per_ha = float(request.form['dm_per_ha'])
            total_dm = area * dm_per_ha if area > 0 and dm_per_ha > 0 else 0
        except ValueError:
            area = 0
            dm_per_ha = 0
            total_dm = 0

        form_data = {
            'name': name,
            'area': request.form['area'],
            'dm_per_ha': request.form['dm_per_ha'],
            'total_dm': total_dm
        }
        
        # Get next paddock ID
        cursor.execute("SELECT MAX(id) as next_id FROM paddocks")
        result = cursor.fetchone()
        next_id = result['next_id'] + 1 if result['next_id'] else 1
        form_data['id'] = next_id

        # Validate paddock name format
        if not re.match(r'^[a-zA-Z]+[a-zA-Z0-9\s]*$', name.strip()):
            flash("Paddock name must start with a letter and can only contain letters, numbers and spaces.", "error")
            return render_template("add_edit_paddock.html", paddock=form_data)

        # Check if paddock name already exists
        cursor.execute("SELECT name FROM paddocks WHERE BINARY name = %s", (name,))
        existing_paddock = cursor.fetchone()
        if existing_paddock:
            flash(f"Cannot add paddock. A paddock named '{name}' already exists.", "error")
            return render_template("add_edit_paddock.html", paddock=form_data)

        try:
            if area <= 0 or dm_per_ha <= 0:
                raise ValueError("Area and DM per ha must be positive numbers")

            cursor.execute("""
                INSERT INTO paddocks (name, area, dm_per_ha, total_dm)
                VALUES (%s, %s, %s, %s)
            """, (name, area, dm_per_ha, total_dm))
            db_connection.commit()
            flash("New paddock added successfully.", "success")
        except ValueError as e:
            flash(str(e), "error")
            return render_template("add_edit_paddock.html", paddock=form_data)
        except mysql.connector.Error as err:
            db_connection.rollback()
            flash(f"Failed to add new paddock: {err}", "error")
            return render_template("add_edit_paddock.html", paddock=form_data)
        return redirect(url_for('paddocks'))

    # GET request: show the form
    cursor.execute("SELECT MAX(id) as next_id FROM paddocks")
    result = cursor.fetchone()
    next_id = result['next_id'] + 1 if result['next_id'] else 1
    return render_template("add_edit_paddock.html", paddock={'id': next_id})

@app.route("/edit_paddock/<int:id>", methods=['GET', 'POST'])
def edit_paddock(id):
    cursor = getCursor()
    if request.method == 'POST':
        name = request.form['name']
        try:
            area = float(request.form['area'])
            dm_per_ha = float(request.form['dm_per_ha'])
            total_dm = area * dm_per_ha if area > 0 and dm_per_ha > 0 else 0
        except ValueError:
            area = 0
            dm_per_ha = 0
            total_dm = 0

        form_data = {
            'id': id,
            'name': name,
            'area': request.form['area'],
            'dm_per_ha': request.form['dm_per_ha'],
            'total_dm': total_dm
        }

        # Validate paddock name format
        if not re.match(r'^[a-zA-Z]+(?:\s?\d+)?$', name.strip()):
            flash("Paddock name must start with letters and can optionally include numbers at the end (e.g., 'Barn' or 'Barn 11' or 'Barn11').", "error")
            return render_template("add_edit_paddock.html", paddock=form_data)

        # Get current paddock data
        cursor.execute("SELECT * FROM paddocks WHERE id = %s", (id,))
        current_paddock = cursor.fetchone()

        # Check if any changes were made
        try:
            if area <= 0 or dm_per_ha <= 0:
                raise ValueError("Area and DM per ha must be positive numbers")

            # Compare current and new values
            if (name == current_paddock['name'] and 
                abs(float(area) - float(current_paddock['area'])) < 0.01 and 
                abs(float(dm_per_ha) - float(current_paddock['dm_per_ha'])) < 0.01):
                return redirect(url_for('paddocks'))

            # Check if new name (if changed) already exists
            if name != current_paddock['name']:
                cursor.execute("SELECT name FROM paddocks WHERE BINARY name = %s AND id != %s", (name, id))
                existing_paddock = cursor.fetchone()
                if existing_paddock:
                    flash(f"Cannot update paddock. A paddock named '{name}' already exists.", "error")
                    return render_template("add_edit_paddock.html", paddock=form_data)

            # Update paddock if changes were made
            cursor.execute("""
                UPDATE paddocks
                SET name = %s, area = %s, dm_per_ha = %s, total_dm = %s
                WHERE id = %s
            """, (name, area, dm_per_ha, total_dm, id))
            db_connection.commit()
            flash("Paddock updated successfully.", "success")

        except ValueError as e:
            flash(str(e), "error")
            return render_template("add_edit_paddock.html", paddock=form_data)
        except mysql.connector.Error as err:
            db_connection.rollback()
            flash(f"Failed to update paddock: {err}", "error")
            return render_template("add_edit_paddock.html", paddock=form_data)
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