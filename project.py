#!/usr/bin/env python2
from flask import Flask, render_template, request, redirect, jsonify, url_for, flash
from sqlalchemy import create_engine, asc, desc
from sqlalchemy.orm import sessionmaker, relationship, joinedload
from sqlalchemy.exc import IntegrityError
from models import Base, Category, CatalogItem, User, ItemLog
from flask import session as login_session
import random
import string
from oauth2client.client import flow_from_clientsecrets
from oauth2client.client import FlowExchangeError
import httplib2
import json
from flask import make_response
import requests
import datetime

app = Flask(__name__)

CLIENT_ID = json.loads(
    open('client_secrets.json', 'r').read())['web']['client_id']
APPLICATION_NAME = "Sports Catalog Application"

engine = create_engine('sqlite:///catalog.db?check_same_thread=False')
Base.metadata.bind = engine

DBSession = sessionmaker(bind=engine)
session = DBSession()


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

    login_session['username'] = data['name']
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
@app.route('/catalog/categories')
def showCategories():
    rows = session.query(Category).count()
    categories = session.query(Category).order_by(asc(Category.name)).all()
    items = session.query(CatalogItem.name, Category.name).filter(CatalogItem.category_id==Category.id).order_by(desc(CatalogItem.id)).limit(rows).all()
    if 'username' not in login_session:
        return render_template('publiccategories.html', categories=categories, items=items, displayRecent=True)
    else:
        return render_template('categories.html', categories=categories, items=items, displayRecent=True)

# Display all items for a Category
# Example: localhost:8000/catalog/Snowboarding/items
@app.route('/catalog/<string:name>/items')
def showCategoryItems(name):
    category = session.query(Category).filter_by(name=name).one()
    items = session.query(CatalogItem).filter_by(category_id=category.id).order_by(asc(CatalogItem.name)).all()
    itemcount = session.query(CatalogItem).filter_by(category_id=category.id).count()
    if itemcount == 1:
       itemtitle = "%s (%s item)" % (category.name, str(itemcount))
    else:
       itemtitle = "%s (%s items)" % (category.name, str(itemcount))
    categories = session.query(Category).order_by(asc(Category.name)).all()
    if 'username' not in login_session:
        return render_template('publiccategories.html', category=category, categories=categories, items=items, itemtitle=itemtitle, displayRecent=False)
    else:
        return render_template('categories.html', category=category, categories=categories, items=items, itemtitle=itemtitle, displayRecent=False)

# Display a specific item
# Example: localhost:8000/catalog/Snowboarding/Snowboard
@app.route('/catalog/<string:category_name>/<string:item_name>')
def showItem(category_name, item_name):
    category = session.query(Category).filter_by(name=category_name).one()
    item = session.query(CatalogItem).filter_by(name=item_name, category_id=category.id).one()
    if 'username' not in login_session:
        return render_template('publicitem.html', category_name=category_name, item_name=item_name, itemDesc=item.desc)
    else:
        return render_template('item.html', category_name=category_name, item_name=item_name, itemDesc=item.desc)

# Add new item
# Example: localhost:8000/catalog/item/new
@app.route('/catalog/item/new', methods=['GET', 'POST'])
def newItem():
    if 'username' not in login_session:
        return redirect('/login')
    if request.method == 'POST':
        if request.form.get('save') == 'save':
           try:
              item = CatalogItem(name=request.form['name'], desc=request.form['desc'],
                        category_id=request.form['category'], user_id=login_session['user_id'])
              session.add(item)
              session.commit()
              logTrans("Add", item)
              flash('New Catalog Item %s Successfully Created' % (item.name))
              return redirect(url_for('showCategories'))
           except IntegrityError:
              session.rollback()
              flash('"%s" Already Exists...Catalog Item not added.' % request.form['name'])
              return redirect(url_for('showCategories'))
        else:
           return redirect(url_for('showCategories'))
    else:
        categories = session.query(Category).order_by(asc(Category.name)).all()
        return render_template('newitem.html', categories=categories)

# Edit a specific item
# Example: localhost:8000/catalog/Snowboarding/Snowboard/edit
@app.route('/catalog/<string:category_name>/<string:item_name>/edit', methods=['GET', 'POST'])
def editItem(category_name, item_name):
      if 'username' not in login_session:
          return redirect('/login')
      category = session.query(Category).filter_by(name=category_name).one()
      item = session.query(CatalogItem).filter_by(name=item_name, category_id=category.id).one()
      categories = session.query(Category).order_by(asc(Category.name)).all()
      if request.method == 'POST':
         if request.form.get('save') == 'save':
            try:
                print ("current category_name=" + category_name)
                print ("current item_name=" + item_name)
                print ("current item.category_id on db table=" + str(item.category.id))
                print ("name=" + request.form['name'])
                print ("desc=" + request.form['desc'])
                print ("category=" + request.form['category'])
                item.name = request.form['name']
                item.desc = request.form['desc']
                item.category_id = request.form['category']
                item.user_id=login_session['user_id']
                session.add(item)
                session.commit()
                logTrans("Change", item)
                flash('Catalog Item Successfully Edited %s' % item.name)
                return redirect(url_for('showCategories'))
            except IntegrityError:
                session.rollback()
                flash('"%s" Already Exists...Catalog Item not changed.' % request.form['name'])
                return redirect(url_for('showCategories'))
         else:
            return redirect(url_for('showCategories'))
      else:
         return render_template('edititem.html', category_name=category_name, item=item, categories=categories)

# Delete a specific item
# Example: localhost:8000/catalog/Snowboarding/Snowboard/delete
@app.route('/catalog/<string:category_name>/<string:item_name>/delete', methods=['GET', 'POST'])
def deleteItem(category_name, item_name):
    if 'username' not in login_session:
        return redirect('/login')
    if request.method == 'POST':
       if request.form.get('delete') == 'delete':
          category = session.query(Category).filter_by(name=category_name).one()
          item = session.query(CatalogItem).filter_by(name=item_name, category_id=category.id).one()
          session.delete(item)
          session.commit()
          logTrans("Delete", item)
          flash('Catalog Item Successfully Deleted')
          return redirect(url_for('showCategories'))
       else:
          return redirect(url_for('showCategories'))
    else:
        return render_template('deleteitem.html', category_name=category_name, item_name=item_name)

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
          itemcategory_id=item.category_id,
          itemcategory=category.name)
    session.add(log)
    session.commit()
    return

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
    app.secret_key = 'super_secret_key'
    app.debug = True
    app.run(host='0.0.0.0', port=5000)
