#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""A collection of python utilties useful for coding infra in AWS"""

import contextlib
import logging
import logging.config
import os
from troposphere import Template
import boto3
import botocore
import yaml
import urllib.request
import re
import ssl
import sys
from subprocess import check_call
from typing import List, Dict, Sequence


def get_root() -> str:
    """Get root folder (tagged with .root file)"""
    curpath = os.path.abspath(os.path.dirname(__file__))
    def is_root(path: str) -> bool:
        return os.path.exists(os.path.join(path, ".root"))
    while not is_root(curpath):
        parent = os.path.abspath(os.path.join(curpath, os.pardir))
        if parent == curpath:
            raise RuntimeError("Got to the root and couldn't find a parent folder with .root")
        curpath = parent
    return curpath


def wait_port_open(server, port, timeout=None):
    """ Wait for network service to appear
        @param server: host to connect to (str)
        @param port: port (int)
        @param timeout: in seconds, if None or 0 wait forever
        @return: True of False, if timeout is None may return only True or
                 throw unhandled network exception
    """
    import socket
    import errno
    import time
    sleep_s = 0
    if timeout:
        from time import time as now
        # time module is needed to calc timeout shared between two exceptions
        end = now() + timeout

    while True:
        logging.debug("Sleeping for %s second(s)", sleep_s)
        time.sleep(sleep_s)
        s = socket.socket()
        try:
            if timeout:
                next_timeout = end - now()
                if next_timeout < 0:
                    return False
                else:
                    s.settimeout(next_timeout)

            logging.info("connect %s %d", server, port)
            s.connect((server, port))

        except ConnectionError as err:
            logging.debug("ConnectionError %s", err)
            if sleep_s == 0:
                sleep_s = 1

        except socket.gaierror as err:
            logging.debug("gaierror %s",err)
            return False

        except socket.timeout as err:
            # this exception occurs only if timeout is set
            if timeout:
                return False

        except TimeoutError as err:
            # catch timeout exception from underlying network library
            # this one is different from socket.timeout
            raise

        else:
            s.close()
            logging.info("wait_port_open: port %s:%s is open", server, port)
            return True


@contextlib.contextmanager
def remember_cwd():
    '''
    Restore current directory when exiting context
    '''
    curdir = os.getcwd()
    try: yield
    finally: os.chdir(curdir)


def retry(target_exception, tries=4, delay_s=1, backoff=2):
    """Retry calling the decorated function using an exponential backoff.

    http://www.saltycrane.com/blog/2009/11/trying-out-retry-decorator-python/
    original from: http://wiki.python.org/moin/PythonDecoratorLibrary#Retry

    :param target_exception: the exception to check. may be a tuple of
        exceptions to check
    :type target_exception: Exception or tuple
    :param tries: number of times to try (not retry) before giving up
    :type tries: int
    :param delay_s: initial delay between retries in seconds
    :type delay_s: int
    :param backoff: backoff multiplier e.g. value of 2 will double the delay
        each retry
    :type backoff: int
    """
    import time
    from functools import wraps

    def decorated_retry(f):
        @wraps(f)
        def f_retry(*args, **kwargs):
            mtries, mdelay = tries, delay_s
            while mtries > 1:
                try:
                    return f(*args, **kwargs)
                except target_exception as e:
                    logging.warning("Exception: %s, Retrying in %d seconds...", str(e), mdelay)
                    time.sleep(mdelay)
                    mtries -= 1
                    mdelay *= backoff
            return f(*args, **kwargs)

        return f_retry  # true decorator

    return decorated_retry


def stack_exists(client, stack_name):
    stacks = client.list_stacks()['StackSummaries']
    for stack in stacks:
        if stack['StackStatus'] == 'DELETE_COMPLETE':
            continue
        if stack_name == stack['StackName']:
            return True
    return False


def delete_stack_s3_content(client, stack_name) -> None:
    stacks = client.describe_stacks(StackName=stack_name)
    #In [24]: stack['Stacks'][0]['Outputs'][0]
    #Out[24]:
    #{'OutputKey': 'ArtifactBucket',
    # 'OutputValue': 'cdpipeline-s3bucket-1o1kj4z50v7gv',
    # 'Description': 'Bucket for build artifacts'}
    buckets = []
    if not 'Outputs' in stacks['Stacks'][0]:
        return
    for output in stacks['Stacks'][0]['Outputs']:
        if output['OutputKey'] == 'ArtifactBucket':
            buckets.append(output['OutputValue'])
    for bucket in buckets:
        logging.info("Nuking bucket: %s", bucket)
        s3 = boto3.resource('s3')
        b = s3.Bucket(bucket)
        b.objects.all().delete()


def delete_stack(client, stack_name) -> None:
    if stack_exists(client, stack_name):
        # Delete S3 buckets and contents, otherwise stack deletion can't delete non-empty buckets.
        # rm -rf /
        delete_stack_s3_content(client, stack_name)
        client.delete_stack(StackName=stack_name)
        waiter = client.get_waiter('stack_delete_complete')
        logging.info("Waiting for stack deletion...")
        waiter.wait(StackName=stack_name)



def instantiate_CF_template(template: Template, stack_name: str="unnamed", **params) -> None:
    client = boto3.client('cloudformation')
    logging.info(f"Validating stack {stack_name}")
    tpl_yaml = template.to_yaml()
    validate_result = client.validate_template(TemplateBody=tpl_yaml)
    logging.info(f"Creating stack {stack_name}")
    stack_params = dict(
            StackName = stack_name,
            TemplateBody = tpl_yaml,
            Parameters = [],
            Capabilities=['CAPABILITY_IAM'],
            #OnFailure = 'DELETE',
    )
    stack_params.update(params)
    if stack_exists(client, stack_name):
        logging.warning(f"Stack '{stack_name}' already exists")
        stacks = client.describe_stacks(StackName=stack_name)
        status = stacks['Stacks'][0]['StackStatus']
        if status == 'ROLLBACK_COMPLETE':
            # Stacks in Rollback complete can't be updated.
            #input("Press enter to delete the stack (is in ROLLBACK_COMPLETE state) or ^C to abort...")
            logging.info("Deleting stack...")
            delete_stack(client, stack_name)
            stack_result = client.create_stack(**stack_params)
            waiter = client.get_waiter('stack_create_complete')
            logging.info("Waiting for stack create...")
            waiter.wait(StackName=stack_name)
        else:
            stack_result = client.update_stack(**stack_params)
            waiter = client.get_waiter('stack_update_complete')
            logging.info("Waiting for stack update...")
            waiter.wait(StackName=stack_name)
    else:
        stack_result = client.create_stack(**stack_params)
        waiter = client.get_waiter('stack_create_complete')
        logging.info("Waiting for stack create...")
        waiter.wait(StackName=stack_name)



def get_ubuntu_ami(region, release, arch='amd64', instance_type='hvm:ebs-ssd'):
    # https://aws.amazon.com/amazon-linux-ami/instance-type-matrix/
    # https://cloud-images.ubuntu.com/locator/ec2/  -> Js console -> Network
    ssl._create_default_https_context = ssl._create_unverified_context
    ami_list = yaml.safe_load(urllib.request.urlopen("https://cloud-images.ubuntu.com/locator/ec2/releasesTable").read())['aaData']
    # Items look like:
    #['us-east-1',
    # 'artful',
    # '17.10',
    # 'amd64',
    # 'hvm:instance-store',
    # '20180621',
    # '<a href="https://console.aws.amazon.com/ec2/home?region=us-east-1#launchAmi=ami-71e2b40e">ami-71e2b40e</a>',
    # 'hvm']
    res = [x for x in ami_list if x[0] == region and x[2].startswith(release) and x[3] == arch and x[4] == instance_type]
    ami_link = res[0][6]
    ami_id = re.sub('<[^<]+?>', '', ami_link)
    return ami_id

def wait_port_open(server, port, timeout=None):
    """ Wait for network service to appear
        @param server: host to connect to (str)
        @param port: port (int)
        @param timeout: in seconds, if None or 0 wait forever
        @return: True of False, if timeout is None may return only True or
                 throw unhandled network exception
    """
    import socket
    import errno
    import time
    sleep_s = 0
    if timeout:
        from time import time as now
        # time module is needed to calc timeout shared between two exceptions
        end = now() + timeout

    while True:
        logging.debug("Sleeping for %s second(s)", sleep_s)
        time.sleep(sleep_s)
        s = socket.socket()
        try:
            if timeout:
                next_timeout = end - now()
                if next_timeout < 0:
                    return False
                else:
                    s.settimeout(next_timeout)

            logging.info("connect %s %d", server, port)
            s.connect((server, port))

        except ConnectionError as err:
            logging.debug("ConnectionError %s", err)
            if sleep_s == 0:
                sleep_s = 1

        except socket.gaierror as err:
            logging.debug("gaierror %s",err)
            return False

        except socket.timeout as err:
            # this exception occurs only if timeout is set
            if timeout:
                return False

        except TimeoutError as err:
            # catch timeout exception from underlying network library
            # this one is different from socket.timeout
            raise

        else:
            s.close()
            logging.info("wait_port_open: port %s:%s is open", server, port)
            return True



def create_security_groups(ec2_client, ec2_resource):
    sec_group_name = 'ssh_anywhere'
    try:
        ec2_client.delete_security_group(GroupName=sec_group_name)
    except:
        pass
    sg = ec2_resource.create_security_group(
        GroupName=sec_group_name,
        Description='SSH from anywhere')
    resp = ec2_client.authorize_security_group_ingress(
        GroupId=sg.id,
        IpPermissions=[
            {'IpProtocol': 'tcp',
             'FromPort': 22,
             'ToPort': 22,
             'IpRanges': [{'CidrIp': '0.0.0.0/0'}]}
        ])
    return [sec_group_name]

def wait_for_instances(instances):
    """
    Wait until the given boto3 instance objects are running
    """
    logging.info("Waiting for instances: {}".format([i.id for i in instances]))
    for i in instances:
        logging.info("Waiting for instance {}".format(i.id))
        i.wait_until_running()
        logging.info("Instance {} running".format(i.id))

    client = boto3.client('ec2')
    waiter = client.get_waiter('instance_status_ok')
    logging.info("Waiting for instances to initialize (status ok): {}".format([i.id for i in instances]))
    waiter.wait(InstanceIds=[i.id for i in instances])
    logging.info("EC2 instances are ready to roll")
    for i in instances:
        i.reload()

def parse_args():
    with open('launch_template.yml', 'r') as f:
        launch_template = yaml.load(f)
    parser = argparse.ArgumentParser(description="launcher")
    parser.add_argument('-n', '--instance-name', default=launch_template.get('instance-name', "{}-{}".format('worker', getpass.getuser())))
    parser.add_argument('-i', '--instance-type', default=launch_template['instance-type'])
    parser.add_argument('--ubuntu', default=launch_template.get('ubuntu'))
    parser.add_argument('-u', '--username',
                        default=launch_template.get('username', getpass.getuser()))
    ssh_key = launch_template.get('ssh-key', os.path.join(expanduser("~"),".ssh","id_rsa.pub"))
    parser.add_argument('--ssh-key-file', default=ssh_key)
    parser.add_argument('--ssh-key-name', default="ssh_{}_key".format(getpass.getuser()))
    parser.add_argument('-a', '--ami', default=launch_template['ami'])
    parser.add_argument('rest', nargs='*')
    args = parser.parse_args()
    return args


def read_file(file):
    with open(file, 'r') as f:
        return f.read()


def ansible_provision_host(host: str, username: str, playbook: str ='playbook.yml') -> None:
    """
    Ansible provisioning
    """
    assert host
    assert username
    ansible_cmd= [
        "ansible-playbook",
        #"-v", # verbose
        "-u", "ubuntu",
        "-i", "{},".format(host),
        playbook,
        "--extra-vars", "user_name={}".format(username)]

    logging.info("Executing: '{}'".format(' '.join(ansible_cmd)))
    os.environ['ANSIBLE_HOST_KEY_CHECKING']='False'
    check_call(ansible_cmd)


def yaml_ansible_inventory(hosts, **vars):
    hdict = {}
    for h in hosts:
        hdict[h] = None
    invdata = {'all': {
        'hosts': hdict,
        'vars': vars
    }}
    return yaml.dump(invdata)


def create_inventory(file: str='inventory.yaml') -> None:
    """Create inventory file from running tagged instances"""
    logging.info(f"Creating inventory file: '{file}'")
    if os.path.exists(file):
        logging.warning(f"create_inventory: '{file}' already exists, skipping")
        return
        #raise FileExistsError(f"'{file}' already exists")
    instances = get_tagged_instances(('label', 'benchmark'))
    hostnames = list(map(lambda x: x.public_dns_name, instances))
    logging.info("hosts %s", hostnames)
    with open(file, 'w+') as fh:
        fh.write(yaml_ansible_inventory(hostnames, ansible_user='ubuntu', user_name='piotr'))


def create_hosts_file(file: str='hosts.txt') -> None:
    """Create a hosts file with ip addresses from the cluster nodes for mpirun / horovod"""
    logging.info(f"Creating hosts file: '{file}'")
    if os.path.exists(file):
        logging.warning(f"create_hosts_file: '{file}' already exists, skipping")
        return
    instances = get_tagged_instances(('label', 'benchmark'))
    ips = list(map(lambda x: x.public_ip_address, instances))
    logging.info("ips %s", ips)
    with open(file, 'w+') as fh:
        fh.write('\n'.join(ips))


def get_tagged_instances(*tags):
    ec2_resource = boto3.resource('ec2')
    filters = []
    for k,v in tags:
        filters.append({'Name': f'tag:{k}', 'Values': [v]})
    filters.append({'Name': 'instance-state-name', 'Values': ['pending', 'starting', 'running']})
    return ec2_resource.instances.filter(Filters=filters)


def assemble_userdata(*userdata_files):
    """
    :param userdata_files: tuples defining file and mime type for cloud-init
    example:
        assemble_userdata(('userdata.py', 'text/x-shellscript'), ('cloud-config',
        'text/cloud-config'))
    """
    from email.mime.multipart import MIMEMultipart
    from email.mime.text import MIMEText
    combined_message = MIMEMultipart()
    for fname, mimetype in userdata_files:
        with open(fname, "r") as f:
            content = f.read()
        sub_message = MIMEText(content, mimetype, sys.getdefaultencoding())
        sub_message.add_header('Content-Disposition', 'attachment; filename="{}"'.format(fname))
        combined_message.attach(sub_message)
    return combined_message


def create_instances(
    ec2: object,
    tag: str,
    instance_type: str,
    keyName: str,
    ami: str,
    security_groups: List[str],
    userdata_files: List[Sequence[str]],
    create_instance_kwargs: Dict,
    instanceCount: int = 1):

    logging.info("Launching {} instances".format(instanceCount))
    kwargs = { 'ImageId': ami
        , 'MinCount': instanceCount
        , 'MaxCount': instanceCount
        , 'KeyName': keyName
        , 'InstanceType': instance_type
        , 'UserData': assemble_userdata(*userdata_files).as_string()
    }
    if 'NetworkInterfaces' in create_instance_kwargs:
        for iface in create_instance_kwargs['NetworkInterfaces']:
            iface['Groups'] = security_groups
    else:
        kwargs['SecurityGroupIds'] = security_groups
    kwargs.update(create_instance_kwargs)
    instances = ec2.create_instances(**kwargs)
    ec2.create_tags(
        Resources = [instance.id for instance in instances]
        , Tags = [
          {'Key': 'Name', 'Value': tag}
        ]
    )

    return instances


def create_image(
    ec2: object,
    instance_id: str,
    image_name: str,
    image_description: str,
    **kwargs) -> str:
    """Trigger creation of AMI image and return its id"""
    kwargs.update(dict(
        InstanceId=instance_id,
        Name=image_name,
        Description=image_description,
    ))
    return ec2.create_image(**kwargs)['ImageId']


def create_ssh_anywhere_sg(ec2_client, ec2_resource):
    sec_group_name = 'ssh_anywhere'
    try:
        ec2_client.delete_security_group(GroupName=sec_group_name)
    except:
        pass
    sg = ec2_resource.create_security_group(
        GroupName=sec_group_name,
        Description='SSH from anywhere')
    resp = ec2_client.authorize_security_group_ingress(
        GroupId=sg.id,
        IpPermissions=[
            {'IpProtocol': 'tcp',
             'FromPort': 22,
             'ToPort': 22,
             'IpRanges': [{'CidrIp': '0.0.0.0/0'}]}
        ])
    return [sg.id]

