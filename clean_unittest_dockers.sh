#!/bin/bash
docker ps -a | grep unittest- | sed -e 's/.*\(unittest-[0-9]*\).*/\1/' | xargs -r docker rm
