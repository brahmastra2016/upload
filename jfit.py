#! /usr/bin/env python
from __future__ import print_function

import argparse
import json
import os
import shlex
import shutil
import subprocess
import time
from distutils.dir_util import copy_tree
from distutils.errors import DistutilsFileError

import colorama
import jinja2

DEP_SCRIPT = 'install_dep.sh'
DATA_DIR = 'data'
FILE_DIR_PATH = os.path.dirname(os.path.realpath(__file__))
ETC_DIR_PATH = os.path.join(FILE_DIR_PATH, 'etc')
MGD_IMAGE = 'jfit_mgd.tar.gz'
CONFIG_LOCATION = 'config'
GROUP_DIR = os.path.join(ETC_DIR_PATH, 'core_output')
COMPOSE_SNIPPET_DIR = os.path.join(FILE_DIR_PATH, 'compose_files')
GROUP_ENV_FILE = 'source.env'
SERVICE_KEYS = ['JTI_NATIVE_COLLECTOR',
                'JTI_OC_COLLECTOR',
                'RULE_ENGINE',
                'TRAINING_ENGINE',
                'COMMAND_RPC',
                'DATABASE']
DOCKER_IMAGE_DIR = os.path.join(FILE_DIR_PATH, 'docker_images')
PARSE_INPUT_DIR = os.path.join(FILE_DIR_PATH, 'input')


def parse_args():
    '''
    Argument parser for the script
    '''
    arg_parser = argparse.ArgumentParser()
    subparsers = arg_parser.add_subparsers(help='sub-command help',
                                           dest='commands')
    install_parser = subparsers.add_parser(
        'install',
        help='Install jFit')
    remove_parser = subparsers.add_parser(
        'remove',
        help='Remove/Delete services')
    remove_parser.add_argument("group_name",
                               help="Group name. Absence of service name will lead to deletion of all services in the group",
                               type=str)
    remove_parser.add_argument("-s", "--service",
                               help="Name of the service to be removed",
                               type=str)
    parse_parser = subparsers.add_parser('parse',
                                         help='Parse the input data model')
    parse_parser.add_argument('input_file_path',
                              help='Path of input data model')
    parse_parser.add_argument('device_group',
                              help='Device group name')
    parse_parser.add_argument('-i', '--input-dir',
                              help='Input directory location. Keep udf and iagent files here. Defaults to {}'.format(PARSE_INPUT_DIR))
    start_parser = subparsers.add_parser(
        'start',
        help='Start the application for a group')
    start_parser.add_argument("group_name",
                              help="Group name",
                              type=str)
    start_parser.add_argument("-s", "--service",
                              help="Name of service to be started. In the absence of this, all neccessary services would be started",
                              type=str)
    stop_parser = subparsers.add_parser(
        'stop',
        help='Stop the application for a group')
    stop_parser.add_argument("group_name",
                             help="Group name",
                             type=str)
    stop_parser.add_argument("-s", "--service",
                             help="Name of service to be stopped. In the absence of this, all neccessary services would be stopped",
                             type=str)
    restart_parser = subparsers.add_parser(
        'restart',
        help='Restart the application for a group')
    restart_parser.add_argument("group_name",
                                help="Group name",
                                type=str)
    restart_parser.add_argument("-s", "--service",
                                help="Name of service to be restarted. In the absence of this, all neccessary services would be restarted",
                                type=str)
    cli_parser = subparsers.add_parser(
        'cli',
        help='Gain cli access to a service')
    cli_parser.add_argument("group_name",
                            help="Group name",
                            type=str)
    cli_parser.add_argument("service",
                            help="Name of the service",
                            type=str)
    logs_parser = subparsers.add_parser(
        'logs',
        help='Access service logs')
    logs_parser.add_argument("group_name",
                             help="Group name",
                             type=str)
    logs_parser.add_argument("service",
                             help="Name of the service",
                             type=str)
    mgd_parser = subparsers.add_parser(
        'mgd',
        help='Spin up MGD container for writing rules'
    )
    mgd_parser.add_argument('mgd_command',
                            help='Command for container',
                            choices=['start', 'stop', 'cli'],
                            type=str)
    args = arg_parser.parse_args()
    return args


def execute(command_string, color=colorama.Fore.CYAN):
    '''
    Execute the given command string
    '''
    args = shlex.split(command_string)
    print(color+command_string)
    try:
        output = subprocess.check_output(args,
                                         stderr=subprocess.STDOUT)
        output = output.strip()
    except subprocess.CalledProcessError as exc:
        err = "Command {0} exited with code: {1}".\
            format(command_string, exc.returncode)
        err += "\nError: {}".format(exc.output)
        print(colorama.Fore.RED + err)
        raise exc
    else:
        return output


def shell_command(command_string, color=colorama.Fore.CYAN):
    '''
    Execute command in shell mode
    '''
    args = command_string
    print(color+command_string)
    try:
        output = subprocess.call(args,
                                 shell=True,
                                 stderr=subprocess.STDOUT)
    except subprocess.CalledProcessError as exc:
        err = "Command {0} exited with code: {1}".\
            format(command_string, exc.returncode)
        err += "\nError: {}".format(exc.output)
        print(colorama.Fore.RED + err)
        raise exc
    else:
        return output


def get_docker_images(full_path=True):
    '''
    Search docker image directory and return their names or path
    depending on the argument
    '''
    docker_images = [f
                     for f in os.listdir(DOCKER_IMAGE_DIR)
                     if f.startswith('jfit_') and
                     f.endswith('.tar.gz')]
    if full_path:
        docker_images = [os.path.join(DOCKER_IMAGE_DIR, f)
                         for f in docker_images]
    return docker_images


def get_group_dir_path(group_name):
    '''
    Return full path of the group
    '''
    return os.path.join(GROUP_DIR, group_name)


def _get_container_tags(container_image_path):
    cwd = os.getcwd()
    os.chdir(FILE_DIR_PATH)
    image_manifest_file = 'manifest.json'
    untar_command = 'tar -xf {} {}'.format(container_image_path, image_manifest_file)
    execute(untar_command)
    image_manifest_file_path = os.path.join(FILE_DIR_PATH, image_manifest_file)
    tags = json.load(open(image_manifest_file, 'r'))[0]['RepoTags'][0]
    os.remove(image_manifest_file_path)
    os.chdir(cwd)
    return tags


def _create_compose_file(dir_path, compose_snippet_loc=COMPOSE_SNIPPET_DIR):
    # collect service names
    env_file = os.path.join(dir_path, GROUP_ENV_FILE)
    if not os.path.isfile(env_file):
        err = 'Unable to find file: {}'.format(env_file)
        print(colorama.Fore.RED + err)
    with open(env_file, 'r') as fob:
        env_file_content = fob.read()
    # parse env contents
    env_dict = {line.split('=')[0]: line.split('=')[1]
                for line in env_file_content.split()
                if line.strip()}
    for key in env_dict:
        if key.endswith('_LIST'):
            val = env_dict[key][1:-1]
            val = val.split(",")
            env_dict[key] = val
    # directory paths should be without '/' at the end
    env_dict.update({
        'JFIT_ETC_PATH': ETC_DIR_PATH,
        'JFIT_OUTPUT_PATH': GROUP_DIR
    })
    ret_code = 0
    for service_type in env_dict:
        if service_type not in SERVICE_KEYS:
            continue
        service_name = 'jfit_{}'.format(env_dict[service_type])
        service_image_path = os.path.join(DOCKER_IMAGE_DIR, service_name+'.tar.gz')
        if not os.path.isfile(service_image_path):
            err = 'Unable to find docker image: {}'.format(service_image_path)
            ret_code = 1
            break
        service_tag = _get_container_tags(service_image_path)
        if service_tag is None:
            err = 'Unable to extract tags for service: {}'.format(service_name)
            ret_code = 1
            break
        service_tag = service_tag.split(':')
        service = service_tag[0].strip()
        version = service_tag[1].strip()
        jinja_template = '{}.yaml.j2'.format(service)
        if service == 'TRAINING_ENGINE':
            jinja_template = '{}_training.yaml.j2'.format(service)
        jinja_template = os.path.join(compose_snippet_loc, jinja_template)
        if not os.path.isfile(jinja_template):
            err = 'Compose file {} is missing'.format(jinja_template)
            ret_code = 1
            break
        template = None
        with open(jinja_template, 'r') as fob:
            template = fob.read()
        if not template:
            err = 'Compose file {} is empty'.format(jinja_template)
            ret_code = 1
            break
        data = {
            '{}_IMAGE'.format(service.upper()): service,
            '{}_TAG'.format(service.upper()): version
        }
        # remove 'jfit_' from service name
        conf_file_name = service[5:]+'.conf'
        conf_file_path = os.path.join(
            dir_path, service_type.lower(), conf_file_name)
        if os.path.isfile(conf_file_path):
            data['{}_CONF'.format(service.upper())] = conf_file_path
        data.update(env_dict)
        output = jinja2.Template(template).render(env=data)
        # place them inside the group directory
        rendered_compose_location = os.path.join(dir_path,
                                                 '{}.yaml'.format(service))
        with open(rendered_compose_location, 'w') as fob:
            fob.write(output)

    if ret_code != 0:
        print(colorama.Fore.RED + err)
    return ret_code


def _get_compose_files(dir_path):
    yaml_files = [x
                  for x in os.listdir(dir_path)
                  if x.endswith('.yaml')]
    if not yaml_files:
        err = 'Unable to find compose files.\n Please run parse command first!'
        print(colorama.Fore.RED + err)
        return 1
    # for appending -f at the beginning of the first file add an empty element
    return ' -f '.join(['']+yaml_files)


def install(args):
    '''
    Function to install jFit
    '''
    cwd = os.getcwd()

    # first install dependencies
    os.chdir(FILE_DIR_PATH)
    dep_install_command = 'bash {}'.format(DEP_SCRIPT)
    ret_code = 0
    try:
        execute(dep_install_command)
    except subprocess.CalledProcessError as exc:
        ret_code = exc.returncode

    if ret_code != 0:
        message = 'Failure: Dependency install'
        print(colorama.Fore.RED + message)
        return ret_code

    message = 'Success: Dependency install'
    print(colorama.Fore.GREEN + message)
    os.chdir(cwd)

    # Load the docker images
    docker_images = get_docker_images()
    if docker_images:
        docker_load_cmd = 'sudo docker load --input {}'
        for docker_image in docker_images:
            try:
                execute(docker_load_cmd.format(docker_image))
            except subprocess.CalledProcessError as exc:
                ret_code = exc.returncode
                break
            else:
                message = 'Successfully loaded {}'.format(docker_image)
                print(colorama.Fore.GREEN + message)
    if ret_code != 0:
        message = 'Failure: Docker image load'
        print(colorama.Fore.RED + message)
        return ret_code

    # make soft link
    command = 'ln -sf {} {}'.format(os.path.realpath(__file__), '/usr/local/bin/jfit')
    try:
        execute(command)
    except subprocess.CalledProcessError as exc:
        ret_code = exc.returncode

    if ret_code != 0:
        message = 'Unable to set a soft link to jfit binary'
        print(colorama.Fore.RED + message)
    return ret_code


def remove(args):
    '''
    Remove application
    '''
    cwd = os.getcwd()
    group_name = args.group_name
    group_dir_path = get_group_dir_path(group_name)
    os.chdir(group_dir_path)
    compose_files = _get_compose_files(group_dir_path)
    compose_command = \
        'docker-compose -p {} {} rm --force --stop -v'.\
        format(group_name, compose_files)
    message = 'Remove group {}'.format(group_name)
    if args.service:
        compose_command = '{} {}'.format(compose_command, args.service)
        message = colorama.Fore.GREEN +\
            'Remove {}\'s service {}'.format(group_name, args.service)
    ret_code = 0
    try:
        execute(compose_command)
        message = colorama.Fore.GREEN + 'Success: {}'.format(message)
    except subprocess.CalledProcessError as exc:
        ret_code = exc.returncode
        message = colorama.Fore.RED + 'Failure: {}'.format(message)
    print(message)
    os.chdir(cwd)
    return ret_code


def parse(args):
    '''
    Parse input json file
    '''
    input_file_path = args.input_file_path
    input_dir = args.input_dir or PARSE_INPUT_DIR
    cwd = os.getcwd()
    input_file_path = os.path.join(cwd, input_file_path)
    err = None
    if not os.path.isfile(input_file_path):
        input_file_path = os.path.join(FILE_DIR_PATH, args.input_file_path)
        if not os.path.isfile(input_file_path):
            err = 'Unable to locate file {}'.format(args.input_file_path)
    elif not os.path.isdir(input_dir):
        full_input_path = os.path.join(FILE_DIR_PATH, input_dir)
        if not os.path.isdir(full_input_path):
            err = 'Invalid input directory: {}'.format(input_dir)
        else:
            input_dir = full_input_path
    if err:
            print(colorama.Fore.RED + err)
            return 1

    jfit_core_container_name = 'jfit_core'
    output_folder = GROUP_DIR
    if not os.path.isdir(output_folder):
        os.makedirs(output_folder)
    else:
        shutil.rmtree(output_folder)
        os.makedirs(output_folder)
    jfit_core_image_path = os.path.join(
        DOCKER_IMAGE_DIR,
        jfit_core_container_name+'.tar.gz')
    tags = _get_container_tags(jfit_core_image_path)
    # below output directory is different than mount point
    # because jfit-core clears the output dir supplied.
    # As you can't delete the mount point, we make another directory
    # inside the mount point and clear it.
    parse_command = 'python /jfit/jfit.py \
                    --config /input.json\
                    --device-group {}\
                    --output-dir /output/core_output\
                    --data-base-path /input\
                    '.format(
                        args.device_group,
                    )
    output_mount = os.path.realpath(os.path.join(output_folder, '..'))
    docker_parse_command = 'docker run -i -d \
                            -v {}:/input.json \
                            -v {}:/output/ \
                            -v {}:/input/ \
                            {} {}'.format(
                                input_file_path,
                                output_mount,
                                input_dir,
                                tags,
                                parse_command)
    ret_code = 0
    try:
        container_id = execute(docker_parse_command)
        status_command = 'docker inspect --format="{{{}}}" {}'.\
            format('{.State.Status}', container_id)
        status = ''
        while status != 'exited':
            status = execute(status_command)
            time.sleep(5)
        remove_command = 'docker rm -f {}'.format(container_id)
        execute(remove_command)
    except subprocess.CalledProcessError as exc:
        ret_code = exc.returncode
    if ret_code != 0:
        return ret_code

    # now go to the output folder and construct their compose files
    if not os.path.isdir(output_folder):
        message = 'Unable to parse input configuration'
        print(colorama.Fore.RED + message)
        return 1
    group_folders = [os.path.join(output_folder, x)
                     for x in os.listdir(output_folder)
                     if not x.startswith('.') and
                     os.path.isdir(os.path.join(output_folder, x))]
    if not group_folders:
        message = 'Unable to parse the input configuration'
        print(colorama.Fore.RED + message)
        return 1
    ret_codes = [_create_compose_file(x) for x in group_folders]
    non_zero = [x for x in ret_codes if x != 0]
    if non_zero:
        ret_code = 1
    return ret_code


def start(args):
    '''
    Start application/service for a group
    '''
    group_name = args.group_name
    group_dir_path = get_group_dir_path(group_name)
    # check if group name is valid
    if not os.path.isdir(group_dir_path):
        err = 'Group name is not valid'
        print(colorama.Fore.RED + err)
        return 1
    ret_code = 0
    message = colorama.Fore.GREEN + 'Success!'
    cwd = os.getcwd()
    os.chdir(group_dir_path)
    compose_command = 'docker-compose -p {}'.format(group_name)
    compose_files = _get_compose_files(group_dir_path)
    if compose_files == 1:
        return 1
    compose_command = '{} {}'.format(compose_command, compose_files)
    if args.service:
        compose_command = '{} start {}'.format(compose_command, args.service)
    else:
        compose_command = '{} up -d'.format(compose_command)
    try:
        output = execute(compose_command)
    except subprocess.CalledProcessError as exc:
        ret_code = exc.returncode
    else:
        print(output)
    os.chdir(cwd)
    if ret_code == 0:
        print(message)
    return ret_code


def stop(args):
    '''
    Stop application or a service
    '''
    group_name = args.group_name
    group_dir_path = get_group_dir_path(group_name)
    # check if group name is valid
    if not os.path.isdir(group_dir_path):
        err = 'Group name is not valid'
        print(colorama.Fore.RED + err)
        return 1
    ret_code = 0
    message = colorama.Fore.GREEN + 'Success!'
    cwd = os.getcwd()
    os.chdir(group_dir_path)
    compose_files = _get_compose_files(group_dir_path)
    if compose_files == 1:
        return 1
    compose_command = 'docker-compose -p {} {} stop'.\
        format(group_name, compose_files)
    if args.service:
        compose_command = '{} {}'.format(compose_command, args.service)
    try:
        output = execute(compose_command)
    except subprocess.CalledProcessError as exc:
        ret_code = exc.returncode
    else:
        print(output)
    os.chdir(cwd)
    if ret_code == 0:
        print(message)
    return ret_code


def restart(args):
    '''
    Restart application or a service
    '''
    group_name = args.group_name
    group_dir_path = get_group_dir_path(group_name)
    # check if group name is valid
    if not os.path.isdir(group_dir_path):
        err = 'Group name is not valid'
        print(colorama.Fore.RED + err)
        return 1
    ret_code = 0
    message = colorama.Fore.GREEN + 'Success!'
    cwd = os.getcwd()
    os.chdir(group_dir_path)
    compose_files = _get_compose_files(group_dir_path)
    if compose_files == 1:
        return 1
    compose_command = 'docker-compose -p {} {} restart'.\
        format(group_name, compose_files)
    if args.service:
        compose_command = '{} {}'.format(compose_command, args.service)
    try:
        output = execute(compose_command)
    except subprocess.CalledProcessError as exc:
        ret_code = exc.returncode
    else:
        print(output)
    os.chdir(cwd)
    if ret_code == 0:
        print(message)
    return ret_code


def cli(args):
    '''
    Cli access to a service
    '''
    group_name = args.group_name
    group_dir_path = get_group_dir_path(group_name)
    # check if group name is valid
    if not os.path.isdir(group_dir_path):
        err = 'Group name is not valid'
        print(colorama.Fore.RED + err)
        return 1
    ret_code = 0
    cwd = os.getcwd()
    os.chdir(group_dir_path)
    compose_files = _get_compose_files(group_dir_path)
    if compose_files == 1:
        return 1
    compose_command = 'docker-compose -p {} {} exec {} sh'.\
        format(group_name, compose_files, args.service)
    try:
        ret_code = shell_command(compose_command)
    except subprocess.CalledProcessError as exc:
        ret_code = exc.returncode
    os.chdir(cwd)
    return ret_code


def logs(args):
    '''
    Access service logs
    '''
    group_name = args.group_name
    group_dir_path = get_group_dir_path(group_name)
    # check if group name is valid
    if not os.path.isdir(group_dir_path):
        err = 'Group name is not valid'
        print(colorama.Fore.RED + err)
        return 1
    ret_code = 0
    cwd = os.getcwd()
    os.chdir(group_dir_path)
    inspect_command = 'docker inspect --format="{{{}}}" {}_{}_1'.\
        format('{.LogPath}', group_name.lower(), args.service)
    try:
        log_location = execute(inspect_command)
    except subprocess.CalledProcessError as exc:
        ret_code = exc.returncode
    else:
        vi_command = 'vi {}'.format(log_location)
        try:
            shell_command(vi_command)
        except subprocess.CalledProcessError as exc:
            ret_code = exc.returncode
    os.chdir(cwd)
    return ret_code


def mgd(args):
    '''
    Spin up mgd container
    '''
    command = args.mgd_command
    mgd_container_name = 'jfit_mgd_cli'
    if command == 'start':
        try:
            remove_command = 'docker rm -f {}'.format(mgd_container_name)
            execute(remove_command)
            message = 'Removed already running container! Starting a new one'
            print(colorama.Fore.MAGENTA + message)
        except subprocess.CalledProcessError as exc:
            pass
        mgd_docker_image = os.path.join(DOCKER_IMAGE_DIR, MGD_IMAGE)
        tags = _get_container_tags(mgd_docker_image)
        config_folder_location = os.path.join(
            FILE_DIR_PATH, CONFIG_LOCATION, '')
        docker_command = 'docker run -v {}:/config/ --name {} -d {}'.format(
            config_folder_location,
            mgd_container_name,
            tags
        )
        execute(docker_command)
        args.mgd_command = 'cli'
        mgd(args)
    elif command == 'stop':
        docker_command = 'docker stop {}'.format(mgd_container_name)
        execute(docker_command)
    elif command == 'cli':
        docker_command = 'docker exec -it {} /usr/sbin/cli'\
            .format(mgd_container_name)
        shell_command(docker_command)


def act(args):
    '''
    Call various sub-command handlers
    '''
    exit_status = globals()[args.commands](args)
    return exit_status


def main():
    '''
    Main function
    '''
    args = parse_args()
    exit_status = act(args)
    return exit_status

if __name__ == '__main__':
    colorama.init(autoreset=True)
    exit_status = main()
    colorama.deinit()
    exit(exit_status)
