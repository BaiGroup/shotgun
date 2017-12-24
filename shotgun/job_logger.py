#!/usr/bin/env python

from __future__ import unicode_literals
from future.utils import iteritems
import os
from shotgun.config import read_config, write_config
import shotgun.database as db


class Job(object):
    ACTIVE_STATE = ['queued', 'dependency_hold', 'user_hold', 'system_hold',
                    'running']

    def __init__(self, context, job_dir, jobid=None):
        self.context = context
        self.job_log = os.path.join(job_dir, 'job.yaml')
        self.config = read_config(self.job_log)
        if jobid is not None:
            self.set_jobid(jobid)
        if 'targets' not in self.config:
            self.config['targets'] = {}

    @property
    def active_targets(self):
        res = {}
        for tname, tinfo in iteritems(self.config['targets']):
            if self.is_active(tinfo['state']):
                res[tname] = tinfo
        return res

    def cancel(self, target_name):
        return self.set_job_state(target_name, 'canceled')

    def hold(self, target_name):
        return self.set_job_state(target_name, 'user_hold')

    @classmethod
    def is_active(cls, state):
        return state in cls.ACTIVE_STATE

    @classmethod
    def is_running(cls, state):
        return state == 'running'

    def release(self, target_name):
        return self.set_job_state(target_name, 'queued')

    @property
    def running_targets(self):
        res = {}
        for tname, tinfo in iteritems(self.config['targets']):
            if self.is_running(tinfo['state']):
                res[tname] = tinfo
        return res

    def save_config(self):
        write_config(self.job_log, self.config)

    def set_exited(self, target_name):
        return self.set_job_state(target_name, 'exited')

    def set_jobid(self, jobid):
        self.config['jobid'] = jobid
        self.save_config()
        return self

    def set_job_state(self, target_name, state):
        self.config['targets'][target_name]['state'] = state
        self.save_config()

        if len(self.running_targets) > 0:
            db.set_started(self.config['jobid'],
                           db=self.context.VAULT)
        elif len(self.active_targets) == 0:
            db.set_finished(self.config['jobid'],
                            db=self.context.VAULT)

        return self

    def set_submitted(self, target_name, result):
        if target_name not in self.config['targets']:
            self.config['targets'][target_name] = {}

        if result is not None and result.ok:
            self.config['targets'][target_name]['job_qid'] = result.job_qid
            self.set_job_state(target_name, 'queued')
        else:
            self.set_job_state(target_name, 'submit_failed')

        return self

    def set_running(self, target_name):
        return self.set_job_state(target_name, 'running')

    @property
    def targets(self):
        return self.config['targets'].copy()
