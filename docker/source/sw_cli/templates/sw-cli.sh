#!/bin/bash -e
if [ -t 0 ] ; then DOCKER_OPTIONS="$DOCKER_OPTIONS -t"; fi
docker pull docker.socialwifi.com/sw-cli
docker run --rm -i $DOCKER_OPTIONS \
    -v /:/hostfs \
    -w="/hostfs$PWD" \
    -e HOST_UID=$UID \
    docker.socialwifi.com/sw-cli "$@"
