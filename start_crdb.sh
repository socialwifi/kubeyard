#start-single-node --insecure --host=localhost --logtostderr


docker run -d \
  --name=roach-single \
  cockroachdb/cockroach:v22.2.19 start-single-node \
  --insecure \
  --host=localhost
