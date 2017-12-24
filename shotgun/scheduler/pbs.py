#!/usr/bin/env python

from __future__ import unicode_literals
from future.utils import listvalues
from shotgun.util import ints_to_str_list, time_in_seconds


def cancel_command(job_qids):
    qid_list = ints_to_str_list(job_qids)
    cmd = 'qdel {}'.format(' '.join(qid_list))
    return cmd


def hold_command(job_qids):
    qid_list = ints_to_str_list(job_qids)
    cmd = 'qhold {}'.format(' '.join(qid_list))
    return cmd


_QUERY_MAP = {
    'Job Id': 'job_qid',
    'job_state': 'job_state',
    'resources_used.walltime': 'run_time',
    'Resource_List.walltime': 'time_limit',
    'queue': 'queue'
}
QUERY_ATTRIBUTES = listvalues(_QUERY_MAP)
_QUERY_STATE_MAP = {
    'Q': 'queued',
    'H': 'user_hold',
    'R': 'running',
    'C': 'exited'
}


def parse_query_output(stdout):
    stdout_lines = stdout.strip().replace('\n\t', '').splitlines()
    info = {'job_qid': int(stdout_lines[0].split(':')[1].split('.')[0])}

    for field in stdout_lines[1:]:
        key, value = field.split(' = ', maxsplit=1)
        key = key.strip()
        if key in _QUERY_MAP:
            if 'walltime' in key:
                value = time_in_seconds(value)
            info[_QUERY_MAP[key]] = value

    info['job_state'] = _QUERY_STATE_MAP[info['job_state']]
    if 'run_time' not in info:
        info['run_time'] = 0

    return info


def parse_submit_output(stdout):
    info = {'job_qid': int(stdout.strip().split('.')[0])}
    return info


def query_command(job_qid):
    cmd = 'qstat -f {}'.format(job_qid)
    return cmd


def release_command(job_qids):
    qid_list = ints_to_str_list(job_qids)
    cmd = 'qrls {}'.format(' '.join(qid_list))
    return cmd


def submit_command(job_script, nodes=1, cpus_per_node=1,
                   mem_per_cpu=None, mem_total=None, time=24,
                   queue=None, account=None, name=None, constraint=None):
    options = ''

    if mem_per_cpu is not None:
        options += ' -l pmem={}mb'.format(mem_per_cpu)
        if mem_total is None:
            mem_total = int(mem_per_cpu) * cpus_per_node * nodes

    if mem_total is not None:
        options += ' -l mem={}mb'.format(mem_total)

    if queue is not None:
        options += ' -q {}'.format(queue)

    if account is not None:
        options += ' -A {} -W group_list={}'.format(account, account)

    if constraint is not None:
        options += ' -l {}'.format(constraint)

    cmd = ('qsub -l nodes={}:ppn={},walltime={}:00:00 -N {}{} {}'
           .format(nodes, cpus_per_node, time, name, options, job_script))

    return cmd
