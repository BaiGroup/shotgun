# Shotgun

## Requirements

Remote machine: should be minimum; Shell, Python?

## Components

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
