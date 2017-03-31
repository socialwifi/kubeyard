#!/bin/bash -ex
ember build -prod --output-path="/tmp/statics" >/dev/null
tar -c /tmp/statics
