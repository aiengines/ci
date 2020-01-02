#!/bin/bash

CMD=$1
BUILD=$2

CACHE_LOC=/drone/src/.ccache
S3BUCKET=s3://drone-ccache

if [ -z "$BUILD" ]; then
	echo "You must provide a build name (cpu/cpu-mkldnn/gpu/gpu-mkldnn)"
	exit
fi


if [ "$CMD" == "pull" ]; then
	aws s3 sync $S3BUCKET/ccache-$BUILD $CACHE_LOC --no-progress --quiet
elif [ "$CMD" == "push" ]; then
	aws s3 sync $CACHE_LOC $S3BUCKET/ccache-$BUILD --delete --no-progress --quiet
	rm -rf $CACHE_LOC
else
	echo "Unknown command '$CMD'"
	exit
fi


