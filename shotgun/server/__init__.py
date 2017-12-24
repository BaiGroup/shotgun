from __future__ import unicode_literals
from collections import namedtuple
from flask import Flask
from shotgun import APP_NAME
from shotgun.config import read_config, user_config_file


FlaskConfig = namedtuple('FlaskConfig', ['TOKEN', 'VAULT'])


def get_config():
    config_file = user_config_file()
    config = read_config(config_file)

    flask_config = {}
    for key in FlaskConfig._fields:
        try:
            flask_config[key] = config[key]
        except KeyError:
            raise RuntimeError(
                '"{}" missing in: {}.\n'
                'Initialize by: shotgun create-config'
                .format(key, config_file)
            )

    return FlaskConfig(**flask_config)


app = Flask(APP_NAME)
app.config.from_object(get_config())


import shotgun.server.responder
