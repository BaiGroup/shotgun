# AGENTS.md — Shotgun Codebase Guide

Guidance for AI agents and developers working in this repository.

Companion doc: [docs/ARCHITECTURE.md](docs/ARCHITECTURE.md) (internals).
End-user tutorial lives on the internal wiki:
<https://wiki.bai.group/meta/Shotgun_job_management_system> (not
committed to this repo).

## Project Overview

**Shotgun** is a Python CLI tool for submitting and managing computational
jobs across multiple remote HPC queuing systems (SLURM, PBS, LSF)
simultaneously — "shotgun" submission. It syncs job directories to remote
clusters via `rsync`/`ssh`, submits to all configured targets, tracks job
state in a local SQLite database and per-job YAML logs, and supports an
optional Flask "pingback" server so remote jobs can report
started/finished events (first job to start wins; others are canceled).

- Package name / CLI command: `shotgun`
- Version: `0.1.0` (defined in [shotgun/__init__.py](shotgun/__init__.py))

## Tech Stack & Dependencies

- Python 2/3 compatible code (uses `future`: `iteritems`, `listitems`,
  `listvalues`, `from __future__ import ...`). Modernize carefully.
- Dependencies (from [setup.py](setup.py) `install_requires`):
  `future`, `invoke`, `ruamel.yaml`, `SQLAlchemy`
- **Undeclared dependency**: `flask` is required by `shotgun/server/` but
  missing from `install_requires`.
- External tools required at runtime: `ssh`, `rsync` (remote operations),
  plus scheduler CLIs on remotes (`sbatch`/`scontrol`/`scancel`, `qsub`/
  `qstat`/`qdel`, `bsub`/`bjobs`/`bkill`).
- CLI framework: **invoke** (`Program`, `Collection`, `@task`) — tasks are
  the CLI subcommands.
- No test suite, no CI, no lint config, no `requirements.txt` currently
  exist in this repo.

## Build / Install / Run Commands

```bash
pip install -e .            # install package + `shotgun` console script
pip install flask           # needed only for the pingback server

shotgun init                # create ~/.shotgun.yaml user config + SQLite vault
shotgun new-project         # create shotgun.yaml (job-root config) in cwd
shotgun submit --job-script sub.sh --targets host1 host2
shotgun check-this          # check job in current directory
shotgun check-all --cancel --sync   # check all active jobs
shotgun list-jobs --state active
FLASK_APP=shotgun.server flask run --host 0.0.0.0 --port 8080  # server
```

Entry point: `shotgun = shotgun.commands:program.run` (see
[setup.py](setup.py)).

## Repository Layout

| Path | Purpose |
|---|---|
| [shotgun/commands.py](shotgun/commands.py) | All CLI tasks (submit, check_this, check_all, download, hold, release, cancel_job, init, new_project, list_jobs, bundle, generate_util, set_started, set_finished, upload_asset, upload_job); `ShotgunConfig` (invoke Config subclass with defaults); `program` entry point |
| [shotgun/config.py](shotgun/config.py) | YAML config read/write; `find_job_root_config()` walks up from cwd to find `shotgun.yaml`; user config at `~/.shotgun.yaml` |
| [shotgun/database.py](shotgun/database.py) | SQLAlchemy + SQLite "vault": single `jobs` table (`id`, `created_at`, `updated_at`, `jobdir`, `active`, `started`); session helpers |
| [shotgun/job_logger.py](shotgun/job_logger.py) | `Job` class wrapping per-job `job.yaml` log; target states; syncs state to DB |
| [shotgun/remote_agent.py](shotgun/remote_agent.py) | `Connection` (ssh subprocess wrapper), `RemoteAgent` (rsync sync, submit/query/hold/cancel/release via scheduler module) |
| [shotgun/scheduler/](shotgun/scheduler/) | Scheduler adapters: [slurm.py](shotgun/scheduler/slurm.py), [pbs.py](shotgun/scheduler/pbs.py), [lsf.py](shotgun/scheduler/lsf.py). Loaded dynamically by name |
| [shotgun/server/](shotgun/server/) | Flask pingback server: [responder.py](shotgun/server/responder.py) routes, [basic_auth.py](shotgun/server/basic_auth.py) token auth |
| [shotgun/util.py](shotgun/util.py) | Helpers: `failable` decorator, `time_in_seconds`, token generation, template utilities |
| [shotgun/exception.py](shotgun/exception.py) | `ShotgunError` base exception |
| [shotgun/templates/](shotgun/templates/) | `user_config.yaml`, `job_root.yaml`, `util.sh` (pingback script), `shotgun.server.plist` (macOS launchd) |
| [docs/ARCHITECTURE.md](docs/ARCHITECTURE.md) | Module-level internals and data flows |
| [timeout.txt](timeout.txt) | Sample `scontrol show job` output (reference for SLURM parser) |

## CLI Flags

Invoke auto-assigns short flags for task parameters. The established
user-facing set (used throughout the user guide) is:

| Short | Long | Meaning |
|---|---|---|
| `-c` | `--cpus-per-node` | CPUs per node |
| `-m` | `--mem-per-cpu` | Memory per CPU (e.g. `5200` MB) |
| `-n` | `--nodes` | Number of nodes |
| `-t` | `--time` | Walltime (hours) |
| `-r` | `--targets` | Remote targets (iterable) |
| `-q` | `--queue` | Queue/partition |
| `-j` | `--job-script` | Batch script to submit |

If you rename task parameters, these short flags change — that would
break every user script and the documentation.

## Configuration Model (three layers, merged by invoke)

1. `ShotgunConfig.global_defaults()` — `SERVER`, `TOKEN`, `VAULT`
   (`~/shotgun.sqlite`), `targets`, `default_targets`, exclude lists.
2. User config `~/.shotgun.yaml` — created by `shotgun init` from
   [shotgun/templates/user_config.yaml](shotgun/templates/user_config.yaml);
   defines `targets` (per-cluster: `scheduler`, `cpus_per_node`, `queue`,
   `host`, `skip_pingback`).
3. Project config `shotgun.yaml` at the *job root* — created by
   `shotgun new-project` from
   [shotgun/templates/job_root.yaml](shotgun/templates/job_root.yaml);
   per-target `job_root` (remote path), `local_asset_dir`, `asset_dir`,
   `job_script`. Found by walking up directories from cwd
   (`find_job_root_config`), so most commands must run inside a job tree.

Key target attributes: `scheduler` (`slurm`/`pbs`/`lsf` — must match a
module name in `shotgun/scheduler/`), `host` (defaults to target name,
typically an SSH config alias), `job_root`, `asset_dir`/`local_asset_dir`,
`skip_pingback`, `command_decorator` (optional shell wrapper template).

## Job State Model

Two coordinated stores:

- **Per-job log** `job.yaml` in the job directory (`Job` in
  [shotgun/job_logger.py](shotgun/job_logger.py)): maps target name →
  `{job_qid, state}`.
- **Global DB** (SQLite): one row per job directory with `active` /
  `started` flags.

Normalized job states: `queued`, `dependency_hold`, `user_hold`,
`system_hold`, `running`, `suspended` (active); `completed`, `failed`,
`canceled`, `exited`, `submit_failed`, `killed` (terminal).
`Job.set_job_state()` updates the DB automatically: any running target →
`started=True`; no active targets → finished.

Submission flow: register job dir in DB → per target: rsync assets →
generate `util.sh` pingback script → rsync job dir → run submit command
via ssh → record `job_qid`/state in `job.yaml`.

Pingback flow (when `skip_pingback: False`): remote job runs generated
`util.sh`, which curls `/<jobid>/<target>/started`; server cancels sibling
targets and can rsync results back; on EXIT trap it calls
`/<jobid>/<target>/ended`; `/<jobid>/should-exit` lets late starters
self-terminate. User job scripts are expected to `source util.sh`
(see the [user guide on the internal
wiki](https://wiki.bai.group/meta/Shotgun_job_management_system)).

## Usage Conventions (from the field)

- **Symlinks in job directories must be relative.** `submit` rsyncs the
  job dir to the remote `job_root`; absolute symlinks break because the
  referenced path does not exist on the remote. Large shared executables
  are intentionally *outside* `asset_dir` and transferred manually.
- **`bundle` template markers**: `bundle` replicates the section between
  `#>>>BEGIN<<<` and `#>>>END<<<` once per job directory listed in the
  `--dirs` file, substituting `$job_dir` (a `string.Template`
  placeholder). Bundled and cycling (`qcycle-*`) job patterns are user
  scripts, not shotgun features — see the [user guide on the internal
  wiki](https://wiki.bai.group/meta/Shotgun_job_management_system).
- **`-c` on `check-*` means "cancel siblings"**, not "cancel this job":
  keep the earliest/longest-running target, cancel the rest
  ("shotgun mode"). Users commonly run `check-all --sync --cancel` from
  cron every 30 min.
- **Full-node charging**: many HPC queues (Bridges2 RM, Expanse compute,
  Perlmutter regular, ...) charge for whole nodes; defaults in
  `~/.shotgun.yaml` should point at shared queues so omitting `-q` is
  safe.

## Coding Conventions

- Keep `from __future__ import unicode_literals` style headers and
  `future.utils` imports consistent with existing files until a deliberate
  2→3 cleanup is done.
- Errors in remote operations are swallowed by the `@failable`
  decorator (returns `None`, logs exception) — always handle `None`
  returns from `RemoteAgent` methods.
- Scheduler adapters expose a fixed function surface:
  `submit_command`, `cancel_command`, `hold_command`, `release_command`,
  `query_command`, `parse_submit_output`, `parse_query_output`, and
  `QUERY_ATTRIBUTES`. New schedulers must implement all of these and
  normalize states to the shared vocabulary above.
- YAML I/O goes through `shotgun.config` (`ruamel.yaml`), not `yaml`
  directly.

## Known Issues / Gotchas

- `flask` missing from `install_requires` in [setup.py](setup.py).
- `RemoteAgent.rsync_to_remote` reads `self.context.delete_excluded`, but
  `delete_excluded` is not in `ShotgunConfig` defaults — only settable via
  project config; will raise if unset.
- Mutable default arguments (`targets=[]`, `exclude=[]`) are used in
  several functions (`check_all`, `check_this`, `submit`, rsync methods).
  `submit()` mutates the `targets` list (`targets.remove(...)`).
- Many tasks call `os.chdir(job_dir)` — process-wide side effect; be
  careful when adding concurrent code (`check_all_parallel` already
  combines threads with `chdir`, which is racy).
- `Connection.run` builds ssh commands via string formatting and
  `shlex.split` — quoting of remote commands containing single quotes is
  fragile.
- `scheduler/lsf.py` `parse_query_output` has placeholder
  `NON_EXISTENT_*` map entries and year-less date parsing (fragile around
  New Year).
- `job_ended`/`job_started` in [shotgun/commands.py](shotgun/commands.py)
  spawn threads that construct a fresh invoke `Context`; server and CLI
  share the same SQLite vault file.

## Where to Make Common Changes

- New CLI command: add `@task` function in
  [shotgun/commands.py](shotgun/commands.py) (auto-collected via
  `Collection.from_module`).
- New scheduler: add module in [shotgun/scheduler/](shotgun/scheduler/)
  implementing the adapter surface above.
- New server endpoint: [shotgun/server/responder.py](shotgun/server/responder.py)
  (protect with `@basic_auth`).
- Config defaults: `ShotgunConfig.global_defaults()` in
  [shotgun/commands.py](shotgun/commands.py).
