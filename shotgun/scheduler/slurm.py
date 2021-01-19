#!/usr/bin/env python

from __future__ import unicode_literals
from future.utils import listvalues
from shotgun.exception import ShotgunError
from shotgun.util import ints_to_str_list, time_in_seconds


def cancel_command(job_qids):
    qid_list = ints_to_str_list(job_qids)
    cmd = 'scancel {}'.format(' '.join(qid_list))
    return cmd


def hold_command(job_qids):
    qid_list = ints_to_str_list(job_qids)
    cmd = 'scontrol hold {}'.format(','.join(qid_list))
    return cmd


_QUERY_MAP = {
    'JobId': 'job_qid',
    'JobState': 'job_state',
    'Reason': 'note',
    'RunTime': 'run_time',
    'TimeLimit': 'time_limit',
    'Partition': 'queue'
}
QUERY_ATTRIBUTES = listvalues(_QUERY_MAP)
_QUERY_STATE_MAP = {
    'PENDING': 'queued',
    'RUNNING': 'running',
    'COMPLETED': 'completed',
    'CANCELLED': 'canceled',
    'TIMEOUT': 'killed'
}
_QUERY_REASON_MAP = {
    'None': 'running|completed',
    'Resources': 'queued',
    'Priority': 'queued',
    'Dependency': 'dependency_hold',
    'JobHeldUser': 'user_hold',
    'QOSMaxJobsPerUserLimit': 'system_hold',
    'TimeLimit': 'killed'
}


def parse_query_output(stdout):
    info = {}
    for field in stdout.strip().replace('\n', ' ').split():
        try:
            key, value = field.split('=', maxsplit=1)
        except ValueError as e:
            continue
        if key in _QUERY_MAP:
            if 'Time' in key:
                value = time_in_seconds(value)
            info[_QUERY_MAP[key]] = value

    try:
        info['job_state'] = _QUERY_STATE_MAP[info['job_state']]
    except KeyError as e:
        raise SlurmParseQueryError('STDOUT: {}'.format(stdout)) from e

    if info['job_state'] == 'queued':
        try:
            info['job_state'] = _QUERY_REASON_MAP[info['note']]
        except KeyError:
            pass

    return info


def parse_submit_output(stdout):
    info = {}
    out = stdout.strip()
    if 'Submitted batch job' in out:
        info['job_qid'] = int(out.split()[-1])
    return info


def query_command(job_qid):
    cmd = 'scontrol show job {}'.format(job_qid)
    return cmd


def release_command(job_qids):
    qid_list = ints_to_str_list(job_qids)
    cmd = 'scontrol release {}'.format(','.join(qid_list))
    return cmd


class SlurmParseQueryError(ShotgunError):
    pass


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
        options += ' --mem-per-cpu={}'.format(mem_per_cpu)

    if queue is not None:
        options += ' --partition {}'.format(queue)

    if account is not None:
        options += ' --account {}'.format(account)

    if constraint is not None:
        options += ' --constraint="{}"'.format(constraint)

    cmd = ('sbatch --nodes={} --ntasks-per-node={} --cpus-per-task=1'
           ' --time={}:00 --job-name {}{} {}'
           .format(nodes, cpus_per_node, time, name, options, job_script))

    return cmd
