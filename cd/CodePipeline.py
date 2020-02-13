#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Github attached AWS Code Pipeline"""

__author__ = 'Pedro Larroy'
__version__ = '0.2'


import boto3
import os
import sys
import subprocess
import logging
from troposphere import Parameter, Ref, Template, iam, Output
from troposphere.iam import Role
from troposphere.s3 import Bucket
from troposphere.codepipeline import (
    Pipeline, Stages, Actions, ActionTypeId, OutputArtifacts, InputArtifacts, Webhook,
    WebhookAuthConfiguration, WebhookFilterRule,
    ArtifactStore, DisableInboundStageTransitions)
import troposphere.codebuild as cb
import argparse
from awacs.aws import Allow, Statement, Principal, PolicyDocument, Policy
from awacs.sts import AssumeRole
from typing import List, Dict, Sequence
import yaml
import awsutils

from troposphere.codebuild import Project, Environment, Artifacts, Source

def create_pipeline_template(config) -> Template:
    t = Template()

    github_token = t.add_parameter(Parameter(
        "GithubToken",
        Type = "String",
        Default = os.environ.get('GH_TOKEN', '')
    ))

    github_owner = t.add_parameter(Parameter(
        "GitHubOwner",
        Type = 'String',
        Default = 'aiengines',
        AllowedPattern = "[A-Za-z0-9-_]+"
    ))

    github_repo = t.add_parameter(Parameter(
        "GitHubRepo",
        Type = 'String',
        Default = 'ci',
        AllowedPattern = "[A-Za-z0-9-_]+"
    ))

    github_branch = t.add_parameter(Parameter(
        "GitHubBranch",
        Type = 'String',
        Default = 'master',
        AllowedPattern = "[A-Za-z0-9-_]+"
    ))

    artifact_store_s3_bucket = t.add_resource(Bucket(
        "S3Bucket",
    ))

    cloudformationrole = t.add_resource(Role(
        "CloudformationRole",
        AssumeRolePolicyDocument = PolicyDocument(
            Version = "2012-10-17",
            Statement = [
                Statement(
                    Effect = Allow,
                    Action = [AssumeRole],
                    Principal = Principal("Service", ["cloudformation.amazonaws.com"])
                )
            ]
        ),
        ManagedPolicyArns = ['arn:aws:iam::aws:policy/AdministratorAccess']
    ))

    codepipelinerole = t.add_resource(Role(
        "CodePipelineRole",
        AssumeRolePolicyDocument = PolicyDocument(
            Statement = [
                Statement(
                    Effect = Allow,
                    Action = [AssumeRole],
                    Principal = Principal("Service", ["codepipeline.amazonaws.com"])
                )
            ]
        ),
        ManagedPolicyArns = ['arn:aws:iam::aws:policy/AdministratorAccess']
    ))


    linux_environment = Environment(
        ComputeType='BUILD_GENERAL1_LARGE',
        Image='aws/codebuild/standard:3.0',
        Type='LINUX_CONTAINER',
    )

    codebuild_role = t.add_resource(
        Role(
            "CodeBuildRole",
            AssumeRolePolicyDocument=Policy(
                Statement=[
                    Statement(
                        Effect=Allow,
                        Action=[AssumeRole],
                        Principal=Principal("Service", ["codebuild.amazonaws.com"])
                    )
                ]
            ),
            ManagedPolicyArns=[
                'arn:aws:iam::aws:policy/AmazonS3FullAccess',
                'arn:aws:iam::aws:policy/CloudWatchFullAccess',
                'arn:aws:iam::aws:policy/AWSCodeBuildAdminAccess',
            ],
        )
    )

    # https://docs.aws.amazon.com/AWSCloudFormation/latest/UserGuide/aws-properties-codebuild-project-source.html
    cb_project = t.add_resource(Project(
        "CDBuild",
        Name = "CDBuild",
        Description = 'Continous pipeline',
        Artifacts = Artifacts(Type='CODEPIPELINE'),
        Environment = linux_environment,
        Source = Source(Type='CODEPIPELINE', BuildSpec="cd/buildspec.yml"),
        ServiceRole = Ref(codebuild_role)
    ))


    pipeline = t.add_resource(Pipeline(
        "CDPipeline",
        ArtifactStore = ArtifactStore(
            Type = "S3",
            Location = Ref(artifact_store_s3_bucket)
        ),
#        DisableInboundStageTransitions = [
#            DisableInboundStageTransitions(
#                StageName = "Release",
#                Reason = "Disabling the transition until "
#                       "integration tests are completed"
#            )
#        ],
        RestartExecutionOnUpdate = True,
        RoleArn = codepipelinerole.GetAtt('Arn'),
        Stages = [
            Stages(
                Name = "Source",
                Actions = [
                    Actions(
                        Name = "SourceAction",
                        ActionTypeId = ActionTypeId(
                            Category = "Source",
                            Owner = "ThirdParty",
                            Provider = "GitHub",
                            Version = "1",
                        ),
                        OutputArtifacts = [
                            OutputArtifacts(
                                Name = "GitHubSourceCode"
                            )
                        ],
                        Configuration = {
                            'Owner': Ref(github_owner),
                            'Repo': Ref(github_repo),
                            'Branch': Ref(github_branch),
                            'PollForSourceChanges': False,
                            'OAuthToken': Ref(github_token)
                        },
                        RunOrder = "1"
                    )
                ]
            ),
            Stages(
                Name = "Build",
                Actions = [
                    Actions(
                        Name = "LinuxBuild",
                        ActionTypeId = ActionTypeId(
                            Category = "Build",
                            Owner = "AWS",
                            Provider = "CodeBuild",
                            Version = "1"
                        ),
                        InputArtifacts = [
                            InputArtifacts(
                                Name = "GitHubSourceCode"
                            )
                        ],
                        OutputArtifacts = [
                            OutputArtifacts(
                                Name = "LinuxBuild"
                            )
                        ],
                        Configuration = {
                            'ProjectName': Ref(cb_project),
                        },
                        RunOrder = "1"
                    ),
                ]
            ),

        ],
    ))

    t.add_resource(Webhook(
        "GitHubWebHook",
        Authentication = 'GITHUB_HMAC',
        AuthenticationConfiguration = WebhookAuthConfiguration(
            SecretToken = Ref(github_token)
        ),
        Filters = [
            WebhookFilterRule(
                JsonPath = '$.ref',
                MatchEquals = 'refs/heads/{Branch}'
            )
        ],
        TargetPipeline = Ref(pipeline),
        TargetAction = 'Source',
        TargetPipelineVersion = pipeline.GetAtt('Version')
    ))

    t.add_output(Output(
        "ArtifactBucket",
        Description="Bucket for build artifacts",
        Value=Ref(artifact_store_s3_bucket)
    ))

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
    parser = argparse.ArgumentParser(description="Code pipeline",
        epilog="""
""")
    parser.add_argument('config', nargs='?', help='config file', default='config.yaml')
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

    logging.info(f"Creating stack {config['stack_name']}")

    client = boto3.client('cloudformation')
    awsutils.delete_stack(client, config['stack_name'])

    param_values_dict = parameters_interactive(template)
    tparams = dict(
            TemplateBody = template.to_yaml(),
            Parameters = param_values_dict,
            Capabilities=['CAPABILITY_IAM'],
            #OnFailure = 'DELETE',
    )
    awsutils.instantiate_CF_template(template, config['stack_name'], **tparams)
    return 0

if __name__ == '__main__':
    sys.exit(main())
