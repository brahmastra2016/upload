#!/usr/bin/env bash

CURR_DIR="$( cd "$( dirname "${BASH_SOURCE[0]}" )" && pwd )"

# install docker-compose
is_docker_compose_present=`docker-compose -h &> /dev/null; echo $?`
if [[ $is_docker_compose_present -ne 0 ]];
then
    sudo curl -L https://github.com/docker/compose/releases/download/1.16.1/docker-compose-`uname -s`-`uname -m` -o /usr/local/bin/docker-compose
    sudo chmod +x /usr/local/bin/docker-compose
    docker-compose --version
fi

#install colorama
pip install colorama

#install jinja2
pip install Jinja2

docker_dir=$CURR_DIR/docker_images
mkdir -p $docker_dir
function fetch(){
    docker pull registry.juniper.net/iceberg/jfit-images/$1:$2 && \
    docker tag registry.juniper.net/iceberg/jfit-images/$1:$2 $1:$2 && \
    docker image save -o $docker_dir/$1.tar.gz $1:$2 &
}
# fetch jfit_core
fetch jfit_core 0.1
# fetch jfit_mgd
fetch jfit_mgd DCB
# fetch jfit_fluentd
fetch jfit_fluentd v0.12
# fetch jfit_kapacitor
fetch jfit_kapacitor 1.3.3
# fetch jfit_influxdb
fetch jfit_influxdb 1.3.6
# fetch jfit_telegraf
fetch jfit_telegraf 1.0.0-beta1-1178-gd2e24845-1 
# fetch iagent
fetch jfit_iagent latest
