# TODO

Prioritized action items for the Shotgun codebase. Derived from the
analysis in [AGENTS.md](AGENTS.md) and
[docs/ARCHITECTURE.md](docs/ARCHITECTURE.md).

## Urgent — correctness bugs

- [ ] **Add `flask` to `install_requires`** in [setup.py](setup.py). The
  pingback server ([shotgun/server/](shotgun/server/)) breaks on a fresh
  install. One-line fix.
- [ ] **Fix `delete_excluded` crash** —
  [remote_agent.py](shotgun/remote_agent.py) reads
  `self.context.delete_excluded`, but it is not in
  `ShotgunConfig.global_defaults()`. Any rsync upload without a project
  config setting it will raise. Add `'delete_excluded': False` to the
  defaults in [commands.py](shotgun/commands.py).
- [ ] **Fix racy `chdir` + threads** — `check_all_parallel` in
  [commands.py](shotgun/commands.py) runs `check_this` (which calls
  `os.chdir`) in a `ThreadPoolExecutor`. Parallel checks of different job
  directories can silently operate on the wrong directory and corrupt
  `job.yaml` state. Refactor `check_this`/`Job` to take paths instead of
  changing the process-wide cwd.
- [ ] **Fix mutable default arguments** — `submit()` mutates
  `targets=[]` via `targets.remove(...)`; `[]` defaults also appear in
  `check_all`, `check_this`, and the rsync methods. Switch to `None`
  defaults throughout.

## High — fragile under specific conditions

- [ ] **Fix SSH command quoting** — `Connection.run` wraps remote
  commands in single quotes and `shlex.split`s the result; remote
  commands containing single quotes break (and are an injection vector if
  job names/paths are user-influenced). Pass the command as an argv list
  and send the payload via stdin or base64.
- [ ] **Finish the LSF parser** — [scheduler/lsf.py](shotgun/scheduler/lsf.py)
  has `NON_EXISTENT_*` placeholder keys in `_QUERY_MAP` and year-less
  `datetime.strptime` for run time (breaks across New Year). Needs real
  `bjobs -UF` output samples (like [timeout.txt](timeout.txt) provides
  for SLURM) and tests.
- [ ] **Pingback token over plain HTTP** — the server uses Basic auth
  with a shared token. Fine for a trusted LAN, but document the risk and
  add TLS/reverse-proxy guidance before exposing the port broadly.

## Medium — maintainability

- [ ] **Add a minimal test suite** — currently zero tests. Start with the
  pure parsers: `parse_query_output` / `parse_submit_output` for all
  three schedulers (fixtures from `scontrol` / `qstat` / `bjobs` output),
  plus `time_in_seconds` and `convert_size_to_MB`.
- [ ] **Decide the Python 2/3 story** — the `future` shim (`iteritems`,
  `listitems`) adds friction everywhere; [setup.py](setup.py) classifiers
  only claim up to Python 3.6. A clean Py3-only pass would simplify
  everything.
- [ ] **Silent-failure audit** — `@failable` converts remote errors into
  `None`. Grep-audit every `RemoteAgent` call site to confirm the result
  is null-checked.
- [ ] **Add `requirements.txt` / dev extras** and note that
  `shotgun.egg-info/` should not be committed.

## Low

- [x] **Flesh out [README.md](README.md)** — done: overview, quick
  start, and links to [AGENTS.md](AGENTS.md) and
  [docs/ARCHITECTURE.md](docs/ARCHITECTURE.md).
- [ ] **SQLite concurrency** — if the server sees real traffic, enable
  WAL mode on the vault.

## Suggested first PR

Items 1–4 from *Urgent*: the `flask` dependency, `delete_excluded`
default, and mutable-default fixes are tiny and safe; the `chdir`/thread
race is the only item that can silently corrupt job state, so it deserves
priority despite being a larger change.
