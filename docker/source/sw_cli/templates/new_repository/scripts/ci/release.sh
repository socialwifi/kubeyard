#!/bin/bash -e
MAIN_DIRECTORY=$(pushd "$(dirname "${BASH_SOURCE[0]}")" > /dev/null; git rev-parse --show-toplevel; popd > /dev/null)

source $MAIN_DIRECTORY/scripts/env.sh
VERSION=${1?"Provide version number"}

docker tag $IMAGE:$VERSION $IMAGE:latest
docker push $IMAGE:$VERSION
docker push $IMAGE:latest
