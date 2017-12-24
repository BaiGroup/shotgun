from functools import wraps
from flask import request, Response
from shotgun.server import app


def check(username, password):
    '''Check if username / password combination is valid.'''

    return username == 'token' and password == app.config['TOKEN']


def denied():
    '''Sends a 401 response.'''

    return Response(
        'Could not verify your access level for that URL.\n'
        'You have to login with proper credentials', 401,
        {'WWW-Authenticate': 'Basic realm="Login Required"'}
    )


def basic_auth(f):
    @wraps(f)
    def decorated(*args, **kwargs):
        auth = request.authorization
        if not auth or not check(auth.username, auth.password):
            return denied()
        else:
            return f(*args, **kwargs)
    return decorated
