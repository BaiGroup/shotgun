#!/usr/bin/env python

from __future__ import unicode_literals
from flask import send_from_directory
import shotgun.commands as cmd
import shotgun.database as db
from shotgun.server import app
from shotgun.server.basic_auth import basic_auth


@app.route('/<int:job_id>/<target_name>/ended')
@basic_auth
def job_ended(job_id, target_name):
    cmd.job_ended(jobid=job_id, target_name=target_name)
    return 'Finished.'


@app.route('/<int:job_id>/<target_name>/started')
@basic_auth
def job_started(job_id, target_name):
    cmd.job_started(job_id, target_name=target_name)
    return 'Started.'


@app.route('/<int:job_id>/should-exit')
@basic_auth
def should_exit(job_id):
    started = db.is_started(job_id, db=app.config['VAULT'])
    return str(started)


@app.route('/<path:path>')
def static_files(path):
    print(path)
    return send_from_directory('static', path)
