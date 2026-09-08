#!/usr/bin/env bash
set -euo pipefail
entry_dir="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")/.." && pwd)"
workspace_dir="$(cd -- "${entry_dir}/../.." && pwd)"
if [[ $# -lt 1 || "$1" == --help || "$1" == -h ]]; then
  printf '%s\n' 'Usage: start_robot.sh ROBOT_ID [name:=value ...]' \
    'Start an imported and applied manager configuration. ROS_DOMAIN_ID defaults to 14.'
  exit 0
fi
robot_id=$1
shift
if [[ ! "$robot_id" =~ ^[A-Za-z0-9][A-Za-z0-9_.-]*$ ]]; then
  printf '%s\n' 'Invalid robot ID.' >&2
  exit 2
fi
if [[ ! -f "${workspace_dir}/install/setup.bash" ]]; then
  printf '%s\n' 'Workspace is not built; run workspace.sh build first.' >&2
  exit 2
fi
set +u
source /opt/ros/humble/setup.bash
source "${workspace_dir}/install/setup.bash"
set -u
export ROS_DOMAIN_ID="${ROS_DOMAIN_ID:-14}"
exec ros2 launch humanoid_manager managed_robot.launch.py "robot_id:=${robot_id}" "$@"
