#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Paquito
=======

A simple AMI building tool.

Will launch an instance and provision with Ansible playbooks and create an AMI out of it.

Uses configuration from file 'ami_launch_template.yml'

"""
import os
import sys
import subprocess
import glob
import logging
import argparse
import getpass
import boto3
from os.path import expanduser
from subprocess import check_call
import botocore
import yaml
import re
from awsutils import *
import itertools


AMI_LAUNCH_TEMPLATE_FILE = os.getenv('PAQUITO_AMI_LAUNCH_TEMPLATE', 'linux/launch_template.yaml')


def group_user_data(xs):
    """Group a flat list of [file, mime, file, mime] into
    [[file, mime], [file,mime]]"""
    assert len(xs) % 2 == 0
    q = deque(xs)
    res = []
    while q:
        res.append( (q.popleft(), q.popleft()) )
    return res


def flatten(xs):
    return list(itertools.chain.from_iterable(xs))


def _create_ami_image(
    ec2: object,
    instance_id: str,
    image_name: str,
    image_description: str,
    launch_template: object,
    reboot: bool = True
    ) -> id:

    logging.info("Creating AMI %s from instance %s...", image_name, instance_id)
    create_image_args = dict(
        BlockDeviceMappings = launch_template['CreateInstanceArgs']['BlockDeviceMappings'],
        NoReboot = not reboot,
    )
    id = create_image(ec2, instance_id, image_name, image_description, **create_image_args)
    logging.info("AMI %s creationg complete.", id)
    return id


def _provision(ec2_resource, ec2_client, launch_template, args) -> None:
    try:
        logging.info("Creating security groups")
        security_groups = create_ssh_anywhere_sg(ec2_client, ec2_resource)
    except botocore.exceptions.ClientError as e:
        logging.info("Continuing: Security group might already exist or be used by a running instance")
        res = ec2_client.describe_security_groups(GroupNames=['ssh_anywhere'])
        security_groups = [res['SecurityGroups'][0]['GroupId']]


    try:
        ec2_client.import_key_pair(KeyName=args.ssh_key_name, PublicKeyMaterial=read_file(args.ssh_key_file))
    except botocore.exceptions.ClientError as e:
        logging.info("Continuing: Key pair '%s' might already exist", args.ssh_key_name)

    aws_account = boto3.client('sts').get_caller_identity()['Account']
    logging.info("""

    AWS Account: %s
    Instance type: %s
    Region: %s
    Base AMI: %s
    SSH Key: %s (from: %s)
    Security groups: %s
    Playbook: %s
    User Data: %s

    """, aws_account, args.instance_type, boto3.session.Session().region_name, args.ami, args.ssh_key_name,
         args.ssh_key_file, security_groups, args.playbook, args.user_data)


    logging.info("creating instances")
    instances = create_instances(
        ec2_resource,
        args.instance_name,
        args.instance_type,
        args.ssh_key_name,
        args.ami,
        security_groups,
        args.user_data,
        launch_template.get('CreateInstanceArgs', {}))
    try:
        wait_for_instances(instances)
        ec2_resource.create_tags(
            Resources = [instance.id for instance in instances]
            , Tags = [
              {'Key': 'AWSCop', 'Value': 'DevDesktop'}
            ]
        )


        for instance in instances:
            host = instance.public_dns_name
            logging.info("Waiting for host {}".format(host))
            wait_port_open(host, 22, 300)
            ansible_provision_host(host, args.username, args.playbook)
            logging.info("All done, the following hosts are now available: %s", host)
        instance = next(iter(instances))
        logging.info("Imaging the first instance: %s", instance.instance_id)
        ami_id = _create_ami_image(ec2_client, instance.instance_id, args.image_name,
                          args.image_description, launch_template)
        ami_waiter = ec2_client.get_waiter('image_available')
        logging.info("Waiting for AMI id %s (this might take a long time)", ami_id)
        ami_waiter.wait(ImageIds=[ami_id], WaiterConfig={'Delay': 10, 'MaxAttempts': 180})

    finally:
        if not args.keep_instance:
            logging.info("Terminate instances")
            for instance in instances:
                instance.stop()


def parse_args(**kwargs):
    parser = argparse.ArgumentParser(description="Paquito AMI packer")
    parser.add_argument('-n', '--instance-name', default=kwargs.get('instance-name',
                        "{}-{}".format('paquito', getpass.getuser())))
    parser.add_argument('-i', '--instance-type', default=kwargs.get('instance-type'))
    parser.add_argument('--ubuntu', default=kwargs.get('ubuntu'),
                        help="Specify an ubuntu release like 18.04 instead of an ami")
    parser.add_argument('-u', '--username',
                        default=kwargs.get('username', getpass.getuser()))
    ssh_key = kwargs.get('ssh-key', os.path.join(expanduser("~"),".ssh","id_rsa.pub"))
    parser.add_argument('--ssh-key-file', default=ssh_key)
    parser.add_argument('--ssh-key-name', default="ssh_{}_key".format(getpass.getuser()))
    parser.add_argument('-a', '--ami', default=kwargs.get('ami'))
    parser.add_argument('-p', '--playbook', default=kwargs.get('playbook'),
                        help="Ansible playbook to use for provisioning")
    parser.add_argument('-m', '--image-name', default=kwargs.get('image-name'))
    parser.add_argument('--user-data', nargs="*",
                        help="Add a flat list of file and mime type pair files to use for user data"
                        "for the instance")
    parser.add_argument('--keep-instance',
                        help="Keep instance on to diagnose problems",
                        action='store_true')
    parser.add_argument('-d', '--image-description', default=kwargs.get('image-description'))
    parser.add_argument('--image-instance-id',
                        help="Image an existing instance by instance id")
    parser.add_argument('rest', nargs='*')
    args = parser.parse_args()
    return args


def fill_args_interactive(args, current_region):
    if not args.instance_name:
        args.instance_name = input("instance_name: ")
    if not args.instance_type:
        args.instance_type = input("instance_type (https://www.ec2instances.info): ")

    if not args.ssh_key_file:
        args.ssh_key_file = input("(public) ssh_key_file: ")
    assert os.path.isfile(args.ssh_key_file)

    if not args.ubuntu:
        args.ubuntu = input("ubuntu release (or specific 'ami'): ")

    if args.ubuntu.startswith('ami') or args.ubuntu.startswith('aki'):
        args.ami = ubuntu
        args.ubuntu = None
    else:
        args.ami = get_ubuntu_ami(current_region, args.ubuntu)
        logging.info("Automatic Ubuntu ami selection based on region %s and release %s -> AMI id: %s",
                     current_region, args.ubuntu, args.ami)
    if not args.username:
        args.username = input("user name: ")

    if not args.playbook:
        args.playbook = input("Ansible playbook: ")


def validate_args(args):
    assert args.ami
    assert args.instance_type
    assert args.playbook and os.path.isfile(args.playbook)
    assert args.ssh_key_file and os.path.isfile(args.ssh_key_file)


def script_name() -> str:
    """:returns: script name with leading paths removed"""
    return os.path.split(sys.argv[0])[1]


def config_logging():
    import time
    logging.getLogger().setLevel(logging.INFO)
    logging.basicConfig(format='{}: %(asctime)sZ %(levelname)s %(message)s'.format(script_name()))
    logging.Formatter.converter = time.gmtime 


def main():
    # Launch a new instance each time by removing the state, otherwise tf will destroy the existing
    # one first
    def script_name() -> str:
        return os.path.split(sys.argv[0])[1]

    config_logging()

    launch_template = dict()
    launch_template_file = os.getenv('PAQUITO_TEMPLATE', AMI_LAUNCH_TEMPLATE_FILE)
    if os.path.exists(launch_template_file):
        with open(launch_template_file, 'r') as f:
            launch_template = yaml.load(f, Loader=yaml.SafeLoader)

    args = parse_args(**launch_template)

    if args.user_data:
        args.user_data = group_user_data(args.user_data)
    else:
        args.user_data = launch_template['user-data']

    fill_args_interactive(args, boto3.session.Session().region_name)
    validate_args(args)

    ec2_resource = boto3.resource('ec2')
    ec2_client = boto3.client('ec2')

    if args.image_instance_id:
        _create_ami_image(ec2_client, args.image_instance_id, args.image_name, args.image_description,
        launch_template, True)
    else:
        _provision(ec2_resource, ec2_client, launch_template, args)
    return 0

if __name__ == '__main__':
    sys.exit(main())

