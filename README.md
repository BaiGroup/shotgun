# Shotgun

Shotgun is a job management tool that streamlines file syncing and job
submission to HPC systems. It submits the same job to multiple remote
queuing systems (SLURM, PBS, LSF) at once — "shotgun" submission — and
can keep only the first job that starts running, canceling the rest.

## Quick start

```bash
pip install -e .
pip install flask          # only needed for the pingback server

shotgun init               # create ~/.shotgun.yaml + SQLite vault
shotgun new-project        # create shotgun.yaml in the project root
shotgun submit -c 8 -m 5200 -n 1 -t 24 -r bridges -q RM-shared -j ./sub.sh
shotgun check-all -c -s    # check all jobs, cancel siblings, sync back
```

## Documentation

- [docs/ARCHITECTURE.md](docs/ARCHITECTURE.md) — internal design and
  data flows
- [AGENTS.md](AGENTS.md) — codebase guide for AI agents and contributors
- [TODO.md](TODO.md) — prioritized action items
- User guide: <https://wiki.bai.group/meta/Shotgun_job_management_system>
  (internal wiki) — setup, basic workflow, bundling/cycling jobs,
  troubleshooting, HPC usage notes

## Original design notes

### Requirements

Remote machine: should be minimum; Shell, Python?

### Components

### Command-Line Interface

#### Submitter

* Sync program directories
* Sync job directory
* Submit the job to all configured systems+queues
* Log job in job directory
* Record job in global database

#### Maintenance

* Check job status periodically
* Sync job directories periodically

### Remote Agents

#### Queue Agent

* Submit, hold, cancel jobs
* Query job status

#### Sync Agent

Transfer only if files have been modified

### Job Logger

 YAML; possible states:
* pre: queued, dependency\_hold, user\_hold, system\_hold
* running
* post: completed, failed, canceled, exited, submit\_failed

### Job Database

Maintain a database of all jobs; sqlite3

### Net Responder

Allow remote jobs to ping back, and respond to certain events.

### Job Script

* Exit if job already started on another system+queue
* Ping back: to start or exit

#### Proxy

Establish connection via frontend nodes if necessary
