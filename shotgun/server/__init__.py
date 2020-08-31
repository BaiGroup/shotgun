from __future__ import unicode_literals
from collections import namedtuple
from flask import Flask
from shotgun import APP_NAME
from shotgun.config import read_config, user_config_file
from shotgun.exception import ShotgunError


FlaskConfig = namedtuple('FlaskConfig', ['TOKEN', 'VAULT'])


def get_config():
    config_file = user_config_file()
    config = read_config(config_file)

    flask_config = {}
    for key in FlaskConfig._fields:
        try:
            flask_config[key] = config[key]
        except KeyError as e:
            raise ServerInitError(
                '"{}" missing in: {}.\n'
                'Initialize by: shotgun init'
                .format(key, config_file)
            ) from e

    return FlaskConfig(**flask_config)


class ServerInitError(ShotgunError):
    pass


app = Flask(APP_NAME)
app.config.from_object(get_config())


import shotgun.server.responder
