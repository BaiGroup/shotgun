#!/usr/bin/env python

from __future__ import print_function, unicode_literals
from future.utils import iteritems
import importlib
from invoke.exceptions import UnexpectedExit
import logging
import math
import queue
import shlex
from shotgun import APP_NAME
from shotgun.util import failable, is_number, is_sequence_except_str,\
    time_in_seconds
import subprocess
import sys
import threading


_logger = logging.getLogger(APP_NAME)
_logger.addHandler(logging.NullHandler())


def enqueue_output(fd, queue, output=True):
    for line in iter(fd.readline, b''):
        l = line.decode(sys.stdout.encoding)
        queue.put(l)
        if output:
            print(l, end='')
    fd.close()


class Connection(object):
    '''A replacement for fabric.Connection based on external SSH client.'''

    def __init__(self, host):
        self.host = host

    def close(self):
        pass

    def run(self, cmd, hide=None):
        ssh_cmd = "ssh {} '{}'".format(self.host, cmd)
        res = subprocess.Popen(shlex.split(ssh_cmd), stdout=subprocess.PIPE,
                               stderr=subprocess.PIPE)

        prints = [True, True]
        if hide == 'out':
            prints = [False, True]
        elif hide == 'err':
            prints = [True, False]
        elif hide == 'both' or hide == True:
            prints = [False, False]
        elif hide is not None and hide != False:
            _logger.warning('hide=%s is not valid', str(hide))

        fds = [res.stdout, res.stderr]
        queues = []
        for fd, p in zip(fds, prints):
            q = queue.Queue()
            queues.append(q)
            t = threading.Thread(target=enqueue_output, args=(fd, q, p))
            t.daemon = True
            t.start()

        res.wait()
        output = []
        for q in queues:
            o = []
            while True:
                try:
                    line = q.get(block=False)
                    o.append(line)
                except queue.Empty:
                    break
            output.append(''.join(o))

        res.stdout = output[0]
        res.stderr = output[1]
        res.ok = res.returncode == 0
        return res


class RemoteAgent(object):
    def __init__(self, context, name, attr):
        self.context = context
        self.name = name
        self.attr = attr
        self.conn = Connection(attr['host'])
        sched_mod = 'shotgun.scheduler.{}'.format(self.attr['scheduler'])
        self.sched = importlib.import_module(sched_mod)

    def __del__(self):
        self.conn.close()

    def __str__(self):
        return '[{}]'.format(self.name)

    @failable(UnexpectedExit)
    def cancel(self, job_qids):
        cmd = self.sched.cancel_command(job_qids)
        print('{} Canceling: {}'.format(str(self), cmd))
        return self.conn.run(cmd)

    @failable(UnexpectedExit)
    def hold(self, job_qids):
        cmd = self.sched.hold_command(job_qids)
        print('{} Holding: {}'.format(str(self), cmd))
        return self.conn.run(cmd)

    @failable(UnexpectedExit)
    def query(self, job_qid, hide='out'):
        cmd = self.sched.query_command(job_qid)
        print('{} Querying: {}'.format(str(self), cmd))
        result = self.conn.run(cmd, hide=hide)
        if result.ok:
            job_info = self.sched.parse_query_output(result.stdout)
            for attr in self.sched.QUERY_ATTRIBUTES:
                setattr(result, attr, job_info[attr])
        return result

    @failable(UnexpectedExit)
    def rsync_from_remote(self, local_dir, remote_dir, hide='out', exclude=[]):
        if not is_sequence_except_str(exclude):
            exclude = [exclude]
        exclude_str = ' '.join('--exclude='+str(ex) for ex in exclude)

        host = self.attr['host']
        cmd = 'rsync -rltDzP {} {}:{}/ {}/'
        cmd = cmd.format(exclude_str, host, remote_dir, local_dir)
        print('{} Rsyncing: {}'.format(str(self), cmd))
        return subprocess.call(shlex.split(cmd), stdout=subprocess.PIPE)

    @failable(UnexpectedExit)
    def rsync_to_remote(self, local_dir, remote_dir, hide='out', exclude=[]):
        if not is_sequence_except_str(exclude):
            exclude = [exclude]
        exclude_str = ' '.join('--exclude='+str(ex) for ex in exclude)
        if self.context.delete_excluded:
            exclude_str = '--delete-excluded ' + exclude_str

        host = self.attr['host']
        cmd = 'rsync -rltDzP --delete {} {}/ {}:{}/'
        cmd = cmd.format(exclude_str, local_dir, host, remote_dir)
        print('{} Rsyncing: {}'.format(str(self), cmd))
        return subprocess.call(shlex.split(cmd), stdout=subprocess.PIPE)

    @failable(UnexpectedExit)
    def submit(self, job_dir, **kwargs):
        kwargs = self.with_submit_defaults(**kwargs)
        seconds = time_in_seconds(kwargs['time'])
        hours = int(seconds/3600)
        minutes = math.ceil((seconds - hours*3600)/60)
        kwargs['time'] = '{:d}:{:02d}'.format(hours, minutes)
        cmd = self.sched.submit_command(**kwargs)
        print('{} Submitting: {}'.format(str(self), cmd))
        result = self.conn.run('cd {} && {}'.format(job_dir, cmd))
        if result is not None and result.ok:
            job_info = self.sched.parse_submit_output(result.stdout)
            result.job_qid = job_info['job_qid']
        return result

    @failable(UnexpectedExit)
    def sync_from_remote(self, local_dir, remote_dir, hide='out',
                         exclude=[]):
        print('{} Syncing (REMOTE) {} -> (LOCAL) {}'
              .format(str(self), remote_dir, local_dir))
        return self.rsync_from_remote(local_dir, remote_dir, hide=hide,
                                      exclude=exclude)

    @failable(UnexpectedExit)
    def sync_to_remote(self, local_dir, remote_dir, hide='out',
                       exclude=[]):
        print('{} Syncing (LOCAL) {} -> (REMOTE) {}'
              .format(str(self), local_dir, remote_dir))

        cmd = 'mkdir -p {}'.format(remote_dir)
        print('{} Make remote directory: {}'.format(str(self), cmd))
        result = self.conn.run(cmd)

        if result is not None and result.ok:
            return self.rsync_to_remote(local_dir, remote_dir, hide=hide,
                                        exclude=exclude)

    @failable(UnexpectedExit)
    def release(self, job_qids):
        cmd = self.sched.release_command(job_qids)
        print('{} Releasing hold: {}'.format(str(self), cmd))
        return self.conn.run(cmd)

    def with_submit_defaults(self, **kwargs):
        for key, val in iteritems(kwargs):
            try:
                if (val is None) or (is_number(val) and val < 0) \
                   or (isinstance(val, str) and len(val) == 0):
                    kwargs[key] = self.attr[key]
            except KeyError:
                pass
        return kwargs
