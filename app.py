from flask import Flask, render_template, request, redirect, url_for, session, flash
from datetime import date, datetime, timedelta
import mysql.connector
import connect
import re
from pathlib import Path
from dateutil.relativedelta import relativedelta

app = Flask(__name__)
app.secret_key = 'COMP636 S2'

# Global constants
START_DATE = datetime(2024, 10, 29)
PASTURE_GROWTH_RATE = 65    # kg DM/ha/day - Daily pasture dry matter growth rate
STOCK_CONSUMPTION_RATE = 14  # kg DM/animal/day - Daily animal consumption of dry matter

# Database connection singleton
db_connection = None

def getCursor():
    """
    Gets a new dictionary cursor for the database connection.
    Creates a new connection if none exists or if the existing one is disconnected.
    
    Returns:
        mysql.connector.cursor: A dictionary cursor for database operations
    """
    global db_connection
 
    if db_connection is None or not db_connection.is_connected():
        db_connection = mysql.connector.connect(
            user=connect.dbuser,
            password=connect.dbpass, 
            host=connect.dbhost,
            database=connect.dbname, 
            autocommit=True
        )
       
    return db_connection.cursor(dictionary=True, buffered=False)

def get_date():
    """
    Retrieves the current system date from the database.
    
    Returns:
        datetime: Current system date
    """
    cursor = getCursor()        
    cursor.execute("SELECT curr_date FROM curr_date")        
    return cursor.fetchone()['curr_date']

def validate_paddock_name(name, id=None):
    """
    Validates paddock name format and uniqueness.
    
    Rules:
    1. Must start with one or more letters
    2. Can optionally end with numbers (with or without a single space before numbers)
    3. Cannot have leading or trailing spaces
    4. Cannot have multiple consecutive spaces
    5. Cannot contain special characters
    6. Name must be unique (case sensitive)
    
    Examples:
    Valid: "Bar", "Bar11", "Bar 11"
    Invalid: "Bar-", ".Bar", "Bar.", "11Bar", "Bar  11", " Bar", "Bar "
    
    Args:
        name (str): Paddock name to validate
        id (int, optional): Paddock ID for edit operations
        
    Returns:
        tuple: (bool, str) - (is_valid, error_message)
    """
    cursor = getCursor()
    
    # Remove leading and trailing spaces and check if multiple spaces exist
    cleaned_name = name.strip()
    if cleaned_name != name:
        return False, "Paddock name cannot have leading or trailing spaces."
    
    if "  " in name:  # Check for multiple consecutive spaces
        return False, "Paddock name cannot contain multiple consecutive spaces."
    
    # Validate format: must start with letters, can only end with optional numbers
    if not re.match(r'^[a-zA-Z]+(?:\s?\d+)?$', cleaned_name):
        return False, "Paddock name must start with letters and can optionally include numbers at the end."
    
    # Check name uniqueness (case sensitive)
    query = "SELECT name FROM paddocks WHERE BINARY name = %s"
    params = [cleaned_name]
    if id:
        query += " AND id != %s"
        params.append(id)
        
    cursor.execute(query, tuple(params))
    if cursor.fetchone():
        return False, f"A paddock named '{cleaned_name}' already exists."
        
    return True, ""

@app.route("/")
def home():
    """Renders the home page with current date."""
    return render_template("home.html", curr_date=get_date())

@app.route("/mobs")
def mobs():
    """
    Displays all mobs with their associated paddock names.
    SQL: Joins mobs and paddocks tables to show which paddock each mob is in.
    """
    cursor = getCursor()
    cursor.execute("""
        -- Get mob names and their current paddock locations
        SELECT m.name, p.name AS paddock_name
        FROM mobs m 
        JOIN paddocks p ON m.paddock_id = p.id 
        ORDER BY m.name
    """)
    return render_template("mobs.html", mobs=cursor.fetchall())

@app.route("/paddocks")
def paddocks():
    """
    Displays all paddocks with associated mob and stock information.
    SQL: Complex join to get paddock details, mob names, and stock counts.
    """
    cursor = getCursor()
    cursor.execute("""
        -- Get paddock details with mob and stock count information
        SELECT 
            p.*,
            m.name AS mob_name,
            COALESCE(s.stock_count, 0) AS stock_count
        FROM paddocks p
        LEFT JOIN mobs m ON p.id = m.paddock_id
        LEFT JOIN (
            -- Subquery to count animals in each mob
            SELECT mob_id, COUNT(*) as stock_count 
            FROM stock 
            GROUP BY mob_id
        ) s ON m.id = s.mob_id
        ORDER BY p.name
    """)
    return render_template("paddocks.html", paddocks=cursor.fetchall())

@app.route("/stock")
def stock():
    """
    Displays all stock grouped by mob, including mob details and animal statistics.
    Orders mobs alphabetically and animals by ID within each mob.
    SQL: Complex join with window functions for aggregate calculations.
    """
    cursor = getCursor()
    current_date = get_date()
    
    cursor.execute("""
        -- Get detailed stock information with mob statistics
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
    
    stock_data = cursor.fetchall()
    
    # Calculate exact age for each animal using relativedelta
    for animal in stock_data:
        if animal['dob']:
            dob = animal['dob']
            age = relativedelta(current_date, dob)
            animal['exact_age'] = f"{age.years} years, {age.months} months, {age.days} days"
            animal['age'] = age.years  # Store only complete years
            
    return render_template("stock.html", stock=stock_data, current_date=current_date)
    
@app.route("/next_day")
def next_day():
    """
    Advances the system date by one day and updates pasture levels.
    Takes into account pasture growth and stock consumption.
    SQL: Updates paddock DM levels based on growth rate and stock consumption.
    """
    cursor = getCursor()
    curr_date = get_date()
    new_date = curr_date + timedelta(days=1)
    
    try:
        # Update pasture levels based on growth and consumption
        cursor.execute("""
            -- Update paddock dry matter levels
            UPDATE paddocks p
            LEFT JOIN mobs m ON p.id = m.paddock_id
            LEFT JOIN (
                -- Calculate total animals per mob
                SELECT mob_id, COUNT(*) as stock_count 
                FROM stock 
                GROUP BY mob_id
            ) s ON m.id = s.mob_id
            SET p.total_dm = p.total_dm + (p.area * %s) - COALESCE(s.stock_count * %s, 0),
                p.dm_per_ha = p.total_dm / p.area
        """, (PASTURE_GROWTH_RATE, STOCK_CONSUMPTION_RATE))
        
        # Update system date
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
    Resets the system to its initial state using fms-reset.sql script.
    Executes SQL statements from the reset script sequentially.
    """
    cursor = getCursor()
    try:
        with open(Path(__file__).parent.resolve() / 'fms-reset.sql', 'r') as f:
            for statement in f.read().split(';'):
                if statement.strip():
                    cursor.execute(statement)
        db_connection.commit()
        flash(f"System has been reset to initial state. Current date is now {get_date().strftime('%d %B %Y')}.", "success")
    except Exception as e:
        db_connection.rollback()
        flash(f"Error resetting system: {str(e)}", "error")
    return redirect(url_for('paddocks'))

@app.route("/move_mob", methods=['GET', 'POST'])
def move_mob():
    """
    Handles mob movement between paddocks.
    GET: Shows the movement form with available paddocks
    POST: Processes the movement request and updates database
    SQL: Multiple queries to verify paddock availability and perform move
    """
    cursor = getCursor()
    if request.method == 'POST':
        mob_id = request.form['mob_id']
        new_paddock_id = request.form['new_paddock_id']
        
        # Verify paddock availability
        cursor.execute("SELECT id FROM mobs WHERE paddock_id = %s", (new_paddock_id,))
        if cursor.fetchone():
            flash("Cannot move mob. Selected paddock is already occupied.", "error")
        else:
            try:
                # Get movement details and perform move
                cursor.execute("""
                    -- Get details for move confirmation message
                    SELECT m.name as mob_name, 
                           p_old.name as old_paddock, 
                           p_new.name as new_paddock
                    FROM mobs m 
                    JOIN paddocks p_old ON m.paddock_id = p_old.id
                    JOIN paddocks p_new ON p_new.id = %s
                    WHERE m.id = %s
                """, (new_paddock_id, mob_id))
                move_details = cursor.fetchone()
                
                cursor.execute("UPDATE mobs SET paddock_id = %s WHERE id = %s", 
                             (new_paddock_id, mob_id))
                db_connection.commit()
                flash(f"{move_details['mob_name']} moved from {move_details['old_paddock']} "
                      f"to {move_details['new_paddock']}.", "success")
            except mysql.connector.Error as err:
                db_connection.rollback()
                flash(f"Failed to move mob: {err}", "error")
        return redirect(url_for('paddocks'))  
    
    # Prepare data for move_mob form
    cursor.execute("SELECT id, name FROM mobs")
    mobs = cursor.fetchall()
    
    cursor.execute("""
        -- Get list of available (unoccupied) paddocks
        SELECT id, name 
        FROM paddocks 
        WHERE id NOT IN (SELECT paddock_id FROM mobs WHERE paddock_id IS NOT NULL)
    """)
    available_paddocks = cursor.fetchall()
    
    cursor.execute("""
        -- Get current distribution of mobs and paddocks
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
    """
    Handles paddock addition.
    GET: Shows the add form
    POST: Processes the add request with input validation
    SQL: Inserts new paddock with calculated total dry matter
    """
    cursor = getCursor()
    
    if request.method == 'POST':
        name = request.form['name']
        try:
            # Convert string inputs to float and round to 2 decimal places
            area = round(float(request.form['area']), 2)
            dm_per_ha = round(float(request.form['dm_per_ha']), 2)
            total_dm = round(area * dm_per_ha, 2)
            
            # Validate input values
            if area <= 0 or dm_per_ha <= 0:
                raise ValueError("Area and Dry Matter per hectare must be positive numbers")
                
            # Validate paddock name
            is_valid, error_message = validate_paddock_name(name)
            if not is_valid:
                flash(error_message, "error")
                return render_template("add_edit_paddock.html", 
                                    paddock={'name': name, 
                                            'area': str(area), 
                                            'dm_per_ha': str(dm_per_ha)})
            
            cursor.execute("""
                -- Insert new paddock with calculated total dry matter
                INSERT INTO paddocks (name, area, dm_per_ha, total_dm)
                VALUES (%s, %s, %s, %s)
            """, (name, area, dm_per_ha, total_dm))
            db_connection.commit()
            flash(f"Paddock '{name}' added successfully.", "success")
            return redirect(url_for('paddocks'))
            
        except ValueError as e:
            flash(str(e), "error")
            return render_template("add_edit_paddock.html", 
                                paddock={'name': name, 
                                        'area': request.form['area'], 
                                        'dm_per_ha': request.form['dm_per_ha']})
        except mysql.connector.Error as err:
            db_connection.rollback()
            flash(f"Failed to add paddock: {err}", "error")
            return redirect(url_for('paddocks'))
    
    return render_template("add_edit_paddock.html")

@app.route("/edit_paddock/<int:id>", methods=['GET', 'POST'])
def edit_paddock(id):
    """
    Handles paddock editing.
    GET: Shows the edit form with current paddock data
    POST: Processes the edit request with validation
    SQL: Updates paddock data only if changes were made
    
    Args:
        id (int): Paddock ID to edit
    """
    cursor = getCursor()
    
    if request.method == 'POST':
        name = request.form['name']
        try:
            # Convert string inputs to float and round to 2 decimal places
            area = round(float(request.form['area']), 2)
            dm_per_ha = round(float(request.form['dm_per_ha']), 2)
            total_dm = round(area * dm_per_ha, 2) if area > 0 and dm_per_ha > 0 else 0
            
            if area <= 0 or dm_per_ha <= 0:
                raise ValueError("Area and DM per ha must be positive numbers")
            
            # Validate paddock name
            is_valid, error_message = validate_paddock_name(name, id)
            if not is_valid:
                flash(error_message, "error")
                return render_template("add_edit_paddock.html", 
                                    paddock={'id': id, 'name': name, 
                                            'area': str(area), 
                                            'dm_per_ha': str(dm_per_ha)})
            
            # Get current paddock data to check for changes
            cursor.execute("""
                -- Get current paddock data for comparison
                SELECT * FROM paddocks WHERE id = %s
            """, (id,))
            current_paddock = cursor.fetchone()
            
            # Convert current values to float for comparison
            current_area = round(float(current_paddock['area']), 2)
            current_dm_per_ha = round(float(current_paddock['dm_per_ha']), 2)
            
            # Check if any values have changed
            if (name == current_paddock['name'] and 
                area == current_area and 
                dm_per_ha == current_dm_per_ha):
                flash(f"No changes were made to paddock '{name}'.", "success")
                return redirect(url_for('paddocks'))
            
            # Update paddock if changes were made
            cursor.execute("""
                -- Update paddock with new values and recalculated total dry matter
                UPDATE paddocks
                SET name = %s, area = %s, dm_per_ha = %s, total_dm = %s
                WHERE id = %s
            """, (name, area, dm_per_ha, total_dm, id))
            db_connection.commit()
            flash(f"Paddock '{name}' updated successfully.", "success")
            return redirect(url_for('paddocks'))
            
        except ValueError as e:
            flash(str(e), "error")
            return render_template("add_edit_paddock.html", 
                                paddock={'id': id, 'name': name, 
                                        'area': request.form['area'], 
                                        'dm_per_ha': request.form['dm_per_ha']})
        except mysql.connector.Error as err:
            db_connection.rollback()
            flash(f"Failed to update paddock: {err}", "error")
    
    # Get existing paddock data for GET request
    cursor.execute("""
        -- Get paddock details for edit form
        SELECT * FROM paddocks WHERE id = %s
    """, (id,))
    paddock = cursor.fetchone()
    if not paddock:
        flash("Paddock not found.", "error")
        return redirect(url_for('paddocks'))
    
    return render_template("add_edit_paddock.html", paddock=paddock)

@app.context_processor
def utility_processor():
    """
    Adds utility functions to the template context.
    Makes get_date() function available in all templates.
    """
    return dict(get_date=get_date)

if __name__ == '__main__':
    app.run(debug=True)