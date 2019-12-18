#!/bin/bash

. ./drone_settings

docker run \
  --volume=/var/lib/drone:/data \
  -e DRONE_RUNNER_CAPACITY=${DRONE_RUNNER_CAPACITY} \
  -e DRONE_AGENTS_ENABLED=true \
  -e DRONE_GITHUB_SERVER=https://github.com \
  -e DRONE_GITHUB_CLIENT_ID=${DRONE_GITHUB_CLIENT_ID} \
  -e DRONE_GITHUB_CLIENT_SECRET=${DRONE_GITHUB_CLIENT_SECRET} \
  -e DRONE_RPC_SECRET=${DRONE_RPC_SECRET} \
  -e DRONE_SERVER_HOST=${DRONE_SERVER_HOST} \
  -e DRONE_SERVER_PROTO=${DRONE_SERVER_PROTO} \
  -e DRONE_USER_CREATE=username:joe,admin:true \
  --publish=80:80 \
  --publish=443:443 \
  --restart=always \
  --detach=true \
  --name=drone \
  drone/drone:1

