from __future__ import unicode_literals
import os
from ruamel.yaml import YAML
from shotgun import APP_NAME


def find_job_root_config(filename=APP_NAME+'.yaml'):
    curdir = os.getcwd()
    while True:
        root_config = os.path.join(curdir, filename)
        if os.path.isfile(root_config):
            break
        elif curdir == '/':
            raise FileNotFoundError('Config file not found: ' + filename)
        else:
            curdir = os.path.normpath(os.path.join(curdir, '..'))
    return root_config


def read_config(filename):
    yaml = YAML()
    try:
        with open(filename) as f:
            config = yaml.load(f)
    except FileNotFoundError:
        config = {}

    if config is None:
        config = {}

    return config


def user_config_file():
    return os.path.expanduser('~/.{}.yaml'.format(APP_NAME))


def write_config(filename, config):
    yaml = YAML()
    with open(filename, 'w') as f:
        yaml.dump(config, f)
