#!/usr/bin/env python2
from flask import Flask, render_template, request, redirect, jsonify, url_for, flash, send_from_directory, make_response
from sqlalchemy import create_engine, asc, desc
from sqlalchemy.orm import sessionmaker, relationship, joinedload
from sqlalchemy.exc import IntegrityError
from models import Base, Category, CatalogItem, User, ItemLog
from flask import session as login_session
from oauth2client.client import flow_from_clientsecrets
from oauth2client.client import FlowExchangeError
import random
import string
import httplib2
import json
import requests
import datetime
import os

app = Flask(__name__)

CLIENT_ID = json.loads(
    open('client_secrets.json', 'r').read())['web']['client_id']
APPLICATION_NAME = "Sports Catalog Application"

engine = create_engine('sqlite:///catalog.db?check_same_thread=False')
Base.metadata.bind = engine

DBSession = sessionmaker(bind=engine)
session = DBSession()

app.secret_key = '\x0b8\xdf\x7f\x147\x1c\xe4\xdb5\xf1\x1f\xe3\x05\x7f_(8\xbd\x8bY'

# Create anti-forgery state token
@app.route('/login')
def showLogin():
    state = ''.join(random.choice(string.ascii_uppercase + string.digits)
                    for x in xrange(32))
    login_session['state'] = state
    # return "The current session state is %s" % login_session['state']
    return render_template('login.html', STATE=state)


@app.route('/fbconnect', methods=['POST'])
def fbconnect():
    if request.args.get('state') != login_session['state']:
        response = make_response(json.dumps('Invalid state parameter.'), 401)
        response.headers['Content-Type'] = 'application/json'
        return response
    access_token = request.data
    print "access token received %s " % access_token


    app_id = json.loads(open('fb_client_secrets.json', 'r').read())[
        'web']['app_id']
    app_secret = json.loads(
        open('fb_client_secrets.json', 'r').read())['web']['app_secret']
    url = 'https://graph.facebook.com/oauth/access_token?grant_type=fb_exchange_token&client_id=%s&client_secret=%s&fb_exchange_token=%s' % (
        app_id, app_secret, access_token)
    h = httplib2.Http()
    result = h.request(url, 'GET')[1]


    # Use token to get user info from API
    userinfo_url = "https://graph.facebook.com/v2.8/me"
    '''
        Due to the formatting for the result from the server token exchange we have to
        split the token first on commas and select the first index which gives us the key : value
        for the server access token then we split it on colons to pull out the actual token value
        and replace the remaining quotes with nothing so that it can be used directly in the graph
        api calls
    '''
    token = result.split(',')[0].split(':')[1].replace('"', '')

    url = 'https://graph.facebook.com/v2.8/me?access_token=%s&fields=name,id,email' % token
    h = httplib2.Http()
    result = h.request(url, 'GET')[1]
    # print "url sent for API access:%s"% url
    # print "API JSON result: %s" % result
    data = json.loads(result)
    login_session['provider'] = 'facebook'
    login_session['username'] = data["name"]
    login_session['email'] = data["email"]
    login_session['facebook_id'] = data["id"]

    # The token must be stored in the login_session in order to properly logout
    login_session['access_token'] = token

    # Get user picture
    url = 'https://graph.facebook.com/v2.8/me/picture?access_token=%s&redirect=0&height=200&width=200' % token
    h = httplib2.Http()
    result = h.request(url, 'GET')[1]
    data = json.loads(result)

    login_session['picture'] = data["data"]["url"]

    # see if user exists
    user_id = getUserID(login_session['email'])
    if not user_id:
        user_id = createUser(login_session)
    login_session['user_id'] = user_id

    output = ''
    output += '<h1>Welcome, '
    output += login_session['username']

    output += '!</h1>'
    output += '<img src="'
    output += login_session['picture']
    output += ' " style = "width: 300px; height: 300px;border-radius: 150px;-webkit-border-radius: 150px;-moz-border-radius: 150px;"> '

    flash("Now logged in as %s" % login_session['username'])
    return output


@app.route('/fbdisconnect')
def fbdisconnect():
    facebook_id = login_session['facebook_id']
    # The access token must me included to successfully logout
    access_token = login_session['access_token']
    url = 'https://graph.facebook.com/%s/permissions?access_token=%s' % (facebook_id,access_token)
    h = httplib2.Http()
    result = h.request(url, 'DELETE')[1]
    return "you have been logged out"


@app.route('/gconnect', methods=['POST'])
def gconnect():
    # Validate state token
    if request.args.get('state') != login_session['state']:
        response = make_response(json.dumps('Invalid state parameter.'), 401)
        response.headers['Content-Type'] = 'application/json'
        return response
    # Obtain authorization code
    code = request.data

    try:
        # Upgrade the authorization code into a credentials object
        oauth_flow = flow_from_clientsecrets('client_secrets.json', scope='')
        oauth_flow.redirect_uri = 'postmessage'
        credentials = oauth_flow.step2_exchange(code)
    except FlowExchangeError:
        response = make_response(
            json.dumps('Failed to upgrade the authorization code.'), 401)
        response.headers['Content-Type'] = 'application/json'
        return response

    # Check that the access token is valid.
    access_token = credentials.access_token
    url = ('https://www.googleapis.com/oauth2/v1/tokeninfo?access_token=%s'
           % access_token)
    h = httplib2.Http()
    result = json.loads(h.request(url, 'GET')[1])
    # If there was an error in the access token info, abort.
    if result.get('error') is not None:
        response = make_response(json.dumps(result.get('error')), 500)
        response.headers['Content-Type'] = 'application/json'
        return response

    # Verify that the access token is used for the intended user.
    gplus_id = credentials.id_token['sub']
    if result['user_id'] != gplus_id:
        response = make_response(
            json.dumps("Token's user ID doesn't match given user ID."), 401)
        response.headers['Content-Type'] = 'application/json'
        return response

    # Verify that the access token is valid for this app.
    if result['issued_to'] != CLIENT_ID:
        response = make_response(
            json.dumps("Token's client ID does not match app's."), 401)
        print "Token's client ID does not match app's."
        response.headers['Content-Type'] = 'application/json'
        return response

    stored_access_token = login_session.get('access_token')
    stored_gplus_id = login_session.get('gplus_id')
    if stored_access_token is not None and gplus_id == stored_gplus_id:
        response = make_response(json.dumps('Current user is already connected.'),
                                 200)
        response.headers['Content-Type'] = 'application/json'
        return response

    # Store the access token in the session for later use.
    login_session['access_token'] = credentials.access_token
    login_session['gplus_id'] = gplus_id

    # Get user info
    userinfo_url = "https://www.googleapis.com/oauth2/v1/userinfo"
    params = {'access_token': credentials.access_token, 'alt': 'json'}
    answer = requests.get(userinfo_url, params=params)

    data = answer.json()

    # Changed line because google user account may not have a username
    if 'name' in data:
       login_session['username'] = data['name']
    else:
       emailPrefix = data['email'].split("@")
       login_session['username'] = emailPrefix[0]

    login_session['picture'] = data['picture']
    login_session['email'] = data['email']
    # ADD PROVIDER TO LOGIN SESSION
    login_session['provider'] = 'google'

    # see if user exists, if it doesn't make a new one
    user_id = getUserID(data["email"])
    if not user_id:
        user_id = createUser(login_session)
    login_session['user_id'] = user_id

    output = ''
    output += '<h1>Welcome, '
    output += login_session['username']
    output += '!</h1>'
    output += '<img src="'
    output += login_session['picture']
    output += ' " style = "width: 300px; height: 300px;border-radius: 150px;-webkit-border-radius: 150px;-moz-border-radius: 150px;"> '
    flash("you are now logged in as %s" % login_session['username'])
    print "done!"
    return output

# User Helper Functions


def createUser(login_session):
    newUser = User(name=login_session['username'], email=login_session[
                   'email'], picture=login_session['picture'])
    session.add(newUser)
    session.commit()
    user = session.query(User).filter_by(email=login_session['email']).one()
    return user.id


def getUserInfo(user_id):
    user = session.query(User).filter_by(id=user_id).one()
    return user


def getUserID(email):
    try:
        user = session.query(User).filter_by(email=email).one()
        return user.id
    except:
        return None

# DISCONNECT - Revoke a current user's token and reset their login_session


@app.route('/gdisconnect')
def gdisconnect():
    # Only disconnect a connected user.
    access_token = login_session.get('access_token')
    if access_token is None:
        response = make_response(
            json.dumps('Current user not connected.'), 401)
        response.headers['Content-Type'] = 'application/json'
        return response
    url = 'https://accounts.google.com/o/oauth2/revoke?token=%s' % access_token
    h = httplib2.Http()
    result = h.request(url, 'GET')[0]
    if result['status'] == '200':
        response = make_response(json.dumps('Successfully disconnected.'), 200)
        response.headers['Content-Type'] = 'application/json'
        return response
    else:
        response = make_response(json.dumps('Failed to revoke token for given user.', 400))
        response.headers['Content-Type'] = 'application/json'
        return response

@app.route('/catalog/JSON')
def catalogJSON():
    categories = session.query(Category).options(joinedload(Category.items)).all()
    return jsonify(dict(Catalog=[dict(c.serialize, items=[i.serialize for i in c.items])
                         for c in categories]))

# Show all categories
@app.route('/')
@app.route('/catalog/categories/')
def showCategories():
    categories = session.query(Category).order_by(asc(Category.name)).all()
    items = session.query(CatalogItem, Category.name).filter(CatalogItem.category_id==Category.id).order_by(desc(CatalogItem.id)).limit(7).all()
    return render_template('categories.html', categories=categories, items=items, displayRecent=True)

# Display all items for a Category. Example: localhost:8000/catalog/Snowboarding/items
@app.route('/catalog/<string:name>/items/')
def showCategoryItems(name):
    category = session.query(Category).filter_by(name=name).one()
    items = session.query(CatalogItem).filter_by(category_id=category.id).order_by(asc(CatalogItem.name)).all()
    itemcount = session.query(CatalogItem).filter_by(category_id=category.id).count()
    if itemcount == 1:
       itemtitle = "%s (%s item)" % (category.name, str(itemcount))
    else:
       itemtitle = "%s (%s items)" % (category.name, str(itemcount))
    categories = session.query(Category).order_by(asc(Category.name)).all()

    # Setup prev and next category links
    cat = []
    for x, c in enumerate(categories):
        cat.append(c.name)
        if name == cat[x]:
           curIndex = x
    if curIndex == 0:
       prevCat = cat[len(cat)-1]
    else:
       prevCat = cat[curIndex-1]
    if curIndex == len(cat)-1:
       nextCat = cat[0]
    else:
       nextCat = cat[curIndex+1]             

    return render_template('categories.html', category=category, categories=categories, items=items, itemtitle=itemtitle, displayRecent=False, prevCat=prevCat, nextCat=nextCat)

# Display a specific item. Example: localhost:8000/catalog/Snowboarding/Snowboard
@app.route('/catalog/<string:category_name>/<string:item_name>/')
def showItem(category_name, item_name):
    category = session.query(Category).filter_by(name=category_name).one()
    item = session.query(CatalogItem).filter_by(name=item_name, category_id=category.id).one()
    try:
        itemuser = session.query(User).filter_by(id=item.user_id).one()
    except:
        itemuser = None
    return render_template('item.html', category_name=category_name, item=item, itemuser=itemuser)

# Add new item. Example: localhost:8000/catalog/item/new
@app.route('/catalog/item/new/', methods=['GET', 'POST'])
def newItem():
    if 'username' not in login_session:
        return redirect('/login')
    form = {}
    if request.method == 'POST':
        if request.form.get('save') == 'save':
            form['name'] = str(request.form['name'])
            form['desc'] = str(request.form['desc'])
            form['image'] = str(request.form['image'])
            form['category'] = int(request.form['category'])
            if len(request.form['name'].strip()) == 0:
               flash('Error! Item Name can not be blank') 
               categories = session.query(Category).order_by(asc(Category.name)).all()
               return render_template('newitem.html', categories=categories, imageList=getImages(), form=form)
            if len(request.form['name'].strip()) > 30:
               flash('Error! Item Name must be bwtween 1 and 30 characters') 
               categories = session.query(Category).order_by(asc(Category.name)).all()
               return render_template('newitem.html',categories=categories, imageList=getImages(), form=form)
            if len(request.form['desc'].strip()) > 250:
               flash('Error! Item Description must be bwtween 1 and 250 characters') 
               categories = session.query(Category).order_by(asc(Category.name)).all()
               return render_template('newitem.html', categories=categories, imageList=getImages(), form=form)
            try:
                item = CatalogItem(name=request.form['name'].strip(), desc=request.form['desc'].strip(), image=request.form['image'],
                            category_id=request.form['category'], user_id=login_session['user_id'])
                session.add(item)
                session.commit()
                logTrans("Add", item)
                flash('New Catalog Item %s Successfully Created' % (item.name))
                return redirect(url_for('showCategories'))
            except IntegrityError:
                session.rollback()
                flash('Error! "%s" Already Exists in this Category...Item not changed.' % request.form['name'])
                categories = session.query(Category).order_by(asc(Category.name)).all()
                return render_template('newitem.html', categories=categories, imageList=getImages(), form=form)
        else:
            return redirect(url_for('showCategories'))
    else:
        form['name'] = ""
        form['desc'] = ""
        form['image'] = ""
        form['category'] = 1
        categories = session.query(Category).order_by(asc(Category.name)).all()
        return render_template('newitem.html', categories=categories, imageList=getImages(), form=form)

# Edit a specific item. Example: localhost:8000/catalog/Snowboarding/Snowboard/edit
@app.route('/catalog/<string:category_name>/<string:item_name>/edit/', methods=['GET', 'POST'])
def editItem(category_name, item_name):
      if 'username' not in login_session:
          return redirect('/login')
      category = session.query(Category).filter_by(name=category_name).one()
      item = session.query(CatalogItem).filter_by(name=item_name, category_id=category.id).one()
      categories = session.query(Category).order_by(asc(Category.name)).all()
      if request.method == 'POST':
         if request.form.get('save') == 'save':
            form = {}
            form['name'] = str(request.form['name'])
            form['desc'] = str(request.form['desc'])
            form['image'] = str(request.form['image'])
            form['category'] = int(request.form['category'])
            if len(request.form['name'].strip()) == 0:
               flash('Error! Item Name can not be blank') 
               return render_template('edititem.html', category_name=category_name, item_name=item_name, form=form, categories=categories, imageList=getImages())
            if len(request.form['name'].strip()) > 30:
               flash('Error! Item Name must be bwtween 1 and 30 characters') 
               return render_template('edititem.html', category_name=category_name, item_name=item_name, form=form, categories=categories, imageList=getImages())
            if len(request.form['desc'].strip()) > 250:
               flash('Error! Item Description must be bwtween 1 and 250 characters') 
               return render_template('edititem.html', category_name=category_name, item_name=item_name, form=form, categories=categories, imageList=getImages())
            try:
                item.name = request.form['name'].strip()
                item.desc = request.form['desc'].strip()
                item.image = image=request.form['image']
                item.category_id = request.form['category']
                item.user_id=login_session['user_id']
                session.commit()
                logTrans("Change", item)
                flash('Catalog Item Successfully Edited %s' % item.name)
                return redirect(url_for('showCategories'))
            except IntegrityError:
                session.rollback()
                flash('Error! "%s" Already Exists in this Category...Item not changed.' % request.form['name'])
                return render_template('edititem.html', category_name=category_name, item_name=item_name, form=form, categories=categories, imageList=getImages())
         else:
             return redirect(url_for('showItem', category_name=category_name, item_name=item_name))
      else:
          form = {}
          form['name'] = item.name
          form['desc'] = item.desc
          form['image'] = item.image
          form['category'] = item.category_id
          return render_template('edititem.html', category_name=category_name, item_name=item_name, form=form, categories=categories, imageList=getImages())

# Delete a specific item. Example: localhost:8000/catalog/Snowboarding/Snowboard/delete
@app.route('/catalog/<string:category_name>/<string:item_name>/delete/', methods=['GET', 'POST'])
def deleteItem(category_name, item_name):
    if 'username' not in login_session:
        return redirect('/login')
    category = session.query(Category).filter_by(name=category_name).one()
    item = session.query(CatalogItem).filter_by(name=item_name, category_id=category.id).one()
    session.delete(item)
    session.commit()
    logTrans("Delete", item)
    flash('Catalog Item Successfully Deleted')
    return redirect(url_for('showCategories'))

# Delete Category. Example: localhost:8000/catalog/category/<string:category_name>/delete/
@app.route('/catalog/category/<string:category_name>/delete/', methods=['GET', 'POST'])
def deleteCategory(category_name):
    if 'username' not in login_session:
        return redirect('/login')
    category = session.query(Category).filter_by(name=category_name).one()
    session.delete(category)
    session.commit()
    # # logTrans("Delete", item)
    flash('Category Successfully Deleted')
    return redirect(url_for('showCategories'))

# Edit Category. Example: localhost:8000/catalog/category/<string:category_name>/edit/
@app.route('/catalog/category/<string:category_name>/edit/', methods=['GET', 'POST'])
def editCategory(category_name):
    if 'username' not in login_session:
        return redirect('/login')
    if request.method == 'POST':
        if request.form.get('save') == 'save':
           form = request.form
           if len(request.form['name'].strip()) == 0:
              flash('Error! Category name can not be blank') 
              return render_template('editcategory.html', category_name=category_name, form=form)
           if len(request.form['name'].strip()) > 30:
              flash('Error! Category name must be between 1 to 30 characters') 
              return render_template('editcategory.html', category_name=category_name, form=form)
           try:
               category = session.query(Category).filter_by(name=category_name).one()
               print "category.name={}".format(category.name)
               if category.name != request.form['name'].strip():
                   category.name = request.form['name'].strip()
                   session.commit()
                   flash('Category Successfully Editted')
               else:
                   flash('No change made to category')
               return redirect(url_for('showCategories'))
           except IntegrityError:
                   session.rollback()
                   flash('Error! "%s" Already Exists...Category name not changed.' % request.form['name'])
                   return render_template('editcategory.html', category_name=category_name, form=form)
        else:         
            return redirect(url_for('showCategories'))
    else:
        form = {}
        form['name'] = category_name
        return render_template('editcategory.html', category_name=category_name, form=form)

# New Category. Example: localhost:8000/catalog/category/<string:category_name>/new/
@app.route('/catalog/category/new/', methods=['GET', 'POST'])
def newCategory():
    if 'username' not in login_session:
        return redirect('/login')
    if request.method == 'POST':
       if request.form.get('save') == 'save':
          form = request.form
          if len(request.form['name'].strip()) == 0:
             flash('Error! Category name can not be blank') 
             return render_template('newcategory.html', form=form)
          if len(request.form['name'].strip()) > 30:
             flash('Error! Category name must be between 1 to 30 characters') 
             return render_template('newcategory.html', form=form)
          try:
             category = Category(name=request.form['name'].strip())
             session.add(category)
             session.commit()
             # logTrans("Add", item)
             flash('New Category %s Successfully Created' % (category.name))
             return redirect(url_for('showCategories'))
          except IntegrityError:
             session.rollback()
             flash('Error! "%s" Already Exists...Category not added.' % request.form['name'])
             return render_template('newcategory.html', form=form)
       else:
           return redirect(url_for('showCategories'))
    else:
        form = {}
        form['name'] = ""
        return render_template('newcategory.html', form=form)

@app.route('/upload/<filename>')
def send_image(filename):
    return send_from_directory("images", filename)

def getImages():
    folder = 'images'
    return os.listdir(folder)

# Save new item information on add
# Save new item information on an update
# Save item being deleted on a delete
def logTrans(trans, item):
    now = datetime.datetime.now()
    ts = now.strftime("%Y-%m-%d %H:%M:%S")
    # print ("ts=%s" % (ts))
    # print ("trans=%s" % (trans))
    # print ("username=%s" % (login_session['username']))
    # print ("email=%s" % (login_session['email']))
    # print ("user_id=%s" % (login_session['user_id']))
    # print ("item.id=%s" % (item.id))
    # print ("item.name=%s" % (item.name))
    # print ("item.desc=%s" % (item.desc))
    # print ("item.category_id=%s" % (item.category_id))
    category = session.query(Category).filter_by(id=item.category_id).one()
    # print ("category.name=%s" % (category.name))
    log = ItemLog(timestamp=ts, 
          trans=trans,
          username=login_session['username'],
          email=login_session['email'],
          user_id = login_session['user_id'],
          item_id=item.id,
          itemname=item.name,
          itemdesc=item.desc,
          itemimage=item.image,
          itemcategory_id=item.category_id,
          itemcategory=category.name)
    session.add(log)
    session.commit()
    return

@app.route('/catalog/showlog/')
def showLogTrans():
    itemlog = session.query(ItemLog).order_by(desc(ItemLog.timestamp)).all()
    return render_template('logview.html', itemlog=itemlog)

@app.route('/catalog/showItemlog/<string:category_name>/<string:item_name>/')
def showItemLogTrans(category_name, item_name):
    category = session.query(Category).filter_by(name=category_name).one()
    item = session.query(CatalogItem).filter_by(name=item_name, category_id=category.id).one()
    try:
        itemlog = session.query(ItemLog).filter_by(item_id=item.id, itemcategory_id=category.id).order_by(desc(ItemLog.timestamp)).all()
    except:
        pass
    return render_template('logview.html', itemlog=itemlog)


# Disconnect based on provider
@app.route('/disconnect')
def disconnect():
    if 'provider' in login_session:
        if login_session['provider'] == 'google':
            gdisconnect()
            del login_session['gplus_id']
            del login_session['access_token']
        if login_session['provider'] == 'facebook':
            fbdisconnect()
            del login_session['facebook_id']
        del login_session['username']
        del login_session['email']
        del login_session['picture']
        del login_session['user_id']
        del login_session['provider']
        flash("You have successfully been logged out.")
        return redirect(url_for('showCategories'))
    else:
        flash("You were not logged in")
        return redirect(url_for('showCategories'))
  


if __name__ == '__main__':
    app.debug = True
    app.run(host='0.0.0.0', port=5000)
