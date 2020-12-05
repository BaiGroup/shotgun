#!/usr/bin/env python

from __future__ import unicode_literals
from datetime import datetime
from future.utils import listvalues
from shotgun.util import ints_to_str_list

def cancel_command(job_qids):
    qid_list = ints_to_str_list(job_qids)
    cmd = 'bkill {}'.format(' '.join(qid_list))
    return cmd


def hold_command(job_qids):
    qid_list = ints_to_str_list(job_qids)
    cmd = 'bstop {}'.format(' '.join(qid_list))
    return cmd


_QUERY_MAP = {
    'Job': 'job_qid',
    'Status': 'job_state',
    'NON_EXISTENT_1': 'run_time',
    'NON_EXISTENT_2': 'time_limit',
    'Queue': 'queue'
}
QUERY_ATTRIBUTES = listvalues(_QUERY_MAP)
_QUERY_STATE_MAP = {
    'PEND': 'queued',
    'PSUSP': 'user_hold',
    'RUN': 'running',
    'EXIT': 'exited',
    'DONE': 'completed',
}


def parse_query_output(stdout):
    stdout_lines = stdout.strip().splitlines()
    info = {}

    for field in stdout_lines[0].split(', '):
        key, value = field[:-1].split(' <')
        if key in _QUERY_MAP:
            info[_QUERY_MAP[key]] = value

    i = 1
    while i < len(stdout_lines):
        if ' RUNLIMIT' in stdout_lines[i]:
            i += 1
            info['time_limit'] = 60*float(stdout_lines[i].split()[0])
        elif ': Started on ' in stdout_lines[i]:
            submit_time = datetime.strptime(stdout_lines[i].split(': ')[0],
                                            '%a %b %d %H:%M:%S')
            current_time = datetime.now()
            runtime = current_time - submit_time.replace(year=current_time.year)
            info['run_time'] = runtime.total_seconds()
        i += 1

    info['job_state'] = _QUERY_STATE_MAP[info['job_state']]
    if 'run_time' not in info:
        info['run_time'] = 0

    return info


def parse_submit_output(stdout):
    info = {'job_qid': int(stdout.strip().split('<')[1].split('>')[0])}
    return info


def query_command(job_qid):
    cmd = 'bjobs -UF -X {}'.format(job_qid)
    return cmd


def release_command(job_qids):
    qid_list = ints_to_str_list(job_qids)
    cmd = 'bresume {}'.format(' '.join(qid_list))
    return cmd


def submit_command(job_script, nodes=1, cpus_per_node=1,
                   mem_per_cpu=None, mem_total=None, time=24,
                   queue=None, account=None, name=None, constraint=None):
    options = ''

    if mem_total is not None:
        if mem_per_cpu is None:
            mem_per_cpu = int(mem_total / cpus_per_node / nodes)
        else:
            print('Ignoring mem_total (overriden by mem_per_cpu).')

    if mem_per_cpu is not None:
        options += ' -R "rusage[mem={}]"'.format(mem_per_cpu)

    if queue is not None:
        options += ' -q {}'.format(queue)

    if constraint is not None:
        options += ' -R "{}"'.format(constraint)

    cmd = ('bsub -R "span[ptile={}]" -n {} -W {} -J {}{} {}'
           .format(cpus_per_node, nodes*cpus_per_node, time, name, options,
                   job_script))

    return cmd
