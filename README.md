# Farm Management Simulator Report

## Discuss design decisions

- **Task 1 : On every page, include a page header which includes: the name of the app, a navigation bar with links to the pages.**
    
    I added a move mob navigation item in the navigation bar. The reason for this is that when the user moves the mob, move mob is a distinct and independent page, which allows the user to clearly know his current location and the operation content. In this way, when the user operates the move mob, there will be a clear highlight in the navigation bar to remind the user of the location.
    
- **Task 2 : Add a picture and some (brief) introductory text to the home page.**
    
    This page takes into account the way the page expands and shrinks. The reason for this is that if the layout of the images and text is not responsive, the arrangement of the page content will become quite unclear when it expands and shrinks.
    
- **Task 3 : Modify the page on the /mobs route to show the paddock name that each mob is in and sort alphabetically by mob name.**
    
    The decision I made here is to remove the display of mob ID according to the assignment requirement that "ID numbers for table rows are mainly for internal system use only and should only be made visible to system users when mentioned in the requirements.”
    
- **Task 4 : Create a route to list the stock (animals), grouped by mob**
Here comes a problem that bothers me. The age of animal with ID 1005 always goes wrong when I move to next day. I used several versions to debug. At first, I used the age to two decimal places, hoping that it can be accurate to the movement of each day when moving to next day, but I found that there are still errors; later I adjusted the way to calculate age. Although it can achieve the change of 1005's age on 1/11/2024, from a logical point of view, it still does not accurately consider leap years and other issues. Finally, I import dateutil.relativedelta to solve this problem.
- **Task 5 : Create a route to list the paddocks**
The functions of this page are not difficult to implement. The main problem is how to make it easier for users to understand the content of the page when the interface is displayed. For example, I set the color changes of different DM/pa to yellow and red according to the homework requirements. For users, they may not be able to intuitively understand the meaning of colors, so I added additional explanations at the bottom.
- **Task 6: Create a route to so that a mob can be moved to any other available paddock.**
This is the part I modified the most. The main modification decisions include: Initially, I only implemented the move mob function. But I found a problem. When the user uses the move mob, he doesn't know which one needs to be moved first and which paddock to move to first. So I added a prompt at the top of the page to prompt which mobs are in Critical or Warning status. But I found another problem. This can only prompt which mob to move, but not which paddock to move. And if there are multiple mobs in Critical status, for example 10 mobs, 10 parallel messages will appear in the entire prompt bar, which is ugly. Although this will not appear under the current data volume, I still hope to consider this point. So after several modifications, I finally chose to display the consideration factor information of mob and paddock in full below to assist users in moving mob.
- **Task 7: Update the system so that paddocks can be edited and added by the user:**
    
  Firstly, constraining the naming of paddocks
    
    - Must start with a letter (e.g., "Barn", "Front")
    - Can optionally include a number at the end (e.g., "Barn11" or "Barn 11")
    - No special characters allowed
    - No leading or trailing spaces - to prevent the computer from thinking they are different names, but the human eye thinks they are the same name.
    - No multiple consecutive spaces - same as above
    - Case sensitivity (e.g., "Barn" and "barn" are considered different names) - to prevent the computer from thinking they are different names, but the human ear thinks they are the same name.
    - Names must be unique - to prevent the appearance of paddocks with the same name
    
    In this way, user naming standards are implemented to prevent the appearance of unnecessary garbled characters, such as a paddock named space is meaningless, you can't tell others "space paddock is running out of grass", which is weird and not in line with daily communication.

  Secondly, I limited the value of DM/pa to be greater than 1800 when modifying it, because here we consider the actual scenario, When users need to modify paddock, it must be because there is not enough grass. 1800 is the minimum healthy value of lawn. You can't modify paddock and deliberately adjust DM/PA to an unhealthy level. This is meaningless.
    
- **Task 8 : For each paddock, calculate pasture totals based on growth and consumption** 
Here I originally considered the accuracy of float calculations, so I made a modification to replace all floats with Decimals to handle the accuracy; but later I found that the data types stored in the database were all floats, so I changed them all back to float to keep the system consistent and prevent uncertain bugs.
In addition, according to the "Total DM calculated" in the "Edit paddocks Appropriate paddock details can be edited. Total DM calculated. 8" in the scoring requirements, I tried to display the Total DM information and calculation method to the scorer and the user, but I found that if I want to display it automatically in real time, I must use JavaScript. Otherwise, it can only be calculated after submission, but there is no point in modifying it in this way, because the user cannot see the real-time Total DM calculate information when entering, so I removed this part of the function

## Database Questions:

### **1. What SQL statement creates the mobs table and defines its fields/columns?**

```sql
CREATE TABLE mobs (
    id INT NOT NULL AUTO_INCREMENT,
    name VARCHAR(50) DEFAULT NULL,
    paddock_id INT NOT NULL,
    PRIMARY KEY (id),
    UNIQUE INDEX paddock_idx (paddock_id),
    CONSTRAINT fk_paddock FOREIGN KEY (paddock_id)
        REFERENCES paddocks (id)
        ON DELETE NO ACTION ON UPDATE NO ACTION
);
```

### **2. Which lines of SQL script set up the relationship between the mobs and paddocks tables?**

The following lines establish the foreign key relationship between mobs and paddocks:

```sql
CONSTRAINT fk_paddock FOREIGN KEY (paddock_id)
    REFERENCES paddocks (id)
    ON DELETE NO ACTION ON UPDATE NO ACTION
```

### **3. Write SQL script to create a new table called farms, which includes a unique farm ID, the farm name, an optional short description, and the owner’s name. The ID can be added automatically by the database. (Relationships to other tables not required.)**

```sql
CREATE TABLE farms (
    id INT NOT NULL AUTO_INCREMENT,
    name VARCHAR(100) NOT NULL,
    description TEXT,
    owner_name VARCHAR(100) NOT NULL,
    PRIMARY KEY (id)
);
```

### **4. Write an SQL statement to add details for an example farm to your new farms table, which would be suitable to include in your web application for the users to add farms in a future version. (Type in actual values, don’t use %s markers.)**

```sql
INSERT INTO farms (
    name,
    description,
    owner_name
) VALUES (
    "Fred Farm",
    "An awesome, vigorous dairy farm located in the countryside",
    "Fred Liu"
);
```

### **5. What changes would you need to make to other tables to incorporate the new farms table? (Describe the changes. SQL script not required.)**

To incorporate the farms table, the following adjustments could be made to existing tables:

- **Add a farm_id column:** Add a farm_id field to tables that need to be linked to specific farms, such as the paddocks, mobs, and stock tables. This field will allow each paddock, mob, and animal to be tied to a particular farm.
- **Set up foreign keys:** Create foreign key relationships that link the farm_id in these tables to farms.id, ensuring that paddocks, mobs, and animals are directly associated with a specific farm. This setup makes it clear which farm each paddock, mob, or animal belongs to.
- **Update queries:** Adjust any queries in the application to filter by farm_id.

## Image References: 

Kaszuba, J. (2020, June 11). *Cow dairy cow animal livestock* [Photograph]. 
    Pixabay. [https://pixabay.com/photos/cow-dairy-cow-animal-livestock-5287350/](https://pixabay.com/photos/cow-dairy-cow-animal-livestock-5287350/)
