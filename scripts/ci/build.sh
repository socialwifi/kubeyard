#!/bin/bash -e
MAIN_DIRECTORY=$(pushd "$(dirname "${BASH_SOURCE[0]}")" > /dev/null; git rev-parse --show-toplevel; popd > /dev/null)

VERSION=${1?"Provide version number"}

docker build -t docker.socialwifi.com/sw-cli:$VERSION "$MAIN_DIRECTORY/docker"
