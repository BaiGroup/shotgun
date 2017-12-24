import binascii
import collections
from functools import wraps
import logging
from numbers import Number
import os
from shotgun import APP_NAME
from string import Template


_logger = logging.getLogger(APP_NAME)
_logger.addHandler(logging.NullHandler())


def failable(exception):
    def decorator(func):
        @wraps(func)
        def decorated(*args, **kwargs):
            try:
                res = func(*args, **kwargs)
            except exception as ex:
                res = None
                _logger.exception('*** The following exception ignored ***')
            return res
        return decorated
    return decorator


def generate_token(length=12):
    return binascii.hexlify(os.urandom(length)).decode()


def ints_to_str_list(ints):
    if not is_sequence_except_str(ints):
        ints = [ints]
    return [str(x) for x in ints]


def is_number(obj):
    return isinstance(obj, Number)


def is_sequence_except_str(obj):
    if isinstance(obj, str):
        return False
    else:
        return isinstance(obj, collections.Sequence)


def template_file(filename):
    module_dir = os.path.dirname(__file__)
    return os.path.join(module_dir, 'templates', filename)


def template_from_file(template_file):
    with open(template_file) as f:
        template_str = f.read()
    return Template(template_str)


def time_in_seconds(time_str):
    parts = time_str.split('-')

    if len(parts) == 2:
        days = int(parts[0])
        time_str = parts[1]
    else:
        days = 0
        time_str = parts[0]

    hours, minutes, seconds = [int(x) for x in time_str.split(':')]
    return seconds + (minutes + (hours + days*24) * 60) * 60
