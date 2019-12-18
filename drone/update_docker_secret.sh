#!/bin/bash

export PATH=/usr/local/bin:$PATH

# TODO get these from secret manager
export DRONE_TOKEN=xxxxxxxxx
export DRONE_SERVER=http://drone-server-uri
export DRONE_AUTOSCALER=http://drone-server-uri:8080

REPO="josephevans/incubator-mxnet"

# get updated credentials and store in ~/.docker/config.json
$(aws ecr get-login --no-include-email --region us-west-2)

#drone secret add --name dockerconfigjson --data @$HOME/.docker/config.json --allow-pull-request $REPO
drone secret update --name dockerconfigjson --data @$HOME/.docker/config.json --allow-pull-request $REPO



