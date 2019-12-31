#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Windows AMI SSM pipeline"""

__author__ = 'Pedro Larroy'
__version__ = '0.1'


import boto3
import os
import sys
import subprocess
import logging
from troposphere import Parameter, Ref, Template
from troposphere.iam import Role
from troposphere.s3 import Bucket
from troposphere.ssm import Document
from awacs.aws import Allow, Statement, Principal, PolicyDocument
from awacs.sts import AssumeRole
from util import *
import argparse
from typing import List
from troposphere.codebuild import Project, Environment, Artifacts, Source



def create_pipeline_template(config) -> Template:
    t = Template()
    with open(config['ssm_document_windows_ami'], 'r') as f:
        document_content = yaml.load(f, Loader=yaml.SafeLoader)
        #document_content = f.read()
        t.add_resource(Document(
            config['ssm_windows_ami_name'],
            Content = document_content,
            DocumentType = "Automation"))
    return t


def parameters_interactive(template: Template) -> List[dict]:
    """
    Fill template parameters from standard input
    :param template:
    :return: A list of Parameter dictionary suitable to instantiate the template
    """
    print("Please provide values for the Cloud Formation template parameters.")
    parameter_values = []
    for name, parameter in template.parameters.items():
        paramdict = parameter.to_dict()
        if 'Default' in paramdict:
            default_value = paramdict['Default']
            param_value = input(f"{name} [{default_value}]: ")
            if not param_value:
                param_value = default_value
        else:
            param_value = input(f"{name}: ")
        parameter_values.append({'ParameterKey': name, 'ParameterValue': param_value})
    return parameter_values


def config_logging():
    import time
    logging.getLogger().setLevel(os.environ.get('LOGLEVEL', logging.INFO))
    logging.getLogger("requests").setLevel(logging.WARNING)
    logging.basicConfig(format='{}: %(asctime)sZ %(levelname)s %(message)s'.format(script_name()))
    logging.Formatter.converter = time.gmtime


def script_name() -> str:
    """:returns: script name with leading paths removed"""
    return os.path.split(sys.argv[0])[1]


def config_argparse() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Infra pipeline",
        epilog="""
""")
    parser.add_argument('config', nargs='?', help='config file', default='ssm_ami_pipeline_config.yaml')
    return parser


def main():
    config_logging()
    parser = config_argparse()
    args = parser.parse_args()
    with open(args.config, 'r') as fh:
        config = yaml.load(fh, Loader=yaml.SafeLoader)

    boto3.setup_default_session(region_name=config['aws_region'], profile_name=config['aws_profile'])

    template = create_pipeline_template(config)
    client = boto3.client('cloudformation')

    # FIXME: make a better way to create the token / authenticate
    logging.info(f"Creating stack {config['stack_name']}")
    param_values_dict = parameters_interactive(template)
    tparams = dict(
            TemplateBody = template.to_yaml(),
            Parameters = param_values_dict,
            Capabilities=['CAPABILITY_IAM'],
            #OnFailure = 'DELETE',
    )
    instantiate_CF_template(template, config['stack_name'], **tparams)
    return 0

if __name__ == '__main__':
    sys.exit(main())
