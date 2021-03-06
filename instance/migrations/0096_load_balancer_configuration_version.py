# -*- coding: utf-8 -*-
# Generated by Django 1.10.7 on 2017-10-29 13:09
from __future__ import unicode_literals

from django.db import migrations, models
import functools
import instance.models.load_balancer


class Migration(migrations.Migration):

    dependencies = [
        ('instance', '0095_auto_20170925_0108'),
    ]

    operations = [
        migrations.AddField(
            model_name='loadbalancingserver',
            name='configuration_version',
            field=models.PositiveIntegerField(default=1, help_text='The current version of configuration for this load balancer. The version value is the total number of requests ever made to reconfigure the load balancer.'),
        ),
        migrations.AddField(
            model_name='loadbalancingserver',
            name='deployed_configuration_version',
            field=models.PositiveIntegerField(default=1, help_text='The currently active configuration version of the load balancer. If it is less than the configuration version, the load balancer is dirty. If it is equal to it, then no new reconfiguration is currently required.'),
        ),
        migrations.AlterField(
            model_name='loadbalancingserver',
            name='accepts_new_backends',
            field=models.BooleanField(default=True, help_text='Whether new backends can be assigned to this load-balancing server.'),
        ),
        migrations.AlterField(
            model_name='loadbalancingserver',
            name='fragment_name_postfix',
            field=models.CharField(blank=True, default=functools.partial(instance.models.load_balancer.generate_fragment_name, *(), **{'length': 8}), help_text='A random postfix appended to the haproxy configuration file names to avoid clashes between multiple instance managers (or multiple concurrently running integration tests) sharing the same load balancer.', max_length=8),
        ),
        migrations.AlterField(
            model_name='loadbalancingserver',
            name='ssh_username',
            field=models.CharField(help_text='The username used to SSH into the server.', max_length=32),
        ),
    ]
