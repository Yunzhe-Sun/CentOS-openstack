# vim: tabstop=4 shiftwidth=4 softtabstop=4

# Copyright 2012, Red Hat, Inc.
#
#    Licensed under the Apache License, Version 2.0 (the "License"); you may
#    not use this file except in compliance with the License. You may obtain
#    a copy of the License at
#
#         http://www.apache.org/licenses/LICENSE-2.0
#
#    Unless required by applicable law or agreed to in writing, software
#    distributed under the License is distributed on an "AS IS" BASIS, WITHOUT
#    WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied. See the
#    License for the specific language governing permissions and limitations
#    under the License.

"""
Client side of the compute RPC API.
"""

from oslo.config import cfg

from nova import exception
from nova.objects import base as objects_base
from nova.openstack.common.gettextutils import _
from nova.openstack.common import jsonutils
from nova import rpcclient

rpcapi_opts = [
    cfg.StrOpt('compute_topic',
               default='compute',
               help='the topic compute nodes listen on'),
]

CONF = cfg.CONF
CONF.register_opts(rpcapi_opts)

rpcapi_cap_opt = cfg.StrOpt('compute',
        help='Set a version cap for messages sent to compute services')
CONF.register_opt(rpcapi_cap_opt, 'upgrade_levels')


def _compute_host(host, instance):
    '''Get the destination host for a message.

    :param host: explicit host to send the message to.
    :param instance: If an explicit host was not specified, use
                     instance['host']

    :returns: A host
    '''
    if host:
        return host
    if not instance:
        raise exception.NovaException(_('No compute host specified'))
    if not instance['host']:
        raise exception.NovaException(_('Unable to find host for '
                                        'Instance %s') % instance['uuid'])
    return instance['host']


class ComputeAPI(rpcclient.RpcProxy):
    '''Client side of the compute rpc API.

    API version history:

        1.0 - Initial version.
        1.1 - Adds get_host_uptime()
        1.2 - Adds check_can_live_migrate_[destination|source]
        1.3 - Adds change_instance_metadata()
        1.4 - Remove instance_uuid, add instance argument to reboot_instance()
        1.5 - Remove instance_uuid, add instance argument to pause_instance(),
              unpause_instance()
        1.6 - Remove instance_uuid, add instance argument to suspend_instance()
        1.7 - Remove instance_uuid, add instance argument to
              get_console_output()
        1.8 - Remove instance_uuid, add instance argument to
              add_fixed_ip_to_instance()
        1.9 - Remove instance_uuid, add instance argument to attach_volume()
        1.10 - Remove instance_id, add instance argument to
               check_can_live_migrate_destination()
        1.11 - Remove instance_id, add instance argument to
               check_can_live_migrate_source()
        1.12 - Remove instance_uuid, add instance argument to confirm_resize()
        1.13 - Remove instance_uuid, add instance argument to detach_volume()
        1.14 - Remove instance_uuid, add instance argument to finish_resize()
        1.15 - Remove instance_uuid, add instance argument to
               finish_revert_resize()
        1.16 - Remove instance_uuid, add instance argument to get_diagnostics()
        1.17 - Remove instance_uuid, add instance argument to get_vnc_console()
        1.18 - Remove instance_uuid, add instance argument to inject_file()
        1.19 - Remove instance_uuid, add instance argument to
               inject_network_info()
        1.20 - Remove instance_id, add instance argument to
               post_live_migration_at_destination()
        1.21 - Remove instance_uuid, add instance argument to
               power_off_instance() and stop_instance()
        1.22 - Remove instance_uuid, add instance argument to
               power_on_instance() and start_instance()
        1.23 - Remove instance_id, add instance argument to
               pre_live_migration()
        1.24 - Remove instance_uuid, add instance argument to
               rebuild_instance()
        1.25 - Remove instance_uuid, add instance argument to
               remove_fixed_ip_from_instance()
        1.26 - Remove instance_id, add instance argument to
               remove_volume_connection()
        1.27 - Remove instance_uuid, add instance argument to
               rescue_instance()
        1.28 - Remove instance_uuid, add instance argument to reset_network()
        1.29 - Remove instance_uuid, add instance argument to resize_instance()
        1.30 - Remove instance_uuid, add instance argument to resume_instance()
        1.31 - Remove instance_uuid, add instance argument to revert_resize()
        1.32 - Remove instance_id, add instance argument to
               rollback_live_migration_at_destination()
        1.33 - Remove instance_uuid, add instance argument to
               set_admin_password()
        1.34 - Remove instance_uuid, add instance argument to
               snapshot_instance()
        1.35 - Remove instance_uuid, add instance argument to
               unrescue_instance()
        1.36 - Remove instance_uuid, add instance argument to
               change_instance_metadata()
        1.37 - Remove instance_uuid, add instance argument to
               terminate_instance()
        1.38 - Changes to prep_resize():
                - remove instance_uuid, add instance
                - remove instance_type_id, add instance_type
                - remove topic, it was unused
        1.39 - Remove instance_uuid, add instance argument to run_instance()
        1.40 - Remove instance_id, add instance argument to live_migration()
        1.41 - Adds refresh_instance_security_rules()
        1.42 - Add reservations arg to prep_resize(), resize_instance(),
               finish_resize(), confirm_resize(), revert_resize() and
               finish_revert_resize()
        1.43 - Add migrate_data to live_migration()
        1.44 - Adds reserve_block_device_name()

        2.0 - Remove 1.x backwards compat
        2.1 - Adds orig_sys_metadata to rebuild_instance()
        2.2 - Adds subordinate_info parameter to add_aggregate_host() and
              remove_aggregate_host()
        2.3 - Adds volume_id to reserve_block_device_name()
        2.4 - Add bdms to terminate_instance
        2.5 - Add block device and network info to reboot_instance
        2.6 - Remove migration_id, add migration to resize_instance
        2.7 - Remove migration_id, add migration to confirm_resize
        2.8 - Remove migration_id, add migration to finish_resize
        2.9 - Add publish_service_capabilities()
        2.10 - Adds filter_properties and request_spec to prep_resize()
        2.11 - Adds soft_delete_instance() and restore_instance()
        2.12 - Remove migration_id, add migration to revert_resize
        2.13 - Remove migration_id, add migration to finish_revert_resize
        2.14 - Remove aggregate_id, add aggregate to add_aggregate_host
        2.15 - Remove aggregate_id, add aggregate to remove_aggregate_host
        2.16 - Add instance_type to resize_instance
        2.17 - Add get_backdoor_port()
        2.18 - Add bdms to rebuild_instance
        2.19 - Add node to run_instance
        2.20 - Add node to prep_resize
        2.21 - Add migrate_data dict param to pre_live_migration()
        2.22 - Add recreate, on_shared_storage and host arguments to
               rebuild_instance()
        2.23 - Remove network_info from reboot_instance
        2.24 - Added get_spice_console method
        2.25 - Add attach_interface() and detach_interface()
        2.26 - Add validate_console_port to ensure the service connects to
               vnc on the correct port
        2.27 - Adds 'reservations' to terminate_instance() and
               soft_delete_instance()

        ... Grizzly supports message version 2.27.  So, any changes to existing
        methods in 2.x after that point should be done such that they can
        handle the version_cap being set to 2.27.

        2.28 - Adds check_instance_shared_storage()
        2.29 - Made start_instance() and stop_instance() take new-world
               instance objects
        2.30 - Adds live_snapshot_instance()
        2.31 - Adds shelve_instance(), shelve_offload_instance, and
               unshelve_instance()
        2.32 - Make reboot_instance take a new world instance object
        2.33 - Made suspend_instance() and resume_instance() take new-world
               instance objects
        2.34 - Added swap_volume()
        2.35 - Made terminate_instance() and soft_delete_instance() take
               new-world instance objects
        2.36 - Made pause_instance() and unpause_instance() take new-world
               instance objects
        2.37 - Added the legacy_bdm_in_spec parameter to run_instance
        2.38 - Made check_can_live_migrate_[destination|source] take
               new-world instance objects
        2.39 - Made revert_resize() and confirm_resize() take new-world
               instance objects
        2.40 - Made reset_network() take new-world instance object
        2.41 - Make inject_network_info take new-world instance object
        2.42 - Splits snapshot_instance() into snapshot_instance() and
               backup_instance() and makes them take new-world instance
               objects.
        2.43 - Made prep_resize() take new-world instance object
        2.44 - Add volume_snapshot_create(), volume_snapshot_delete()
        2.45 - Made resize_instance() take new-world objects
        2.46 - Made finish_resize() take new-world objects
        2.47 - Made finish_revert_resize() take new-world objects

        ... Havana supports message version 2.47.  So, any changes to existing
        methods in 2.x after that point should be done such that they can
        handle the version_cap being set to 2.47.

        2.48 - Make add_aggregate_host() and remove_aggregate_host() take
               new-world objects
        ...  - Remove live_snapshot() that was never actually used

        3.0 - Remove 2.x compatibility
        3.1 - Update get_spice_console() to take an instance object
        3.2 - Update get_vnc_console() to take an instance object
        3.3 - Update validate_console_port() to take an instance object
        3.4 - Update rebuild_instance() to take an instance object
    '''

    #
    # NOTE(russellb): This is the default minimum version that the server
    # (manager) side must implement unless otherwise specified using a version
    # argument to self.call()/cast()/etc. here.  It should be left as X.0 where
    # X is the current major API version (1.0, 2.0, ...).  For more information
    # about rpc API versioning, see the docs in
    # openstack/common/rpc/dispatcher.py.
    #
    BASE_RPC_API_VERSION = '3.0'

    VERSION_ALIASES = {
        'grizzly': '2.27',
        'havana': '2.47',
    }

    def __init__(self):
        version_cap = self.VERSION_ALIASES.get(CONF.upgrade_levels.compute,
                                               CONF.upgrade_levels.compute)
        super(ComputeAPI, self).__init__(
                topic=CONF.compute_topic,
                default_version=self.BASE_RPC_API_VERSION,
                serializer=objects_base.NovaObjectSerializer(),
                version_cap=version_cap)
        self.client = self.get_client()

    def _get_compat_version(self, current, havana_compat):
        if not self.can_send_version(current):
            return havana_compat
        return current

    def add_aggregate_host(self, ctxt, aggregate, host_param, host,
                           subordinate_info=None):
        '''Add aggregate host.

        :param ctxt: request context
        :param aggregate_id:
        :param host_param: This value is placed in the message to be the 'host'
                           parameter for the remote method.
        :param host: This is the host to send the message to.
        '''
        if self.can_send_version('3.0'):
            version = '3.0'
        elif self.can_send_version('2.48'):
            version = '2.48'
        else:
            # NOTE(russellb) Havana compat
            version = '2.14'
            aggregate = jsonutils.to_primitive(aggregate)

        cctxt = self.client.prepare(server=host, version=version)
        cctxt.cast(ctxt, 'add_aggregate_host',
                   aggregate=aggregate, host=host_param,
                   subordinate_info=subordinate_info)

    def add_fixed_ip_to_instance(self, ctxt, instance, network_id):
        # NOTE(russellb) Havana compat
        version = self._get_compat_version('3.0', '2.0')
        instance_p = jsonutils.to_primitive(instance)
        cctxt = self.client.prepare(server=_compute_host(None, instance),
                version=version)
        cctxt.cast(ctxt, 'add_fixed_ip_to_instance',
                   instance=instance_p, network_id=network_id)

    def attach_interface(self, ctxt, instance, network_id, port_id,
                         requested_ip):
        # NOTE(russellb) Havana compat
        version = self._get_compat_version('3.0', '2.25')
        instance_p = jsonutils.to_primitive(instance)
        cctxt = self.client.prepare(server=_compute_host(None, instance),
                version=version)
        return cctxt.call(ctxt, 'attach_interface',
                          instance=instance_p, network_id=network_id,
                          port_id=port_id, requested_ip=requested_ip)

    def attach_volume(self, ctxt, instance, volume_id, mountpoint):
        # NOTE(russellb) Havana compat
        version = self._get_compat_version('3.0', '2.0')
        instance_p = jsonutils.to_primitive(instance)
        cctxt = self.client.prepare(server=_compute_host(None, instance),
                version=version)
        cctxt.cast(ctxt, 'attach_volume',
                   instance=instance_p, volume_id=volume_id,
                   mountpoint=mountpoint)

    def change_instance_metadata(self, ctxt, instance, diff):
        # NOTE(russellb) Havana compat
        version = self._get_compat_version('3.0', '2.0')
        instance_p = jsonutils.to_primitive(instance)
        cctxt = self.client.prepare(server=_compute_host(None, instance),
                version=version)
        cctxt.cast(ctxt, 'change_instance_metadata',
                   instance=instance_p, diff=diff)

    def check_can_live_migrate_destination(self, ctxt, instance, destination,
                                           block_migration, disk_over_commit):
        # NOTE(russellb) Havana compat
        version = self._get_compat_version('3.0', '2.38')
        cctxt = self.client.prepare(server=destination, version=version)
        return cctxt.call(ctxt, 'check_can_live_migrate_destination',
                          instance=instance,
                          block_migration=block_migration,
                          disk_over_commit=disk_over_commit)

    def check_can_live_migrate_source(self, ctxt, instance, dest_check_data):
        # NOTE(russellb) Havana compat
        version = self._get_compat_version('3.0', '2.38')
        cctxt = self.client.prepare(server=_compute_host(None, instance),
                version=version)
        return cctxt.call(ctxt, 'check_can_live_migrate_source',
                          instance=instance,
                          dest_check_data=dest_check_data)

    def check_instance_shared_storage(self, ctxt, instance, data):
        # NOTE(russellb) Havana compat
        version = self._get_compat_version('3.0', '2.28')
        instance_p = jsonutils.to_primitive(instance)
        cctxt = self.client.prepare(server=_compute_host(None, instance),
                version=version)
        return cctxt.call(ctxt, 'check_instance_shared_storage',
                          instance=instance_p,
                          data=data)

    def confirm_resize(self, ctxt, instance, migration, host,
            reservations=None, cast=True):
        # NOTE(russellb) Havana compat
        version = self._get_compat_version('3.0', '2.39')
        cctxt = self.client.prepare(server=_compute_host(host, instance),
                version=version)
        rpc_method = cctxt.cast if cast else cctxt.call
        return rpc_method(ctxt, 'confirm_resize',
                          instance=instance, migration=migration,
                          reservations=reservations)

    def detach_interface(self, ctxt, instance, port_id):
        # NOTE(russellb) Havana compat
        version = self._get_compat_version('3.0', '2.25')
        instance_p = jsonutils.to_primitive(instance)
        cctxt = self.client.prepare(server=_compute_host(None, instance),
                version=version)
        cctxt.cast(ctxt, 'detach_interface',
                   instance=instance_p, port_id=port_id)

    def detach_volume(self, ctxt, instance, volume_id):
        # NOTE(russellb) Havana compat
        version = self._get_compat_version('3.0', '2.0')
        instance_p = jsonutils.to_primitive(instance)
        cctxt = self.client.prepare(server=_compute_host(None, instance),
                version=version)
        cctxt.cast(ctxt, 'detach_volume',
                   instance=instance_p, volume_id=volume_id)

    def finish_resize(self, ctxt, instance, migration, image, disk_info,
            host, reservations=None):
        # NOTE(russellb) Havana compat
        version = self._get_compat_version('3.0', '2.46')
        cctxt = self.client.prepare(server=host, version=version)
        cctxt.cast(ctxt, 'finish_resize',
                   instance=instance, migration=migration,
                   image=image, disk_info=disk_info, reservations=reservations)

    def finish_revert_resize(self, ctxt, instance, migration, host,
                             reservations=None):
        # NOTE(russellb) Havana compat
        version = self._get_compat_version('3.0', '2.47')
        cctxt = self.client.prepare(server=host, version=version)
        cctxt.cast(ctxt, 'finish_revert_resize',
                   instance=instance, migration=migration,
                   reservations=reservations)

    def get_console_output(self, ctxt, instance, tail_length):
        # NOTE(russellb) Havana compat
        version = self._get_compat_version('3.0', '2.0')
        instance_p = jsonutils.to_primitive(instance)
        cctxt = self.client.prepare(server=_compute_host(None, instance),
                version=version)
        return cctxt.call(ctxt, 'get_console_output',
                          instance=instance_p, tail_length=tail_length)

    def get_console_pool_info(self, ctxt, console_type, host):
        # NOTE(russellb) Havana compat
        version = self._get_compat_version('3.0', '2.0')
        cctxt = self.client.prepare(server=host, version=version)
        return cctxt.call(ctxt, 'get_console_pool_info',
                          console_type=console_type)

    def get_console_topic(self, ctxt, host):
        # NOTE(russellb) Havana compat
        version = self._get_compat_version('3.0', '2.0')
        cctxt = self.client.prepare(server=host, version=version)
        return cctxt.call(ctxt, 'get_console_topic')

    def get_diagnostics(self, ctxt, instance):
        # NOTE(russellb) Havana compat
        version = self._get_compat_version('3.0', '2.0')
        instance_p = jsonutils.to_primitive(instance)
        cctxt = self.client.prepare(server=_compute_host(None, instance),
                version=version)
        return cctxt.call(ctxt, 'get_diagnostics',
                          instance=instance_p)

    def get_vnc_console(self, ctxt, instance, console_type):
        if self.can_send_version('3.2'):
            version = '3.2'
        else:
            # NOTE(russellb) Havana compat
            version = self._get_compat_version('3.0', '2.0')
            instance = jsonutils.to_primitive(instance)
        cctxt = self.client.prepare(server=_compute_host(None, instance),
                version=version)
        return cctxt.call(ctxt, 'get_vnc_console',
                          instance=instance, console_type=console_type)

    def get_spice_console(self, ctxt, instance, console_type):
        if self.can_send_version('3.1'):
            version = '3.1'
        else:
            # NOTE(russellb) Havana compat
            version = self._get_compat_version('3.0', '2.24')
            instance = jsonutils.to_primitive(instance)
        cctxt = self.client.prepare(server=_compute_host(None, instance),
                version=version)
        return cctxt.call(ctxt, 'get_spice_console',
                          instance=instance, console_type=console_type)

    def validate_console_port(self, ctxt, instance, port, console_type):
        if self.can_send_version('3.3'):
            version = '3.3'
        else:
            # NOTE(russellb) Havana compat
            version = self._get_compat_version('3.0', '2.26')
            instance = jsonutils.to_primitive(instance)
        cctxt = self.client.prepare(server=_compute_host(None, instance),
                version=version)
        return cctxt.call(ctxt, 'validate_console_port',
                          instance=instance, port=port,
                          console_type=console_type)

    def host_maintenance_mode(self, ctxt, host_param, mode, host):
        '''Set host maintenance mode

        :param ctxt: request context
        :param host_param: This value is placed in the message to be the 'host'
                           parameter for the remote method.
        :param mode:
        :param host: This is the host to send the message to.
        '''
        # NOTE(russellb) Havana compat
        version = self._get_compat_version('3.0', '2.0')
        cctxt = self.client.prepare(server=host, version=version)
        return cctxt.call(ctxt, 'host_maintenance_mode',
                          host=host_param, mode=mode)

    def host_power_action(self, ctxt, action, host):
        # NOTE(russellb) Havana compat
        version = self._get_compat_version('3.0', '2.0')
        cctxt = self.client.prepare(server=host, version=version)
        return cctxt.call(ctxt, 'host_power_action', action=action)

    def inject_file(self, ctxt, instance, path, file_contents):
        # NOTE(russellb) Havana compat
        version = self._get_compat_version('3.0', '2.0')
        instance_p = jsonutils.to_primitive(instance)
        cctxt = self.client.prepare(server=_compute_host(None, instance),
                version=version)
        cctxt.cast(ctxt, 'inject_file',
                   instance=instance_p, path=path,
                   file_contents=file_contents)

    def inject_network_info(self, ctxt, instance):
        # NOTE(russellb) Havana compat
        version = self._get_compat_version('3.0', '2.41')
        cctxt = self.client.prepare(server=_compute_host(None, instance),
                version=version)
        cctxt.cast(ctxt, 'inject_network_info', instance=instance)

    def live_migration(self, ctxt, instance, dest, block_migration, host,
                       migrate_data=None):
        # NOTE(russellb) Havana compat
        version = self._get_compat_version('3.0', '2.0')
        instance_p = jsonutils.to_primitive(instance)
        cctxt = self.client.prepare(server=host, version=version)
        cctxt.cast(ctxt, 'live_migration', instance=instance_p,
                   dest=dest, block_migration=block_migration,
                   migrate_data=migrate_data)

    def pause_instance(self, ctxt, instance):
        # NOTE(russellb) Havana compat
        version = self._get_compat_version('3.0', '2.36')
        cctxt = self.client.prepare(server=_compute_host(None, instance),
                version=version)
        cctxt.cast(ctxt, 'pause_instance', instance=instance)

    def post_live_migration_at_destination(self, ctxt, instance,
            block_migration, host):
        # NOTE(russellb) Havana compat
        version = self._get_compat_version('3.0', '2.0')
        instance_p = jsonutils.to_primitive(instance)
        cctxt = self.client.prepare(server=host, version=version)
        return cctxt.call(ctxt,
                          'post_live_migration_at_destination',
                          instance=instance_p, block_migration=block_migration)

    def pre_live_migration(self, ctxt, instance, block_migration, disk,
            host, migrate_data=None):
        # NOTE(russellb) Havana compat
        version = self._get_compat_version('3.0', '2.21')
        instance_p = jsonutils.to_primitive(instance)
        cctxt = self.client.prepare(server=host, version=version)
        return cctxt.call(ctxt, 'pre_live_migration',
                          instance=instance_p,
                          block_migration=block_migration,
                          disk=disk, migrate_data=migrate_data)

    def prep_resize(self, ctxt, image, instance, instance_type, host,
                    reservations=None, request_spec=None,
                    filter_properties=None, node=None):
        # NOTE(russellb) Havana compat
        version = self._get_compat_version('3.0', '2.43')
        instance_type_p = jsonutils.to_primitive(instance_type)
        image_p = jsonutils.to_primitive(image)
        cctxt = self.client.prepare(server=host, version=version)
        cctxt.cast(ctxt, 'prep_resize',
                   instance=instance,
                   instance_type=instance_type_p,
                   image=image_p, reservations=reservations,
                   request_spec=request_spec,
                   filter_properties=filter_properties,
                   node=node)

    def reboot_instance(self, ctxt, instance, block_device_info,
                        reboot_type):
        # NOTE(russellb) Havana compat
        version = self._get_compat_version('3.0', '2.32')
        cctxt = self.client.prepare(server=_compute_host(None, instance),
                version=version)
        cctxt.cast(ctxt, 'reboot_instance',
                   instance=instance,
                   block_device_info=block_device_info,
                   reboot_type=reboot_type)

    def rebuild_instance(self, ctxt, instance, new_pass, injected_files,
            image_ref, orig_image_ref, orig_sys_metadata, bdms,
            recreate=False, on_shared_storage=False, host=None,
            kwargs=None):
        # NOTE(danms): kwargs is only here for cells compatibility, don't
        # actually send it to compute
        if self.can_send_version('3.4'):
            version = '3.4'
        else:
            # NOTE(russellb) Havana compat
            version = self._get_compat_version('3.0', '2.22')
            instance = jsonutils.to_primitive(instance)
        bdms_p = jsonutils.to_primitive(bdms)
        cctxt = self.client.prepare(server=_compute_host(host, instance),
                version=version)
        cctxt.cast(ctxt, 'rebuild_instance',
                   instance=instance, new_pass=new_pass,
                   injected_files=injected_files, image_ref=image_ref,
                   orig_image_ref=orig_image_ref,
                   orig_sys_metadata=orig_sys_metadata, bdms=bdms_p,
                   recreate=recreate, on_shared_storage=on_shared_storage)

    def refresh_provider_fw_rules(self, ctxt, host):
        # NOTE(russellb) Havana compat
        version = self._get_compat_version('3.0', '2.0')
        cctxt = self.client.prepare(server=host, version=version)
        cctxt.cast(ctxt, 'refresh_provider_fw_rules')

    def remove_aggregate_host(self, ctxt, aggregate, host_param, host,
                              subordinate_info=None):
        '''Remove aggregate host.

        :param ctxt: request context
        :param aggregate_id:
        :param host_param: This value is placed in the message to be the 'host'
                           parameter for the remote method.
        :param host: This is the host to send the message to.
        '''
        if self.can_send_version('3.0'):
            version = '3.0'
        elif self.can_send_version('2.48'):
            version = '2.48'
        else:
            # NOTE(russellb) Havana compat
            version = '2.15'
            aggregate = jsonutils.to_primitive(aggregate)

        cctxt = self.client.prepare(server=host, version=version)
        cctxt.cast(ctxt, 'remove_aggregate_host',
                   aggregate=aggregate, host=host_param,
                   subordinate_info=subordinate_info)

    def remove_fixed_ip_from_instance(self, ctxt, instance, address):
        # NOTE(russellb) Havana compat
        version = self._get_compat_version('3.0', '2.0')
        instance_p = jsonutils.to_primitive(instance)
        cctxt = self.client.prepare(server=_compute_host(None, instance),
                version=version)
        cctxt.cast(ctxt, 'remove_fixed_ip_from_instance',
                   instance=instance_p, address=address)

    def remove_volume_connection(self, ctxt, instance, volume_id, host):
        # NOTE(russellb) Havana compat
        version = self._get_compat_version('3.0', '2.0')
        instance_p = jsonutils.to_primitive(instance)
        cctxt = self.client.prepare(server=host, version=version)
        return cctxt.call(ctxt, 'remove_volume_connection',
                          instance=instance_p, volume_id=volume_id)

    def rescue_instance(self, ctxt, instance, rescue_password):
        # NOTE(russellb) Havana compat
        version = self._get_compat_version('3.0', '2.0')
        instance_p = jsonutils.to_primitive(instance)
        cctxt = self.client.prepare(server=_compute_host(None, instance),
                version=version)
        cctxt.cast(ctxt, 'rescue_instance',
                   instance=instance_p,
                   rescue_password=rescue_password)

    def reset_network(self, ctxt, instance):
        # NOTE(russellb) Havana compat
        version = self._get_compat_version('3.0', '2.40')
        cctxt = self.client.prepare(server=_compute_host(None, instance),
                version=version)
        cctxt.cast(ctxt, 'reset_network', instance=instance)

    def resize_instance(self, ctxt, instance, migration, image, instance_type,
                        reservations=None):
        # NOTE(russellb) Havana compat
        version = self._get_compat_version('3.0', '2.45')
        instance_type_p = jsonutils.to_primitive(instance_type)
        cctxt = self.client.prepare(server=_compute_host(None, instance),
                version=version)
        cctxt.cast(ctxt, 'resize_instance',
                   instance=instance, migration=migration,
                   image=image, reservations=reservations,
                   instance_type=instance_type_p)

    def resume_instance(self, ctxt, instance):
        # NOTE(russellb) Havana compat
        version = self._get_compat_version('3.0', '2.33')
        cctxt = self.client.prepare(server=_compute_host(None, instance),
                version=version)
        cctxt.cast(ctxt, 'resume_instance', instance=instance)

    def revert_resize(self, ctxt, instance, migration, host,
                      reservations=None):
        # NOTE(russellb) Havana compat
        version = self._get_compat_version('3.0', '2.39')
        cctxt = self.client.prepare(server=_compute_host(host, instance),
                version=version)
        cctxt.cast(ctxt, 'revert_resize',
                   instance=instance, migration=migration,
                   reservations=reservations)

    def rollback_live_migration_at_destination(self, ctxt, instance, host):
        # NOTE(russellb) Havana compat
        version = self._get_compat_version('3.0', '2.0')
        instance_p = jsonutils.to_primitive(instance)
        cctxt = self.client.prepare(server=host, version=version)
        cctxt.cast(ctxt, 'rollback_live_migration_at_destination',
                   instance=instance_p)

    def run_instance(self, ctxt, instance, host, request_spec,
                     filter_properties, requested_networks,
                     injected_files, admin_password,
                     is_first_time, node=None, legacy_bdm_in_spec=True):
        # NOTE(russellb) Havana compat
        version = self._get_compat_version('3.0', '2.37')
        instance_p = jsonutils.to_primitive(instance)
        msg_kwargs = {'instance': instance_p, 'request_spec': request_spec,
                      'filter_properties': filter_properties,
                      'requested_networks': requested_networks,
                      'injected_files': injected_files,
                      'admin_password': admin_password,
                      'is_first_time': is_first_time, 'node': node,
                      'legacy_bdm_in_spec': legacy_bdm_in_spec}

        cctxt = self.client.prepare(server=host, version=version)
        cctxt.cast(ctxt, 'run_instance', **msg_kwargs)

    def set_admin_password(self, ctxt, instance, new_pass):
        # NOTE(russellb) Havana compat
        version = self._get_compat_version('3.0', '2.0')
        instance_p = jsonutils.to_primitive(instance)
        cctxt = self.client.prepare(server=_compute_host(None, instance),
                version=version)
        return cctxt.call(ctxt, 'set_admin_password',
                          instance=instance_p, new_pass=new_pass)

    def set_host_enabled(self, ctxt, enabled, host):
        # NOTE(russellb) Havana compat
        version = self._get_compat_version('3.0', '2.0')
        cctxt = self.client.prepare(server=host, version=version)
        return cctxt.call(ctxt, 'set_host_enabled', enabled=enabled)

    def swap_volume(self, ctxt, instance, old_volume_id, new_volume_id):
        # NOTE(russellb) Havana compat
        version = self._get_compat_version('3.0', '2.34')
        cctxt = self.client.prepare(server=_compute_host(None, instance),
                version=version)
        cctxt.cast(ctxt, 'swap_volume',
                   instance=instance, old_volume_id=old_volume_id,
                   new_volume_id=new_volume_id)

    def get_host_uptime(self, ctxt, host):
        # NOTE(russellb) Havana compat
        version = self._get_compat_version('3.0', '2.0')
        cctxt = self.client.prepare(server=host, version=version)
        return cctxt.call(ctxt, 'get_host_uptime')

    def reserve_block_device_name(self, ctxt, instance, device, volume_id):
        # NOTE(russellb) Havana compat
        version = self._get_compat_version('3.0', '2.3')
        instance_p = jsonutils.to_primitive(instance)
        cctxt = self.client.prepare(server=_compute_host(None, instance),
                version=version)
        return cctxt.call(ctxt, 'reserve_block_device_name',
                          instance=instance_p, device=device,
                          volume_id=volume_id)

    def backup_instance(self, ctxt, instance, image_id, backup_type,
                        rotation):
        # NOTE(russellb) Havana compat
        version = self._get_compat_version('3.0', '2.42')
        cctxt = self.client.prepare(server=_compute_host(None, instance),
                version=version)
        cctxt.cast(ctxt, 'backup_instance',
                   instance=instance,
                   image_id=image_id,
                   backup_type=backup_type,
                   rotation=rotation)

    def snapshot_instance(self, ctxt, instance, image_id):
        # NOTE(russellb) Havana compat
        version = self._get_compat_version('3.0', '2.42')
        cctxt = self.client.prepare(server=_compute_host(None, instance),
                version=version)
        cctxt.cast(ctxt, 'snapshot_instance',
                   instance=instance,
                   image_id=image_id)

    def start_instance(self, ctxt, instance):
        # NOTE(russellb) Havana compat
        version = self._get_compat_version('3.0', '2.29')
        cctxt = self.client.prepare(server=_compute_host(None, instance),
                version=version)
        cctxt.cast(ctxt, 'start_instance', instance=instance)

    def stop_instance(self, ctxt, instance, do_cast=True):
        # NOTE(russellb) Havana compat
        version = self._get_compat_version('3.0', '2.29')
        cctxt = self.client.prepare(server=_compute_host(None, instance),
                version=version)
        rpc_method = cctxt.cast if do_cast else cctxt.call
        return rpc_method(ctxt, 'stop_instance', instance=instance)

    def suspend_instance(self, ctxt, instance):
        # NOTE(russellb) Havana compat
        version = self._get_compat_version('3.0', '2.33')
        cctxt = self.client.prepare(server=_compute_host(None, instance),
                version=version)
        cctxt.cast(ctxt, 'suspend_instance', instance=instance)

    def terminate_instance(self, ctxt, instance, bdms, reservations=None):
        # NOTE(russellb) Havana compat
        version = self._get_compat_version('3.0', '2.35')
        bdms_p = jsonutils.to_primitive(bdms)
        cctxt = self.client.prepare(server=_compute_host(None, instance),
                version=version)
        cctxt.cast(ctxt, 'terminate_instance',
                   instance=instance, bdms=bdms_p,
                   reservations=reservations)

    def unpause_instance(self, ctxt, instance):
        # NOTE(russellb) Havana compat
        version = self._get_compat_version('3.0', '2.36')
        cctxt = self.client.prepare(server=_compute_host(None, instance),
                version=version)
        cctxt.cast(ctxt, 'unpause_instance', instance=instance)

    def unrescue_instance(self, ctxt, instance):
        # NOTE(russellb) Havana compat
        version = self._get_compat_version('3.0', '2.0')
        instance_p = jsonutils.to_primitive(instance)
        cctxt = self.client.prepare(server=_compute_host(None, instance),
                version=version)
        cctxt.cast(ctxt, 'unrescue_instance', instance=instance_p)

    def soft_delete_instance(self, ctxt, instance, reservations=None):
        # NOTE(russellb) Havana compat
        version = self._get_compat_version('3.0', '2.35')
        cctxt = self.client.prepare(server=_compute_host(None, instance),
                version=version)
        cctxt.cast(ctxt, 'soft_delete_instance',
                   instance=instance, reservations=reservations)

    def restore_instance(self, ctxt, instance):
        # NOTE(russellb) Havana compat
        version = self._get_compat_version('3.0', '2.0')
        instance_p = jsonutils.to_primitive(instance)
        cctxt = self.client.prepare(server=_compute_host(None, instance),
                version=version)
        cctxt.cast(ctxt, 'restore_instance', instance=instance_p)

    def shelve_instance(self, ctxt, instance, image_id=None):
        # NOTE(russellb) Havana compat
        version = self._get_compat_version('3.0', '2.31')
        cctxt = self.client.prepare(server=_compute_host(None, instance),
                version=version)
        cctxt.cast(ctxt, 'shelve_instance',
                   instance=instance, image_id=image_id)

    def shelve_offload_instance(self, ctxt, instance):
        # NOTE(russellb) Havana compat
        version = self._get_compat_version('3.0', '2.31')
        cctxt = self.client.prepare(server=_compute_host(None, instance),
                version=version)
        cctxt.cast(ctxt, 'shelve_offload_instance', instance=instance)

    def unshelve_instance(self, ctxt, instance, host, image=None):
        # NOTE(russellb) Havana compat
        version = self._get_compat_version('3.0', '2.31')
        cctxt = self.client.prepare(server=host, version=version)
        cctxt.cast(ctxt, 'unshelve_instance',
                   instance=instance, image=image)

    def volume_snapshot_create(self, ctxt, instance, volume_id,
                               create_info):
        # NOTE(russellb) Havana compat
        version = self._get_compat_version('3.0', '2.44')
        instance_p = jsonutils.to_primitive(instance)
        cctxt = self.client.prepare(server=_compute_host(None, instance),
                version=version)
        cctxt.cast(ctxt, 'volume_snapshot_create', instance=instance_p,
                   volume_id=volume_id, create_info=create_info)

    def volume_snapshot_delete(self, ctxt, instance, volume_id, snapshot_id,
                               delete_info):
        # NOTE(russellb) Havana compat
        version = self._get_compat_version('3.0', '2.44')
        instance_p = jsonutils.to_primitive(instance)
        cctxt = self.client.prepare(server=_compute_host(None, instance),
                version=version)
        cctxt.cast(ctxt, 'volume_snapshot_delete', instance=instance_p,
                   volume_id=volume_id, snapshot_id=snapshot_id,
                   delete_info=delete_info)


class SecurityGroupAPI(rpcclient.RpcProxy):
    '''Client side of the security group rpc API.

    API version history:

        1.0 - Initial version.
        1.41 - Adds refresh_instance_security_rules()

        2.0 - Remove 1.x backwards compat

        3.0 - Identical to 2.x, but has to be bumped at the same time as the
              compute API since it's all together on the server side.
    '''

    #
    # NOTE(russellb): This is the default minimum version that the server
    # (manager) side must implement unless otherwise specified using a version
    # argument to self.call()/cast()/etc. here.  It should be left as X.0 where
    # X is the current major API version (1.0, 2.0, ...).  For more information
    # about rpc API versioning, see the docs in
    # openstack/common/rpc/dispatcher.py.
    #
    BASE_RPC_API_VERSION = '3.0'

    def __init__(self):
        version_cap = ComputeAPI.VERSION_ALIASES.get(
                CONF.upgrade_levels.compute, CONF.upgrade_levels.compute)
        super(SecurityGroupAPI, self).__init__(
                topic=CONF.compute_topic,
                default_version=self.BASE_RPC_API_VERSION,
                version_cap=version_cap)
        self.client = self.get_client()

    def _get_compat_version(self, current, havana_compat):
        if not self.can_send_version(current):
            return havana_compat
        return current

    def refresh_security_group_rules(self, ctxt, security_group_id, host):
        # NOTE(russellb) Havana compat
        version = self._get_compat_version('3.0', '2.0')
        cctxt = self.client.prepare(server=host, version=version)
        cctxt.cast(ctxt, 'refresh_security_group_rules',
                   security_group_id=security_group_id)

    def refresh_security_group_members(self, ctxt, security_group_id,
            host):
        # NOTE(russellb) Havana compat
        version = self._get_compat_version('3.0', '2.0')
        cctxt = self.client.prepare(server=host, version=version)
        cctxt.cast(ctxt, 'refresh_security_group_members',
                   security_group_id=security_group_id)

    def refresh_instance_security_rules(self, ctxt, host, instance):
        # NOTE(russellb) Havana compat
        version = self._get_compat_version('3.0', '2.0')
        instance_p = jsonutils.to_primitive(instance)
        cctxt = self.client.prepare(server=_compute_host(None, instance),
                version=version)
        cctxt.cast(ctxt, 'refresh_instance_security_rules',
                   instance=instance_p)
