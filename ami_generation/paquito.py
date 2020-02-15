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


def _provision(ec2_resource, ec2_client, launch_template) -> None:
    try:
        logging.info("Creating security groups")
        security_groups = create_ssh_anywhere_sg(ec2_client, ec2_resource)
    except botocore.exceptions.ClientError as e:
        logging.info("Continuing: Security group might already exist or be used by a running instance")
        res = ec2_client.describe_security_groups(GroupNames=['ssh_anywhere'])
        security_groups = [res['SecurityGroups'][0]['GroupId']]


    try:
        ec2_client.import_key_pair(KeyName=launch_template['ssh-key-name'], PublicKeyMaterial=read_file(launch_template['ssh-key-file']))
    except botocore.exceptions.ClientError as e:
        logging.info("Continuing: Key pair '%s' might already exist", launch_template['ssh-key-name'])

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

    """, aws_account,
         launch_template['instance-type'], boto3.session.Session().region_name,
         launch_template['ami'], launch_template['ssh-key-name'],
         launch_template['ssh-key-file'], security_groups, launch_template.get('playbook'),
         launch_template.get('user-data'))


    logging.info("creating instances")
    instances = create_instances(
        ec2_resource,
        launch_template['instance-name'],
        launch_template['instance-type'],
        launch_template['ssh-key-name'],
        launch_template['ami'],
        security_groups,
        launch_template.get('user-data'),
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
            if 'playbook' in launch_template:
                ansible_provision_host(host, launch_template['username'], launch_template['playbook'])
            logging.info("All done, the following hosts are now available: %s", host)
        instance = next(iter(instances))
        logging.info("Imaging the first instance: %s", instance.instance_id)
        ami_id = _create_ami_image(ec2_client, instance.instance_id, launch_template['image-name'],
                          launch_template['image-description'], launch_template)
        ami_waiter = ec2_client.get_waiter('image_available')
        logging.info("Waiting for AMI id %s (this might take a long time)", ami_id)
        ami_waiter.wait(ImageIds=[ami_id], WaiterConfig={'Delay': 10, 'MaxAttempts': 180})

    finally:
        if not launch_template['keep-instance']:
            logging.info("Terminate instances")
            for instance in instances:
                instance.stop()


def parse_args():
    parser = argparse.ArgumentParser(description="Paquito AMI packer")
    parser.add_argument('-u', '--username', default=getpass.getuser())
    ssh_key = os.path.join(expanduser("~"),".ssh","id_rsa.pub")
    parser.add_argument('--ssh-key-file', default=ssh_key)
    parser.add_argument('--ssh-key-name', default="ssh_{}_key".format(getpass.getuser()))
    parser.add_argument('--keep-instance',
                        help="Keep instance on to diagnose problems",
                        action='store_true')

    parser.add_argument('--image-instance-id',
        help="Image an existing instance by instance id")
    parser.add_argument('-m', '--image-name')
    parser.add_argument('-d', '--image-description')
    parser.add_argument('--instance-type')

    parser.add_argument('template', help='template file')
    args = parser.parse_args()
    return args


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
    args = parse_args()

    launch_template = dict()
    if os.path.exists(args.template):
        with open(args.template, 'r') as f:
            launch_template = yaml.load(f, Loader=yaml.SafeLoader)

    for arg in ['username', 'ssh-key-file', 'ssh-key-name', 'keep-instance', 'instance-type']:
        argname = arg.replace('-','_')
        if not arg in launch_template and getattr(args, argname):
            launch_template[arg] = getattr(args, argname)

    if 'ubuntu' in launch_template:
        launch_template['ami'] = get_ubuntu_ami(boto3.session.Session().region_name, launch_template['ubuntu'])

    ec2_resource = boto3.resource('ec2')
    ec2_client = boto3.client('ec2')

    if args.image_instance_id:
        _create_ami_image(ec2_client, args.image_instance_id, args.image_name, args.image_description, launch_template, True)
    else:
        _provision(ec2_resource, ec2_client, launch_template)
    return 0

if __name__ == '__main__':
    sys.exit(main())

