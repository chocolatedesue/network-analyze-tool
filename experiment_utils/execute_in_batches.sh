#!/usr/bin/env bash
# Execute a given command on a percentage of containers by prefix every interval
# until all target containers have executed the command once.
#
# - Default interval: 10s
# - Percentage per batch: configurable (default 20%)
# - Container selection:
#     * Prefer parsing prefix (e.g., clab-ospfv3-torus5x5) -> width=5 height=5
#     * Or --size SIZE (square: SIZE x SIZE)
#     * Or --dims WIDTHxHEIGHT (rectangular)
#     * Fallback to docker/podman ps filter by name
# - Runtime: docker (default) or podman via --runtime
# - Parallelism within a batch: --parallel (default 1, sequential by default)
# - Detach mode inside container: --detach (use exec -d)
# - Dry run supported
#
# Examples:
#   bash experiment_utils/execute_in_batches.sh clab-ospfv3-torus5x5 "echo hello" \
#       --percent 25 --interval 10 --parallel 8
#
#   # Using podman and detaching the command inside containers
#   bash experiment_utils/execute_in_batches.sh clab-ospfv3-grid5x5 "sleep 600" \
#       --percent 10 --interval 5 --runtime podman --detach
#
set -euo pipefail

usage() {
  cat <<'USAGE'
Usage:
  execute_in_batches.sh <prefix> <command> [options]

Options:
  -p, --percent PCT          Percentage of containers per batch (1-100). Default: 20
  -i, --interval SEC         Interval between batches in seconds. Default: 10
  --size N                   Square dimension (N x N) if not in prefix
  --dims WxH                 Rectangular dimensions, e.g., 5x5
  -r, --runtime RUNTIME      docker (default) or podman
  --parallel N               Max concurrent execs per batch. Default: 1 (sequential)
  -d, --detach               Run command detached inside container (exec -d)
  --dry-run                  Print what would run, don't execute
  -h, --help                 Show this help

Notes:
  - Containers are detected by name starting with "<prefix>-router_".
  - If dimensions are not provided and not parseable from prefix, will fallback
    to listing running containers by runtime.
USAGE
}

PREFIX=""
CMD=""
PERCENT=20
INTERVAL=10
RUNTIME="docker"
PARALLEL=1
DETACH=0
DRY_RUN=0
WIDTH=""
HEIGHT=""

# Parse args
if [[ $# -lt 2 ]]; then
  usage
  exit 1
fi

PREFIX="$1"; shift
CMD="$1"; shift

while [[ $# -gt 0 ]]; do
  case "$1" in
    -p|--percent)
      PERCENT="${2:-}"; shift 2;;
    --percent=*)
      PERCENT="${1#*=}"; shift;;
    -i|--interval)
      INTERVAL="${2:-}"; shift 2;;
    --interval=*)
      INTERVAL="${1#*=}"; shift;;
    --size)
      WIDTH="${2:-}"; HEIGHT="${2:-}"; shift 2;;
    --size=*)
      N="${1#*=}"; WIDTH="$N"; HEIGHT="$N"; shift;;
    --dims)
      D="${2:-}"; WIDTH="${D%x*}"; HEIGHT="${D#*x}"; shift 2;;
    --dims=*)
      D="${1#*=}"; WIDTH="${D%x*}"; HEIGHT="${D#*x}"; shift;;
    -r|--runtime)
      RUNTIME="${2:-}"; shift 2;;
    --runtime=*)
      RUNTIME="${1#*=}"; shift;;
    --parallel)
      PARALLEL="${2:-}"; shift 2;;
    --parallel=*)
      PARALLEL="${1#*=}"; shift;;
    -d|--detach)
      DETACH=1; shift;;
    --dry-run)
      DRY_RUN=1; shift;;
    -h|--help)
      usage; exit 0;;
    *)
      echo "Unknown option: $1" >&2
      usage
      exit 1;;
  esac
done

# Validate numeric args
is_int() { [[ "$1" =~ ^[0-9]+$ ]]; }

if ! is_int "$PERCENT" || (( PERCENT < 1 || PERCENT > 100 )); then
  echo "percent must be integer in [1,100], got: $PERCENT" >&2
  exit 1
fi
if ! is_int "$INTERVAL" || (( INTERVAL < 0 )); then
  echo "interval must be non-negative integer seconds, got: $INTERVAL" >&2
  exit 1
fi
if ! is_int "$PARALLEL" || (( PARALLEL < 1 )); then
  echo "parallel must be >=1, got: $PARALLEL" >&2
  exit 1
fi

# Try to parse WxH from prefix if not specified
if [[ -z "$WIDTH" || -z "$HEIGHT" ]]; then
  if [[ "$PREFIX" =~ ([0-9]+)x([0-9]+)$ ]]; then
    WIDTH="${BASH_REMATCH[1]}"; HEIGHT="${BASH_REMATCH[2]}"
  fi
fi

# Build container list
containers=()

if [[ -n "$WIDTH" && -n "$HEIGHT" ]] && is_int "$WIDTH" && is_int "$HEIGHT"; then
  # Generate names from dimensions (zero-padded two digits)
  for ((x=0; x<WIDTH; x++)); do
    for ((y=0; y<HEIGHT; y++)); do
      printf -v name "%s-router_%02d_%02d" "$PREFIX" "$x" "$y"
      containers+=("$name")
    done
  done
else
  # Fallback to listing running containers by runtime
  case "$RUNTIME" in
    docker)
      mapfile -t containers < <(docker ps --format '{{.Names}}' | grep -E "^${PREFIX}-router_[0-9]{2}_[0-9]{2}$" || true)
      ;;
    podman)
      mapfile -t containers < <(podman ps --format '{{.Names}}' | grep -E "^${PREFIX}-router_[0-9]{2}_[0-9]{2}$" || true)
      ;;
    *)
      echo "Unknown runtime: $RUNTIME (use docker or podman)" >&2
      exit 1
      ;;
  esac
fi

TOTAL=${#containers[@]}
if (( TOTAL == 0 )); then
  echo "No containers found for prefix: $PREFIX" >&2
  exit 1
fi

# Compute batch size (ceil)
BATCH_SIZE=$(( (TOTAL * PERCENT + 99) / 100 ))
if (( BATCH_SIZE < 1 )); then BATCH_SIZE=1; fi

exec_cmd() {
  local container="$1"
  local cmd="$2"
  local runtime="$3"
  local detach_flag="$4"

  if (( DRY_RUN )); then
    if (( detach_flag )); then
      echo "DRY-RUN: $runtime exec -d $container sh -lc \"$cmd\""
    else
      echo "DRY-RUN: $runtime exec $container sh -lc \"$cmd\""
    fi
    return 0
  fi

  if (( detach_flag )); then
    $runtime exec -d "$container" sh -lc "$cmd"
  else
    $runtime exec "$container" sh -lc "$cmd"
  fi
}

# Determine the container engine binary
ENGINE="docker"
if [[ "$RUNTIME" == "podman" ]]; then
  ENGINE="podman"
fi

# Iterate batches
index=0
batch_num=1
while (( index < TOTAL )); do
  end=$(( index + BATCH_SIZE ))
  if (( end > TOTAL )); then end=$TOTAL; fi
  echo "[Batch $batch_num] Executing on containers $((index+1))..$end of $TOTAL (batch size=$BATCH_SIZE, interval=${INTERVAL}s)"

  # Batch execution with simple parallelism
  running=0
  for ((i=index; i<end; i++)); do
    ctn="${containers[$i]}"
    if (( PARALLEL > 1 )); then
      exec_cmd "$ctn" "$CMD" "$ENGINE" "$DETACH" &
      (( running++ ))
      if (( running >= PARALLEL )); then
        wait -n || true
        (( running-- ))
      fi
    else
      exec_cmd "$ctn" "$CMD" "$ENGINE" "$DETACH"
    fi
  done
  # Wait remaining background jobs in this batch
  wait || true

  (( index = end ))
  (( batch_num++ ))
  if (( index < TOTAL )); then
    echo "Sleeping $INTERVAL seconds before next batch..."
    sleep "$INTERVAL"
  fi
done

echo "All $TOTAL containers have executed the command."

