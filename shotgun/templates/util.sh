ASSET_DIR="${asset_dir}"
TARGET="${target_name}"

trap_append() {
  local _cmd=$1
  shift
  local _signal
  for _signal in "$@"; do
    trap -- "$(
      extract_trap_cmd() { printf '%s\n' "$3"; }
      eval "extract_trap_cmd $(trap -p "${_signal}")"
      printf '%s\n' "${_cmd}"
    )" "${_signal}"
  done
}

declare -f -t trap_append

set_job_completed() {
    echo 'Echo server: finishing ...'
    curl -s -L --connect-timeout 30 --max-time 60 -u token:$token $server/$jobid/$TARGET/ended
    echo
    echo
}

set_job_started() {
    if [ "$(curl -s -L --connect-timeout 30 --max-time 60 -u token:$token $server/$jobid/should-exit)" == 'True' ]; then
        echo "$jobid is running, exiting now."
        exit
    fi

    echo 'Echo server: starting ...'
    curl -s -L --connect-timeout 30 --max-time 60 -u token:$token $server/$jobid/$TARGET/started
    echo
    echo

    trap_append set_job_completed EXIT
}

[ "${skip_pingback}" == 'false' ] && set_job_started
