# -*- coding: utf-8 -*-
# Generated by Django 1.10.5 on 2017-03-27 18:54
from __future__ import unicode_literals

from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):

    initial = True

    dependencies = [
        ('contenttypes', '0002_remove_content_type_name'),
        ('auth', '0008_alter_user_username_max_length'),
    ]

    operations = [
        migrations.CreateModel(
            name='AccessRule',
            fields=[
                ('id', models.AutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('query', models.TextField(blank=True, help_text='Cypher query for ths access rule.', verbose_name='cypher query')),
                ('is_active', models.BooleanField(default=True, help_text='Disable to disable evaluation of the rule in the rule chain.')),
                ('created', models.DateTimeField(auto_now_add=True, verbose_name='created')),
                ('updated', models.DateTimeField(auto_now=True, verbose_name='updated')),
                ('ctype_source', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name='accessrule_ctype_source_set', to='contenttypes.ContentType', verbose_name='source content type')),
                ('ctype_target', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name='accessrule_ctype_target_set', to='contenttypes.ContentType', verbose_name='target content type')),
                ('permissions', models.ManyToManyField(blank=True, help_text='Required permissions for target node.', related_name='accessrule_permissions', related_query_name='accessrule', to='auth.Permission', verbose_name='access rule permissions')),
            ],
        ),
    ]
