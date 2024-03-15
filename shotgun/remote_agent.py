#!/usr/bin/env python

from __future__ import print_function, unicode_literals
from future.utils import iteritems
import importlib
from invoke.exceptions import UnexpectedExit
import logging
import math
import queue
import re
import shlex
from string import Template
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

    def __str__(self):
        return '[{}]'.format(self.host)

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
        print('{} Canceling: '.format(str(self)), end='')
        return self.run(cmd)

    def convert_size_to_MB(self, size_str):
        regex = re.compile("^(?P<numbers>\d*)(?P<letters>\w*)$")
        try:
            (size, unit) = regex.search(size_str).groups()
        except TypeError:
            return size_str

        if size:
            size = int(size)
        else:
            raise ValueError('{} Incorrect memory specs: {}'.format(str(self), size_str))

        if not unit:
            return size
        else:
            unit = unit.upper()

        if unit == 'TB' or unit == 'T':
            size *= 1024**2
        elif unit == 'GB' or unit == 'G':
            size *= 1024
        elif unit == 'KB' or unit == 'K':
            size = math.ceil(size/1024)
        elif unit == 'B':
            size = math.ceil(size/1024**2)

        return size

    @failable(UnexpectedExit)
    def hold(self, job_qids):
        cmd = self.sched.hold_command(job_qids)
        print('{} Holding: '.format(str(self)), end='')
        return self.run(cmd)

    @failable(UnexpectedExit)
    def query(self, job_qid, hide='out'):
        cmd = self.sched.query_command(job_qid)
        print('{} Querying: '.format(str(self)), end='')
        result = self.run(cmd, hide=hide)
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
        cmd = 'rsync -rltDz --partial {} {}:{}/ {}/'
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
        cmd = 'rsync -rltDz --partial --delete {} {}/ {}:{}/'
        cmd = cmd.format(exclude_str, local_dir, host, remote_dir)
        print('{} Rsyncing: {}'.format(str(self), cmd))
        return subprocess.call(shlex.split(cmd), stdout=subprocess.PIPE)

    @failable(UnexpectedExit)
    def run(self, cmd, **kwargs):
        if 'command_decorator' in self.attr:
            if isinstance(self.attr['command_decorator'], str):
                command_decorator = self.attr['command_decorator']
            elif self.attr['command_decorator']:
                command_decorator = ';'.join(self.attr['command_decorator'])
            template = Template(command_decorator)
            cmd = template.safe_substitute(command=cmd)

        print(cmd)
        return self.conn.run(cmd, **kwargs)

    def set_memory_default(self, **kwargs):
        if kwargs['mem_per_cpu'] is not None:
            kwargs['mem_per_cpu'] = self.convert_size_to_MB(kwargs['mem_per_cpu'])
        if kwargs['mem_total'] is not None:
            kwargs['mem_total'] = self.convert_size_to_MB(kwargs['mem_total'])
            if kwargs['mem_per_cpu'] is None:
                kwargs['mem_per_cpu'] = int(kwargs['mem_total'] / kwargs['cpus_per_node'] / kwargs['nodes'])
            else:
                print('Ignoring mem_total (overriden by mem_per_cpu).')
                kwargs['mem_total'] = int(kwargs['mem_per_cpu']) * kwargs['cpus_per_node'] * kwargs['nodes']
        elif kwargs['mem_per_cpu'] is not None:
            kwargs['mem_total'] = int(kwargs['mem_per_cpu']) * kwargs['cpus_per_node'] * kwargs['nodes']

        return kwargs

    @failable(UnexpectedExit)
    def submit(self, job_dir, **kwargs):
        kwargs = self.with_submit_defaults(**kwargs)
        seconds = time_in_seconds(kwargs['time'])
        hours = int(seconds/3600)
        minutes = math.ceil((seconds - hours*3600)/60)
        kwargs['time'] = '{:d}:{:02d}'.format(hours, minutes)
        extra_options = kwargs.pop('extra_options', ' ')
        if extra_options is None:
            extra_options = ' '
        else:
            extra_options = ' ' + extra_options + ' '
        cmd = self.sched.submit_command(**kwargs).replace(' ', extra_options, 1)
        print('{} Submitting: '.format(str(self)), end='')
        result = self.run('cd {} && {}'.format(job_dir, cmd))
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
        print('{} Make remote directory: '.format(str(self)), end='')
        result = self.run(cmd)

        if result is not None and result.ok:
            return self.rsync_to_remote(local_dir, remote_dir, hide=hide,
                                        exclude=exclude)

    @failable(UnexpectedExit)
    def release(self, job_qids):
        cmd = self.sched.release_command(job_qids)
        print('{} Releasing hold: '.format(str(self)), end='')
        return self.run(cmd)

    def with_submit_defaults(self, **kwargs):
        kwargs = self.set_memory_default(**kwargs)

        for key, val in iteritems(kwargs):
            try:
                if (val is None) or (is_number(val) and val < 0) \
                   or (isinstance(val, str) and len(val) == 0):
                    kwargs[key] = self.attr[key]
            except KeyError:
                pass

        kwargs = self.set_memory_default(**kwargs)
        return kwargs
