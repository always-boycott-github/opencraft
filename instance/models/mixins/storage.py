# -*- coding: utf-8 -*-
#
# OpenCraft -- tools to aid developing and hosting free software projects
# Copyright (C) 2015-2018 OpenCraft <contact@opencraft.com>
#
# This program is free software: you can redistribute it and/or modify
# it under the terms of the GNU Affero General Public License as
# published by the Free Software Foundation, either version 3 of the
# License, or (at your option) any later version.
#
# This program is distributed in the hope that it will be useful,
# but WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
# GNU Affero General Public License for more details.
#
# You should have received a copy of the GNU Affero General Public License
# along with this program.  If not, see <http://www.gnu.org/licenses/>.
#
"""
Instance app model mixins - Database
"""

# Imports #####################################################################
import json
import time

import boto3
from botocore.exceptions import ClientError

from django.db.backends.utils import truncate_name
from django.conf import settings
from django.db import models
from swiftclient.exceptions import ClientException as SwiftClientException

from instance import openstack_utils
from instance.models.utils import default_setting

USER_POLICY_NAME = 'allow_access_s3_bucket'


def get_s3_cors_config():
    """
    Default CORS config for ORA2 File uploads
    """
    return {
        'CORSRules': [{
            'AllowedHeaders': ['*'],
            'AllowedMethods': ['GET', 'PUT'],
            'AllowedOrigins': ['*'],
            'ExposeHeaders': ['GET', 'PUT'],
        }]
    }


def get_s3_lifecycle():
    """
    Default bucket lifecycle for expiring old versions of objects
    """
    return {
        'Rules': [
            {
                'NoncurrentVersionExpiration': {
                    'NoncurrentDays': 30  # settings.S3_VERSION_EXPIRATION
                },
                'Prefix': '',
                'Status': 'Enabled',
            },
        ]
    }


# Classes #####################################################################

class StorageContainer(models.Model):
    """
    Base class selecting the storage type.
    """
    S3_STORAGE = 's3'
    SWIFT_STORAGE = 'swift'
    FILE_STORAGE = 'filesystem'

    storage_type = models.CharField(
        max_length=16,
        blank=True,
        default=default_setting("INSTANCE_STORAGE_TYPE")
    )

    class Meta:
        abstract = True


class SwiftContainerInstanceMixin(models.Model):
    """
    Mixin to provision Swift containers for an instance.
    """
    swift_openstack_user = models.CharField(
        max_length=32,
        blank=True,
        default=default_setting('SWIFT_OPENSTACK_USER'),
    )
    swift_openstack_password = models.CharField(
        max_length=64,
        blank=True,
        default=default_setting('SWIFT_OPENSTACK_PASSWORD'),
    )
    swift_openstack_tenant = models.CharField(
        max_length=32,
        blank=True,
        default=default_setting('SWIFT_OPENSTACK_TENANT'),
    )
    swift_openstack_auth_url = models.URLField(
        blank=True,
        default=default_setting('SWIFT_OPENSTACK_AUTH_URL'),
    )
    swift_openstack_region = models.CharField(
        max_length=16,
        blank=True,
        default=default_setting('SWIFT_OPENSTACK_REGION'),
    )
    swift_provisioned = models.BooleanField(default=False)

    class Meta:
        abstract = True

    @property
    def swift_container_names(self):
        """
        An iterable of Swift container names.
        """
        return NotImplementedError

    def provision_swift(self):
        """
        Create the Swift containers if necessary.
        """
        if self.storage_type == self.SWIFT_STORAGE:
            for container_name in self.swift_container_names:
                openstack_utils.create_swift_container(
                    container_name,
                    user=self.swift_openstack_user,
                    password=self.swift_openstack_password,
                    tenant=self.swift_openstack_tenant,
                    auth_url=self.swift_openstack_auth_url,
                    region=self.swift_openstack_region,
                )
            self.swift_provisioned = True
            self.save()

    def deprovision_swift(self):
        """
        Delete the Swift containers.
        """
        self.logger.info('Deprovisioning swift started.')
        if self.storage_type == self.SWIFT_STORAGE and self.swift_provisioned:
            for container_name in self.swift_container_names:
                self.logger.info('Deleting swift container: %s', container_name)
                try:
                    openstack_utils.delete_swift_container(
                        container_name,
                        user=self.swift_openstack_user,
                        password=self.swift_openstack_password,
                        tenant=self.swift_openstack_tenant,
                        auth_url=self.swift_openstack_auth_url,
                        region=self.swift_openstack_region,
                    )
                except SwiftClientException:
                    # If deleting a Swift container fails, we still want to continue.
                    self.logger.exception('Could not delete Swift container "%s".', container_name)
            self.swift_provisioned = False
            self.save()
        self.logger.info('Deprovisioning swift finished.')


class S3BucketInstanceMixin(models.Model):
    """
    Mixin to provision S3 bucket for an instance.
    """
    class Meta:
        abstract = True

    s3_access_key = models.CharField(max_length=50, blank=True)
    s3_secret_access_key = models.CharField(max_length=50, blank=True)
    s3_bucket_name = models.CharField(max_length=50, blank=True)
    s3_region = models.CharField(
        max_length=50, blank=True, default=default_setting('AWS_S3_DEFAULT_REGION'),
        help_text=(
            'The region must support Signature Version 2.'
            ' See https://docs.aws.amazon.com/general/latest/gr/rande.html#s3_region for options.'
            ' When set empty, the bucket is created in the default region us-east-1.'
        )
    )

    def get_s3_policy(self):
        """
        Return s3 policy with access to create and update bucket
        """
        return {
            "Version": "2012-10-17",
            "Statement": [
                {
                    "Effect": "Allow",
                    "Action": [
                        "s3:ListBucket",
                        "s3:CreateBucket",
                        "s3:DeleteBucket",
                        "s3:PutBucketCORS",
                        "s3:PutBucketVersioning",
                        "s3:PutLifecycleConfiguration",
                    ],
                    "Resource": ["arn:aws:s3:::{}".format(self.s3_bucket_name)]
                },
                {
                    "Effect": "Allow",
                    "Action": [
                        "s3:*Object*"
                    ],
                    "Resource": ["arn:aws:s3:::{}/*".format(self.s3_bucket_name)]
                }
            ]
        }

    @property
    def bucket_name(self):
        """
        Return bucket name truncated to 50 characters
        """
        return truncate_name(
            '{}-{}'.format(settings.AWS_S3_BUCKET_PREFIX, self.database_name.replace('_', '-')),
            length=50
        )

    @property
    def iam_username(self):
        """
        Return IAM username truncated to 50 characters
        """
        return truncate_name(
            '{}-{}'.format(settings.AWS_IAM_USER_PREFIX, self.database_name),
            length=50
        )

    @property
    def s3_hostname(self):
        """
        Return the S3 hostname to use when creating a connection.
        """
        s3_hostname = settings.AWS_S3_DEFAULT_HOSTNAME

        if self.s3_region:
            s3_hostname = settings.AWS_S3_CUSTOM_REGION_HOSTNAME.format(region=self.s3_region)
        return s3_hostname

    @property
    def s3_custom_domain(self):
        """
        The custom domain name built based on the bucket name.
        """
        return "{}.s3.amazonaws.com".format(self.s3_bucket_name)

    @property
    def iam(self):
        """
        Create connection to S3 service
        """
        return boto3.client(
            service_name='iam',
            region_name=self.s3_region or None,
            aws_access_key_id=settings.AWS_ACCESS_KEY_ID,
            aws_secret_access_key=settings.AWS_SECRET_ACCESS_KEY
        )

    def create_iam_user(self):
        """
        Create IAM user with access only to the s3 bucket set in s3_bucket_name
        """
        self.iam.create_user(
            UserName=self.iam_username,
        )
        self.iam.put_user_policy(
            UserName=self.iam_username,
            PolicyName=USER_POLICY_NAME,
            PolicyDocument=json.dumps(self.get_s3_policy())
        )
        access_key = self.iam.create_access_key(UserName=self.iam_username)['AccessKey']
        self.s3_access_key = access_key['AccessKeyId']
        self.s3_secret_access_key = access_key['SecretAccessKey']
        self.save()

    @property
    def s3(self):  # pylint: disable=invalid-name
        """
        Create connection to S3 service
        """
        return boto3.client(
            service_name='s3',
            region_name=self.s3_region or None,
            aws_access_key_id=settings.AWS_ACCESS_KEY_ID,
            aws_secret_access_key=settings.AWS_SECRET_ACCESS_KEY
        )

    def _create_bucket(self, max_tries=4, retry_delay=4, location=None):
        """
        Create bucket, retry up to defined attempts if it fails
        If you specify a location (e.g. 'EU', 'us-west-1'), this method will use it. If the location is
        not specified, the value of the instance's 's3_region' field is used.
        """
        attempt, bucket = 1, None
        location_constraint = location or self.s3_region or None
        location_constraint = None if location_constraint == 'us-east-1' else location_constraint
        # oddly enough, boto3 uses 'us-east-1' as default and doesn't accept it explicitly
        # https://github.com/boto/boto3/issues/125
        while not bucket:
            try:
                if location_constraint is None:
                    bucket = self.s3.create_bucket(Bucket=self.s3_bucket_name)
                else:
                    bucket = self.s3.create_bucket(
                        Bucket=self.s3_bucket_name,
                        CreateBucketConfiguration={
                            'LocationConstraint': location_constraint
                        },
                    )
            except ClientError as e:
                if e.response.get('Error', {}).get('Code') == 'EntityAlreadyExists':
                    break
                self.logger.info(
                    'Retrying bucket creation. IAM keys are not propagated yet, attempt %s of %s.',
                    attempt, max_tries
                )
                time.sleep(retry_delay)
                attempt += 1
                if attempt > max_tries:
                    raise

        # Set bucket cors
        self.s3.put_bucket_cors(
            Bucket=self.s3_bucket_name,
            CORSConfiguration=get_s3_cors_config()
        )

        # Enable bucket lifecycle
        self.s3.put_bucket_lifecycle_configuration(
            Bucket=self.s3_bucket_name,
            LifecycleConfiguration=get_s3_lifecycle()
        )

        # Enable bucket versioning
        self.s3.put_bucket_versioning(
            Bucket=self.s3_bucket_name,
            VersioningConfiguration={
                'Status': 'Enabled'
            }
        )

    def provision_s3(self):
        """
        Create S3 Bucket if it doesn't exist
        """
        if not self.storage_type == self.S3_STORAGE:
            return

        if not self.s3_bucket_name:
            self.s3_bucket_name = self.bucket_name

        if not self.s3_access_key and not self.s3_secret_access_key:
            self.create_iam_user()

        self._create_bucket(location=self.s3_region)

    def deprovision_s3(self):
        """
        Deprovision S3 by deleting S3 bucket and IAM user
        """
        self.logger.info('Deprovisioning S3 started.')
        if (not self.storage_type == self.S3_STORAGE or
                not (self.s3_access_key or self.s3_secret_access_key or self.s3_bucket_name)):
            return

        try:
            while True:
                # Delete object versions and delete markers
                response = self.s3.list_object_versions(Bucket=self.s3_bucket_name)
                to_delete = response.get('Versions', []) + response.get('DeleteMarkers', [])
                if not to_delete:
                    break
                self.s3.delete_objects(
                    Bucket=self.s3_bucket_name,
                    Delete={
                        'Objects': [{'Key': d['Key'], 'VersionId': d['VersionId']} for d in to_delete]
                    }
                )
            # Remove bucket
            self.s3.delete_bucket(Bucket=self.s3_bucket_name)
            self.s3_bucket_name = ""
            self.save()
        except ClientError as e:
            if e.response['Error']['Code'] != '404':
                self.logger.exception(
                    'There was an error trying to remove S3 bucket "%s".',
                    self.s3_bucket_name
                )
        try:
            # Access keys and policies need to be deleted before removing the user
            self.iam.delete_access_key(UserName=self.iam_username, AccessKeyId=self.s3_access_key)
            self.iam.delete_user_policy(UserName=self.iam_username, PolicyName=USER_POLICY_NAME)
            self.iam.delete_user(UserName=self.iam_username)
            self.s3_access_key = ""
            self.s3_secret_access_key = ""
            self.save()
        except ClientError:
            self.logger.exception(
                'There was an error trying to remove IAM user "%s".',
                self.iam_username
            )
        self.logger.info('Deprovisioning S3 finished.')
