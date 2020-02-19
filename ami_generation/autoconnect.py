#!/usr/bin/env python3

# Copyright 2018 Amazon.com, Inc. and its affiliates. All Rights Reserved.
#
# Licensed under the Amazon Software License (the "License").
# You may not use this file except in compliance with the License.
# A copy of the License is located at
#
# http://aws.amazon.com/asl/
#
# or in the "license" file accompanying this file. This file is distributed
# on an "AS IS" BASIS, WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either
# express or implied. See the License for the specific language governing
# permissions and limitations under the License.

"""
Uses the following ec2 tags to connect to the jenkins master:

ci:master_private_url
ci:master_url
ci:node_name
"""

import platform
import logging
import logging.config
import jenkins
import functools
import argparse
import os
import urllib.request
import pprint
import subprocess
import sys
import shutil
import boto3
import time
import re
import random
import signal
import urllib.error
import json
from typing import Dict

AGENT_SLAVE_JAR_PATH = 'jnlpJars/slave.jar'
LOCAL_SLAVE_JAR_PATH = 'slave.jar'
SLAVE_CONNECTION_URL_FORMAT = "{master_private}/computer/{label}/slave-agent.jnlp"
SLAVE_START_COMMAND = 'java -jar {slave_path} -jnlpUrl {connection_url} -workDir "{work_dir}" -failIfWorkDirIsMissing'


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



def connect_to_master(node_name, master_private_url, work_dir):
    # We have to rename this instance before it is able to connect because we're not getting back the control
    # if the launch was successful
    rename_instance(node_name)

    # Try to connect to this node. If it fails, there's probably already a node connected to that slot
    slave_connection_url = SLAVE_CONNECTION_URL_FORMAT.format(master_private=master_private_url, label=node_name)
    slave_start_command = SLAVE_START_COMMAND.format(connection_url=slave_connection_url, work_dir=work_dir,
                                                     slave_path=LOCAL_SLAVE_JAR_PATH)
    logging.info('slave start command: {}'.format(slave_start_command))
    subprocess.check_call(slave_start_command, shell=True)


def download(url: str, file: str):
    logging.debug('Downloading {} to {}'.format(url, file))
    urllib.request.urlretrieve(url, file)


def is_offline_node_matches_prefix(prefix: str, node) -> bool:
    return node['name'].startswith(prefix) and node['offline']


def generate_node_label():
    system = platform.system()
    labelPlatform = "mxnet-"

    # Determine platform type
    if system == "Windows":
        labelPlatform += "windows-"
    elif system == "Linux":
        labelPlatform += "linux-"
    else:
        raise RuntimeError("system {} is not supported yet".format(system))

    # Determine whether CPU or GPU system
    if is_gpu_present():
        labelPlatform += "gpu"
    else:
        labelPlatform += "cpu"

    return labelPlatform


def instance_id():
    try:
        return urllib.request.urlopen('http://instance-data/latest/meta-data/instance-id').read().decode()
    except Exception:
        logging.exception('instance_id')
        return None


def instance_identity() -> Dict:
    response = urllib.request.urlopen("http://169.254.169.254/latest/dynamic/instance-identity/document")
    instance_info = json.loads(response.read().decode('utf-8'))
    return instance_info


def rename_instance(name: str):
    try:
        logging.info('Renaming instance to {}'.format(name))
        nfo = instance_identity()
        instance_id_ = nfo['instanceId']
        ec2 = boto3.resource('ec2', region_name=nfo['region'])
        ec2.create_tags(
            DryRun=False,
            Resources=[
                instance_id_
            ],
            Tags=[
                {
                    'Key': 'Name',
                    'Value': name
                },
            ]
        )
    except Exception as e:
        logging.exception('rename_instance')


def is_gpu_present() -> bool:
    num_gpus = get_num_gpus()
    logging.debug('Number GPUs present: {}'.format(num_gpus))
    return num_gpus > 0


def get_num_gpus() -> int:
    """
    Gets the number of GPUs available on the host (depends on nvidia-smi).
    :return: The number of GPUs on the system.
    """
    #if shutil.which("nvidia-smi") is None:
    nvidia_smi_path = get_nvidia_smi_path()
    if nvidia_smi_path is None or shutil.which(nvidia_smi_path) is None:
        logging.warning("Couldn't find nvidia-smi, therefore we assume no GPUs are available.")
        return 0
    #sp = subprocess.Popen(['nvidia-smi', '-L'], stdout=subprocess.PIPE, stderr=subprocess.PIPE)
    sp = subprocess.Popen([get_nvidia_smi_path(), '-L'], stdout=subprocess.PIPE, stderr=subprocess.PIPE)

    out_str = sp.communicate()[0].decode("utf-8")

    # Ensure we're counting the lines with GPU as CPU-instances have nvidia-smi present as well
    num_gpus = 0
    for line in out_str.split("\n"):
        logging.debug('Nvidia-SMI: {}'.format(line))
        if 'GPU' in line:
            num_gpus += 1

    return num_gpus


def get_nvidia_smi_path() -> str:
    if shutil.which("nvidia-smi") is not None:
        return 'nvidia-smi'

    if shutil.which("C:\\Program Files\\NVIDIA Corporation\\NVSMI\\nvidia-smi.exe") is not None:
        return 'C:\\Program Files\\NVIDIA Corporation\\NVSMI\\nvidia-smi.exe'

    return None


def validate_config(x: Dict) -> bool:
    assert 'master_url' in x
    assert 'master_private_url' in x
    assert 'node_name' in x


def config_from_ec2_tags() -> Dict:
    nfo = instance_identity()
    ec2 = boto3.resource('ec2', region_name=nfo['region'])
    instance = ec2.Instance(nfo['instanceId'])
    res = {}
    for tags in instance.tags:
        m = re.fullmatch('ci:(.+)', tags["Key"])
        if m:
            res[m.group(1)] = tags["Value"]
    return res



def redirect_stream(system_stream, target_stream):
    """ Redirect a system stream to a specified file.

        :param standard_stream: A file object representing a standard I/O
            stream.
        :param target_stream: The target file object for the redirected
            stream, or ``None`` to specify the null device.
        :return: ``None``.

        `system_stream` is a standard system stream such as
        ``sys.stdout``. `target_stream` is an open file object that
        should replace the corresponding system stream object.

        If `target_stream` is ``None``, defaults to opening the
        operating system's null device and using its file descriptor.

        """
    if target_stream is None:
        target_fd = os.open(os.devnull, os.O_RDWR)
    else:
        target_fd = target_stream.fileno()
    os.dup2(target_fd, system_stream.fileno())


def cleanup() -> None:
    pass


def reload_config() -> None:
    pass


def fork_exit_parent() -> None:
    pid = os.fork()
    if pid > 0:
        sys.exit(0)


def daemonize() -> None:
    fork_exit_parent()
    os.setsid()
    fork_exit_parent()
    os.chdir('/home/jenkins_slave')
    config_signal_handlers()
    os.umask(0o022)
    redirect_stream(sys.stdin, None)
    redirect_stream(sys.stdout, open('/tmp/slave_autoconnect.out', 'a'))
    redirect_stream(sys.stderr, open('/tmp/slave_autoconnect.err', 'a'))


def config_signal_handlers() -> None:
    signal.signal(signal.SIGHUP, signal.SIG_IGN)
    signal.signal(signal.SIGTERM, cleanup)
    signal.signal(signal.SIGUSR1, reload_config)
    signal.signal(signal.SIGTTIN, signal.SIG_IGN)
    signal.signal(signal.SIGTSTP, signal.SIG_IGN)
    signal.signal(signal.SIGTTOU, signal.SIG_IGN)


@retry(Exception, tries=2000)
def autoconnect() -> None:
    cfg = config_from_ec2_tags()
    validate_config(cfg)

    # Replace \ by / on URL due to windows using \ as default separator
    jenkins_slave_jar_url = os.path.join(cfg['master_url'], AGENT_SLAVE_JAR_PATH).replace('\\', '/')

    # Download jenkins slave jar
    download(jenkins_slave_jar_url, LOCAL_SLAVE_JAR_PATH)

    work_dir = os.path.join(os.getcwd(), 'workspace')
    logging.info('Work dir: {}'.format(work_dir))

    # Create work dir if it doesnt exist
    os.makedirs(work_dir, exist_ok=True)
    os.makedirs(os.path.join(work_dir, 'remoting'), exist_ok=True)

    server = jenkins.Jenkins(cfg['master_url'])

    if 'node_name' in cfg:
        offline_nodes = [cfg['node_name']]
    else:
        logging.warning('Entering auto connect mode')
        label = generate_node_label()
        logging.info('Local node prefix: {}'.format(label))
        nodes = server.get_nodes()

        offline_nodes = [node['name'] for node in
                         list(filter(functools.partial(is_offline_node_matches_prefix, label), nodes))]
        logging.debug('Offline nodes: {}', offline_nodes)
    # Shuffle to provide random order to reduce race conditions if multiple instances
    # are started at the same time and thus try to connect to the same slot, possibly
    # resulting in a hang
    random.shuffle(offline_nodes)

    if len(offline_nodes) == 0:
        rename_instance('error-no-free-slot')
        logging.fatal('Could connect to master - no free slots')
        raise RuntimeError("No free slots")

    # Loop through nodes and try to connect
    for node_name in offline_nodes:
        start_time = time.time()
        connect_to_master(node_name=cfg['node_name'],
                          master_private_url=cfg['master_private_url'],
                          work_dir=work_dir)
        total_runtime_seconds = time.time() - start_time
    raise RuntimeError('Could not connect to master')


def script_name() -> str:
    """:returns: script name with leading paths removed"""
    return os.path.split(sys.argv[0])[1]


def config_logging():
    import time
    root = logging.getLogger()
    root.setLevel(logging.INFO)
    fh = logging.FileHandler('autoconnect.log')
    fmt = '{}: %(asctime)sZ %(levelname)s %(message)s'.format(script_name())
    logging.basicConfig(format=fmt)
    fh.setFormatter(logging.Formatter(fmt=fmt))
    logging.Formatter.converter = time.gmtime
    root.addHandler(fh)


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('-f', '--foreground', action='store_true',
                        help="don't daemonize")
    args = parser.parse_args()
    if not args.foreground and platform.system() != 'Windows':
        daemonize()

    config_logging()
    autoconnect()
    rename_instance('error-too-many-attempts')
    logging.fatal('Could connect to master - too many attempts')
    return 0


if __name__ == '__main__':
    sys.exit(main())
