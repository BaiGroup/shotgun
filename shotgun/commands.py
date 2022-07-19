#!/usr/bin/env python

from __future__ import print_function, unicode_literals
from builtins import zip
from future.utils import iteritems, listitems
from invoke import Collection, Context, Program, task
from invoke.config import Config, merge_dicts
import logging
import os
from pathlib import PurePath
from string import Template
import sys
import traceback
from shotgun import APP_NAME, APP_VERSION
from shotgun.config import find_job_root_config, read_config, user_config_file
from shotgun.util import (generate_token, make_executable,
                          template_file, template_from_file)


_logger = logging.getLogger(APP_NAME)
_logger.addHandler(logging.NullHandler())


@task
def bundle(ctx, job_template=None, dirs=None, output=None):
    with open(job_template) as f:
        job_script = f.read()

    dir_begin = job_script.find('#>>>BEGIN<<<')
    dir_end = job_script.find('#>>>END<<<', dir_begin)
    lines = job_script[dir_begin:dir_end].splitlines(keepends=True)
    template = Template(''.join(lines[1:]))

    with open(output, 'w') as f:
        f.write(job_script[:dir_begin])
        f.write(lines[0])

        for d in open(dirs):
            f.write(template.safe_substitute(job_dir=os.path.relpath(d.strip())))

        f.write(job_script[dir_end:])

    make_executable(output)


@task
def cancel_job(ctx, target=None, job_dir=None):
    qid_action(ctx, 'cancel', target_name=target, job_dir=job_dir)


@task(help={
    'cancel': 'cancels all jobs except the first one running.',
    'sync': 'downloads the files.',
    'project': 'check jobs belonging to the project of the working directory.',
    'quick': 'check only jobs that have started.',
    'targets': 'check only specified targets.',
    'j': 'how many jobs to check in parallel. Default is 3.',
    'retry': 'how many times to retry before giving up. Default is 2.'
})
def check_all(ctx, cancel=False, sync=False, project=False, quick=False,
              targets=[], j=3, retry=2):
    '''Checks the status of all submitted jobs; can be run anywhere.'''

    if project:
        project = find_job_root()
    else:
        project = None

    if quick:
        started = True
    else:
        started = None

    import shotgun.database as db
    jobs = db.find_jobs(ctx.VAULT, active=True, project=project,
                        started=started)
    check_all_parallel(ctx, jobs=jobs, cancel=cancel, sync=sync,
                       targets=targets, max_workers=j, retry=retry)


def check_all_parallel(ctx, jobs, cancel=False, sync=False, targets=[],
                       max_workers=1, retry=0):
    from concurrent.futures import wait, ThreadPoolExecutor

    futures = []
    with ThreadPoolExecutor(max_workers=max_workers) as executor:
        for job in jobs:
            futures.append(
                executor.submit(check_this, ctx, job_dir=job.jobdir,
                                targets=targets, cancel=cancel, sync=sync))

    failed_jobs = []
    for f, job in zip(futures, jobs):
        try:
            res = f.result()
        except:
            failed_jobs.append(job)
            print('****{} encountered an error: {}****\n{}'.
                  format(job.jobdir, sys.exc_info()[0], traceback.format_exc()))
        else:
            if res is not None:
                print('({}) {}'.format(job.jobdir, res))

    if len(failed_jobs) > 0 and retry > 0:
        print('Some jobs failed. Retrying ... (remaining retries: {})'.
              format(retry-1))
        check_all_parallel(ctx, jobs=failed_jobs, cancel=cancel, sync=sync,
                           targets=targets, max_workers=max_workers,
                           retry=retry-1)


@task(help={
    'job-dir': 'Default is current working directory.',
    'targets': 'check only specified targets.',
    'cancel': 'cancels all jobs except the first one running.',
    'sync': 'downloads the files.',
})
def check_this(ctx, job_dir=None, targets=[], cancel=False, sync=False):
    '''Checks the job in the current directory.'''

    if job_dir is None:
        job_dir = os.getcwd()

    os.chdir(job_dir)
    load_job_root_config(ctx)

    from shotgun.job_logger import Job
    curjob = Job(ctx, job_dir=job_dir)

    if len(targets) == 0:
        targets = curjob.active_targets
    else:
        targets_tmp = {}
        for tname, tinfo in iteritems(curjob.targets):
            if tname in targets:
                targets_tmp[tname] = tinfo
        targets = targets_tmp

    max_runtime = -1
    max_runtime_target_name = None
    active_jobs = {}
    running_jobs = {}

    from shotgun.remote_agent import RemoteAgent

    for tname, tinfo in iteritems(targets):
        if max_runtime_target_name is None:
            max_runtime_target_name = tname

        tattr = ctx.targets[tname]
        ra = RemoteAgent(ctx, tname, tattr)

        res = ra.query(tinfo['job_qid'])
        if res is None or not res.ok:
            curjob.set_exited(tname)
            continue

        fmtstr = ('[{}] JobId={} ({}), qid={}/{}, queue={}, '
                  'job_state={}, run_time={}, time_limit={}')
        print(fmtstr.format(tname, curjob.config['jobid'], job_dir,
                            tinfo['job_qid'],
                            res.job_qid, res.queue, res.job_state,
                            res.run_time, res.time_limit))
        curjob.set_job_state(tname, res.job_state)

        if Job.is_active(res.job_state):
            active_jobs[tname] = (ra, res)
            if Job.is_running(res.job_state):
                running_jobs[tname] = (ra, res)
                if res.run_time > max_runtime:
                    max_runtime = res.run_time
                    max_runtime_target_name = tname

    if cancel and len(running_jobs) > 0 and len(active_jobs) > 1:
        for tname, (ra, res) in iteritems(active_jobs):
            if tname != max_runtime_target_name:
                res = ra.cancel(res.job_qid)
                if res is not None and res.ok:
                    curjob.cancel(tname)

    if sync:
        download(ctx, target=max_runtime_target_name, job_dir=job_dir)


@task
def download(ctx, target=None, job_dir=None):
    if job_dir is None:
        job_dir = os.getcwd()

    os.chdir(job_dir)
    job_root = load_job_root_config(ctx)

    if target is None:
        from shotgun.job_logger import Job
        target, tinfo = get_one_active_target(Job(ctx, job_dir))
        if target is None:
            return

    target_attr = ctx.targets[target]
    rel_job_dir = os.path.relpath(job_dir, job_root)
    target_job_dir = os.path.join(target_attr['job_root'], rel_job_dir)

    from shotgun.remote_agent import RemoteAgent
    tagent = RemoteAgent(ctx, target, target_attr)
    tagent.sync_from_remote(job_dir, target_job_dir,
                            exclude=ctx.download_excludes)


def find_job_root():
    cfg_file = find_job_root_config()
    return os.path.dirname(cfg_file)


@task
def generate_util(ctx, target, job_dir=None):
    if job_dir is None:
        job_dir = os.getcwd()

    os.chdir(job_dir)
    load_job_root_config(ctx)
    target_attr = ctx.targets[target]

    from shotgun.job_logger import Job
    curjob = Job(ctx, job_dir=job_dir)

    template_filename = template_file('util.sh')
    template = template_from_file(template_filename)

    with open('util.sh', 'w') as f:
        f.write(template.safe_substitute(
            asset_dir=target_attr['asset_dir'],
            target_name=target,
            jobid=curjob.config['jobid'],
            server=ctx.SERVER,
            token=ctx.TOKEN,
            skip_pingback=str(target_attr['skip_pingback']).lower()
        ))


def get_one_active_target(curjob, suppress_error=False):
    if len(curjob.active_targets) != 1:
        if not suppress_error:
            print('Zero or 1+ active targets found!\n'
                  'Rerun this command and specify target '
                  '(--target name), or do "check_this --cancel".')
        return None, None
    else:
        target_name, target_info = listitems(curjob.active_targets)[0]
        return target_name, target_info


@task
def hold(ctx, target=None, job_dir=None):
    qid_action(ctx, 'hold', target_name=target, job_dir=job_dir)


@task
def init(ctx):
    template_filename = template_file('user_config.yaml')
    user_config = user_config_file()
    home_dir = os.path.expanduser('~')
    token = generate_token()

    _logger.debug('Using template file: %s\n'
                  'user_config_file: %s\n'
                  'home_dir: %s\n'
                  'token: %s', template_filename, user_config, home_dir, token)

    template = template_from_file(template_filename)

    with open(user_config, 'w') as f:
        f.write(template.substitute(home_dir=home_dir, token=token))

    load_config(ctx, user_config)

    import shotgun.database as db
    print('Creating database: ' + ctx.VAULT)
    s, ins = db.get_session_instance(ctx.VAULT)
    ins.create_db()


def job_ended(jobid, target_name):
    from threading import Thread
    Thread(target=set_finished,
           args=(Context(config=ShotgunConfig()),),
           kwargs=dict(
               target=target_name,
               jobid=jobid,
               sync=True
           )).start()


def job_started(jobid, target_name):
    from threading import Thread
    Thread(target=set_started,
           args=(Context(config=ShotgunConfig()),),
           kwargs=dict(
               target=target_name,
               jobid=jobid,
               cancel=True
           )).start()


@task(iterable=['state'],
      help={
          'state': 'list jobs by state: active/inactive, started/stopped, all. Default is active.',
          'project': 'list jobs belonging to the project of current working directory.',
      })
def list_jobs(ctx, state, project=False,
              created_after=None, created_before=None,
              updated_after=None, updated_before=None):
    if project:
        project = find_job_root()
    else:
        project = None

    if len(state) == 0:
        state = ['active']

    active = None
    started = None
    for s in state:
        if s == 'active':
            active = True
        elif s == 'inactive':
            active = False
        elif s == 'started':
            started = True
        elif s == 'stopped':
            started = False
        elif s == 'all':
            active = None
            started = None

    import shotgun.database as db
    res = db.find_jobs(ctx.VAULT, active=active, project=project,
                       started=started,
                       created_after=created_after,
                       created_before=created_before,
                       updated_after=updated_after,
                       updated_before=updated_before)

    print('Found {} jobs.'.format(len(res)))
    if len(res) > 0:
        print(' JobId Active Started       LastUpdate                  JobDir')
        fmtstr = '{:6d} {:6s} {:6s} {}  {}'
        for job in res:
            print(fmtstr.format(job.id, str(job.active), str(job.started),
                                job.updated_at, job.jobdir))


def load_config(ctx, config_file):
    cfg = read_config(config_file)
    ctx.config.load_overrides(cfg, merge=True)


def load_job_root_config(ctx):
    cfg_file = find_job_root_config()
    local_job_root = os.path.dirname(cfg_file)
    load_config(ctx, cfg_file)
    for tname, tattr in iteritems(ctx.targets):
        if 'host' not in tattr:
            tattr['host'] = tname
        if 'local_asset_dir' not in tattr and 'local_asset_dir' in ctx:
            tattr['local_asset_dir'] = ctx.local_asset_dir
        if 'skip_pingback' not in tattr:
            tattr['skip_pingback'] = True

        if 'local_asset_dir' in tattr:
            tattr['local_asset_dir'] = os.path.expandvars(tattr['local_asset_dir'])

            # The following must come after local_asset_dir is resolved
            if 'asset_dir' not in tattr and 'job_root' in tattr:
                rel_asset_dir = os.path.relpath(tattr['local_asset_dir'], local_job_root)
                tattr['asset_dir'] = os.path.join(tattr['job_root'], rel_asset_dir)
    return local_job_root


@task
def new_project(ctx):
    template_filename = template_file('job_root.yaml')
    job_root = os.getcwd()
    project = os.path.basename(job_root)
    home_dir = os.path.expanduser('~')

    _logger.debug('Using template file: %s\n'
                  'project: %s, job_root: %s\n'
                  'home_dir: %s', template_filename, project, job_root,
                  home_dir)

    template = template_from_file(template_filename)

    with open(APP_NAME+'.yaml', 'w') as f:
        f.write(template.substitute(home_dir=home_dir, project=project))


def qid_action(ctx, action, target_name=None, job_dir=None):
    if job_dir is None:
        job_dir = os.getcwd()

    os.chdir(job_dir)
    load_job_root_config(ctx)

    from shotgun.job_logger import Job
    curjob = Job(ctx, job_dir=job_dir)

    if target_name is None:
        target_name, tinfo = get_one_active_target(curjob)
        if target_name is None:
            return
    else:
        tinfo = curjob.config['targets'][target_name]

    (getattr(curjob, action))(target_name)

    from shotgun.remote_agent import RemoteAgent
    tagent = RemoteAgent(ctx, target_name, ctx.targets[target_name])
    (getattr(tagent, action))(tinfo['job_qid'])


@task
def release(ctx, target=None, job_dir=None):
    qid_action(ctx, 'release', target_name=target, job_dir=job_dir)


def setup_logger():
    import logging

    logger = logging.getLogger(APP_NAME)
    logger.setLevel(logging.DEBUG)
    ch = logging.StreamHandler()
    ch.setLevel(logging.DEBUG)
    logger.addHandler(ch)
    return logger


@task
def set_finished(ctx, target=None, jobid=None, sync=False):
    if jobid is None:
        job_dir = os.getcwd()
    else:
        import shotgun.database as db
        job_dir = db.get_jobdir(jobid, db=ctx.VAULT)

    from shotgun.job_logger import Job
    curjob = Job(ctx, job_dir=job_dir)

    if target is None:
        target, tinfo = get_one_active_target(curjob, suppress_error=True)
        if target is None:
            if jobid is None:
                print('Either target or jobid needs to be provided.')
            else:
                db.set_finished(jobid, db=ctx.VAULT)
            return

    if sync:
        download(ctx, job_dir=job_dir, target=target)

    # only set the following if syncing is successful
    curjob.set_exited(target)


@task
def set_started(ctx, target, jobid=None, cancel=False, sync=False):
    if jobid is None:
        job_dir = os.getcwd()
    else:
        import shotgun.database as db
        job_dir = db.get_jobdir(jobid, db=ctx.VAULT)

    from shotgun.job_logger import Job
    curjob = Job(ctx, job_dir=job_dir)

    curjob.set_running(target)

    running_targets = curjob.running_targets

    if cancel:
        for tname, tinfo in iteritems(curjob.active_targets):
            if tname == target:
                continue
            elif tname in running_targets:
                _logger.error(tname + ' is running -> not killed.')
                continue
            else:
                cancel_job(ctx, target=tname, job_dir=job_dir)

    if sync:
        download(ctx, job_dir=job_dir, target=target)


class ShotgunConfig(Config):
    prefix = APP_NAME

    @staticmethod
    def global_defaults():
        base_defaults = Config.global_defaults()
        shotgun_defaults = {
            'SERVER': 'localhost',
            'TOKEN': '',
            'VAULT': os.path.expanduser('~/{}.sqlite'.format(APP_NAME)),
            'targets': {},
            'default_targets': [],
            'download_excludes': [],
            'upload_excludes': ['job.yaml'],
        }
        return merge_dicts(base_defaults, shotgun_defaults)


@task(iterable=['targets'],
      help={
          'job-script': 'batch script to submit to the queuing system. Needs '
          'to reside in the job directory or the local asset directory. If '
          'given as a relative path, it is with respect to the job directory.',
      })
def submit(ctx, job_script=None, nodes=-1, cpus_per_node=-1,
           mem_per_cpu=None, mem_total=None, gpus_per_node=None, time=None,
           queue=None, account=None, name=None, targets=[], constraint=None,
           extra_options=None):
    '''Submit a job to one or more remote queuing systems.

    Options specified on the command line override defaults from global
    `~/.shotgun.yaml` or project `shotgun.yaml` files.

    '''

    job_root = load_job_root_config(ctx)

    if len(targets) == 0:
        targets = ctx.default_targets

    job_dir = os.getcwd()
    rel_job_dir = os.path.relpath(job_dir, job_root)

    job_script = os.path.relpath(job_script, job_dir)
    job_script_path = PurePath(job_script)
    if not (job_script_path.parts[0] == '..'
            or job_script_path.parts[0] == '.'):
        job_script = os.path.join('.', job_script)

    import shotgun.database as db
    jobid = db.add_job(job_dir, db=ctx.VAULT)

    if name is None:
        name = '_'.join(rel_job_dir.split('/')[::-1])

    from shotgun.job_logger import Job
    curjob = Job(ctx, job_dir, jobid)

    from shotgun.remote_agent import RemoteAgent

    for target_name, target_attr in iteritems(ctx.targets):
        if target_name in targets:
            tagent = RemoteAgent(ctx, target_name, target_attr)
            try:
                res = tagent.sync_to_remote(target_attr['local_asset_dir'],
                                            target_attr['asset_dir'])
            except KeyError:
                pass

            generate_util(ctx, target=target_name, job_dir=job_dir)
            target_job_dir = os.path.join(target_attr['job_root'], rel_job_dir)
            res = tagent.sync_to_remote(job_dir, target_job_dir,
                                        exclude=ctx.upload_excludes)
            res = tagent.submit(target_job_dir, job_script=job_script,
                                nodes=nodes, cpus_per_node=cpus_per_node,
                                mem_per_cpu=mem_per_cpu, mem_total=mem_total,
                                gpus_per_node=gpus_per_node,
                                time=time, queue=queue, account=account,
                                name=name, constraint=constraint,
                                extra_options=extra_options)

            curjob.set_submitted(target_name, res)
            targets.remove(target_name)

    if len(targets) > 0:
        _logger.warning('Ignore targets: %s', ','.join(targets))
        _logger.warning('Available targets: %s', ','.join(
            [t for t in ctx.targets]
        ))


@task
def upload_asset(ctx, target):
    load_job_root_config(ctx)
    target_attr = ctx.targets[target]

    from shotgun.remote_agent import RemoteAgent
    tagent = RemoteAgent(ctx, target, target_attr)
    tagent.sync_to_remote(target_attr['local_asset_dir'],
                          target_attr['asset_dir'])


@task
def upload_job(ctx, target):
    job_root = load_job_root_config(ctx)
    target_attr = ctx.targets[target]

    job_dir = os.getcwd()
    rel_job_dir = os.path.relpath(job_dir, job_root)
    target_job_dir = os.path.join(target_attr['job_root'], rel_job_dir)

    from shotgun.remote_agent import RemoteAgent
    tagent = RemoteAgent(ctx, target, target_attr)
    generate_util(ctx, target=target, job_dir=job_dir)
    tagent.sync_to_remote(job_dir, target_job_dir,
                          exclude=ctx.upload_excludes)


ns = Collection.from_module(sys.modules[__name__], name=None)
program = Program(version=APP_VERSION, namespace=ns,
                  config_class=ShotgunConfig)


if __name__ == '__main__':
    import sys

    logger = setup_logger()
    program.run(sys.argv)
