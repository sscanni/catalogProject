# Sports Catalog Website

## Project Overview

This is a Sport Catalog website application developed using Python, Flask, SQLAlchemy, HTML, CSS and Bootstrap. The website lets a user create sports categories and items within those categories. Categories and items can be changed and/or deleted once they have been created. Categories and items can only be modified or deleted by the user that created them. The information that is used in the program is stored in a SQLLite database. The program contains the following features:

* Reads and displays category and item information from a database.
* Includes forms to allow a user to add new categories and items.
* Includes forms to allow a user to update existing categories and items.
* Gives the user the ability to delete existing categories and items.
* Only allows create, update and delete functions only when a user is logged in otherwise the website functions as display only.
* The website implements a third party authentication and authorization service utilizing Google and Facebook accounts.
* The website provides a "login" and "logout" link on the navigation bar at the top of each page.
* The website provides the ability to assign an image to an item. The program will use the images that are placed in the "image" folder.
* The website provides a JSON endpoint that serves the category and item data from the database.

## Installation Instructions

* The program does not require any setup programs to be run prior to executing the website program for the first time.

* The files that are on Github should be downloaded into a directory. The required folder structures and files are already in place.

* The "image" folder contains some starter item images. To use additional new images on the website, new images should be uploaded to the server and placed in the "image" folder.

* A starter "catalog.db" database file is included and should be used.

## List of Program Files Included

* app.py - This is the main executable program
* models.py - This contains the database models
* client_secrets.json - contains the information for utilizing the Google authentication and authorization service.
* fb_client_secrets.json - contains the information for utilizing the Facebook authentication and authorization service.
* template folder - contains all of the HTML templates used by the program.
* static folder - contains the styles.css file and banner image.
* images folder - contains the item images that the web site displays.

## Design of the Code

The application consists of two Python files, app.py and models.py. App.py contains the endpoints for the website. The models.py contains the database table definition and models.

The app.py program contains the following endpoints:

* "/catalog.json/" - catalogJSON() function - serves json for the category and item information on the database.

* "/catalog/categories/" or "/" - showCategories() function - displays the main screen which displays all of the categories on the left and the seven most recently added items. Returns the categories.html template.

* "/catalog/_name_/items/" - showCategoryItems() function - where _name_ is the selected category name. Displays all of the items for the selected category.  For example, http://localhost:8000/catalog/Snowboarding/items. Returns the categories.html template.

* "/catalog/_category_/_item_" - showItem(category_name, item_name) function. Display a specific item within a category. For example, http://localhost:8000/catalog/Snowboarding/Snowboard. Returns the item.html template.

* "/catalog/item/new/" - newItem() function. Add a new item. Example, http://localhost:8000/catalog/item/new. Returns the newitem.html template.

* "/catalog/_category_/_item_/edit/" - editItem(category_name, item_name) function. Edit an item. Example, http://localhost:8000/catalog/Snowboarding/Snowboard/edit. Returns the edititem.html template.

* "/catalog/_category_/_item_/delete/" - deleteItem(category_name, item_name) function. Delete an item. Example, http://localhost:8000/catalog/Snowboarding/Snowboard/delete/.

* "/catalog/category/_category_/delete/" - deleteCategory(category_name) function. Delete a category. Example, http://localhost:8000/catalog/category/Snowboarding/delete/

* "/catalog/category/_category_/edit/" - editCategory(category_name) function.  Edit a category. Example, http://localhost:8000/catalog/category/Snowboarding/edit/.  Returns the editcategory.html template.

* "/catalog/category/new/" - newCategory(). Add a new category. Example, http://localhost:8000/catalog/category/new/. Returns the newcategory.html template.

* /catalog/showItemLogTrans/_category_/_item_/" - showItemLogTrans(category_name, item_name) function. Display transaction log for an item. Example, http://localhost:8000/catalog/showItemlogTrans/Baseball/Bat. Returns the logview.html template.

## Credits and Acknowledgments
Created by: Steven Scanniello
Email: sscanni@comcast.net
