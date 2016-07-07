# -*- coding: utf-8 -*-
# Generated by Django 1.9.5 on 2016-05-30 12:29
from __future__ import unicode_literals

from django.conf import settings
from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
        ('instance', '0050_appserver_refactor3'),
    ]

    operations = [
        migrations.AddField(
            model_name='openedxappserver',
            name='lms_user_settings',
            field=models.TextField(blank=True, help_text='YAML variables for LMS user creation.'),
        ),
        migrations.AddField(
            model_name='openedxappserver',
            name='lms_users',
            field=models.ManyToManyField(help_text='Instance manager users that should be made staff users on the instance.', to=settings.AUTH_USER_MODEL),
        ),
        migrations.AddField(
            model_name='openedxinstance',
            name='lms_users',
            field=models.ManyToManyField(help_text='Instance manager users that should be made staff users on the instance.', to=settings.AUTH_USER_MODEL),
        ),
    ]