#!/bin/bash -e
VERSION=${1?"Provide version number"}

docker tag docker.socialwifi.com/sw-cli:$VERSION docker.socialwifi.com/sw-cli:latest
docker push docker.socialwifi.com/sw-cli:$VERSION
docker push docker.socialwifi.com/sw-cli:latest
