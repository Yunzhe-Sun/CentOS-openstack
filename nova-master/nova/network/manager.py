# vim: tabstop=4 shiftwidth=4 softtabstop=4

# Copyright (c) 2011 X.commerce, a business unit of eBay Inc.
# Copyright 2010 United States Government as represented by the
# Administrator of the National Aeronautics and Space Administration.
# All Rights Reserved.
# Copyright 2013 IBM Corp.
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

"""Network Hosts are responsible for allocating ips and setting up network.

There are multiple backend drivers that handle specific types of networking
topologies.  All of the network commands are issued to a subclass of
:class:`NetworkManager`.

**Related Flags**

:network_driver:  Driver to use for network creation
:flat_network_bridge:  Bridge device for simple network instances
:flat_interface:  FlatDhcp will bridge into this interface if set
:flat_network_dns:  Dns for simple network
:vlan_start:  First VLAN for private networks
:vpn_ip:  Public IP for the cloudpipe VPN servers
:vpn_start:  First Vpn port for private networks
:cnt_vpn_clients:  Number of addresses reserved for vpn clients
:network_size:  Number of addresses in each private subnet
:fixed_range:  Fixed IP address block
:fixed_ip_disassociate_timeout:  Seconds after which a deallocated ip
                                 is disassociated
:create_unique_mac_address_attempts:  Number of times to attempt creating
                                      a unique mac address

"""

import datetime
import itertools
import math
import re
import uuid

import eventlet
import netaddr
from oslo.config import cfg

from nova import context
from nova import exception
from nova import ipv6
from nova import manager
from nova.network import api as network_api
from nova.network import driver
from nova.network import floating_ips
from nova.network import model as network_model
from nova.network import rpcapi as network_rpcapi
from nova.network.security_group import openstack_driver
from nova.objects import instance as instance_obj
from nova.objects import instance_info_cache as info_cache_obj
from nova.openstack.common import excutils
from nova.openstack.common.gettextutils import _
from nova.openstack.common import importutils
from nova.openstack.common import jsonutils
from nova.openstack.common import log as logging
from nova.openstack.common import periodic_task
from nova.openstack.common.rpc import common as rpc_common
from nova.openstack.common import strutils
from nova.openstack.common import timeutils
from nova.openstack.common import uuidutils
from nova import quota
from nova import servicegroup
from nova import utils

LOG = logging.getLogger(__name__)


network_opts = [
    cfg.StrOpt('flat_network_bridge',
               help='Bridge for simple network instances'),
    cfg.StrOpt('flat_network_dns',
               default='8.8.4.4',
               help='Dns for simple network'),
    cfg.BoolOpt('flat_injected',
                default=False,
                help='Whether to attempt to inject network setup into guest'),
    cfg.StrOpt('flat_interface',
               help='FlatDhcp will bridge into this interface if set'),
    cfg.IntOpt('vlan_start',
               default=100,
               help='First VLAN for private networks'),
    cfg.StrOpt('vlan_interface',
               help='vlans will bridge into this interface if set'),
    cfg.IntOpt('num_networks',
               default=1,
               help='Number of networks to support'),
    cfg.StrOpt('vpn_ip',
               default='$my_ip',
               help='Public IP for the cloudpipe VPN servers'),
    cfg.IntOpt('vpn_start',
               default=1000,
               help='First Vpn port for private networks'),
    cfg.IntOpt('network_size',
               default=256,
               help='Number of addresses in each private subnet'),
    cfg.StrOpt('fixed_range_v6',
               default='fd00::/48',
               help='Fixed IPv6 address block'),
    cfg.StrOpt('gateway',
               help='Default IPv4 gateway'),
    cfg.StrOpt('gateway_v6',
               help='Default IPv6 gateway'),
    cfg.IntOpt('cnt_vpn_clients',
               default=0,
               help='Number of addresses reserved for vpn clients'),
    cfg.IntOpt('fixed_ip_disassociate_timeout',
               default=600,
               help='Seconds after which a deallocated ip is disassociated'),
    cfg.IntOpt('create_unique_mac_address_attempts',
               default=5,
               help='Number of attempts to create unique mac address'),
    cfg.BoolOpt('fake_network',
                default=False,
                help='If passed, use fake network devices and addresses'),
    cfg.BoolOpt('fake_call',
                default=False,
                help='If True, skip using the queue and make local calls'),
    cfg.BoolOpt('teardown_unused_network_gateway',
                default=False,
                help='If True, unused gateway devices (VLAN and bridge) are '
                     'deleted in VLAN network mode with multi hosted '
                     'networks'),
    cfg.BoolOpt('force_dhcp_release',
                default=True,
                help='If True, send a dhcp release on instance termination'),
    cfg.BoolOpt('share_dhcp_address',
                default=False,
                help='If True in multi_host mode, all compute hosts share '
                     'the same dhcp address. The same IP address used for '
                     'DHCP will be added on each nova-network node which '
                     'is only visible to the vms on the same host.'),
    cfg.BoolOpt('update_dns_entries',
                default=False,
                help='If True, when a DNS entry must be updated, it sends a '
                     'fanout cast to all network hosts to update their DNS '
                     'entries in multi host mode'),
    cfg.IntOpt("dns_update_periodic_interval",
               default=-1,
               help='Number of seconds to wait between runs of updates to DNS '
                    'entries.'),
    cfg.StrOpt('dhcp_domain',
               default='novalocal',
               help='domain to use for building the hostnames'),
    cfg.StrOpt('l3_lib',
               default='nova.network.l3.LinuxNetL3',
               help="Indicates underlying L3 management library"),
    ]

CONF = cfg.CONF
CONF.register_opts(network_opts)
CONF.import_opt('use_ipv6', 'nova.netconf')
CONF.import_opt('my_ip', 'nova.netconf')
CONF.import_opt('network_topic', 'nova.network.rpcapi')


class RPCAllocateFixedIP(object):
    """Mixin class originally for FlatDCHP and VLAN network managers.

    used since they share code to RPC.call allocate_fixed_ip on the
    correct network host to configure dnsmasq
    """

    servicegroup_api = None

    def _allocate_fixed_ips(self, context, instance_id, host, networks,
                            **kwargs):
        """Calls allocate_fixed_ip once for each network."""
        green_threads = []

        vpn = kwargs.get('vpn')
        requested_networks = kwargs.get('requested_networks')

        for network in networks:
            address = None
            if requested_networks is not None:
                for address in (fixed_ip for (uuid, fixed_ip) in
                                requested_networks if network['uuid'] == uuid):
                    break

            # NOTE(vish): if we are not multi_host pass to the network host
            # NOTE(tr3buchet): but if we are, host came from instance['host']
            if not network['multi_host']:
                host = network['host']
            # NOTE(vish): if there is no network host, set one
            if host is None:
                host = self.network_rpcapi.set_network_host(context, network)
            if host != self.host:
                # need to call allocate_fixed_ip to correct network host
                green_threads.append(eventlet.spawn(
                        self.network_rpcapi._rpc_allocate_fixed_ip,
                        context, instance_id, network['id'], address, vpn,
                        host))
            else:
                # i am the correct host, run here
                self.allocate_fixed_ip(context, instance_id, network,
                                       vpn=vpn, address=address)

        # wait for all of the allocates (if any) to finish
        for gt in green_threads:
            gt.wait()

    def _rpc_allocate_fixed_ip(self, context, instance_id, network_id,
                               **kwargs):
        """Sits in between _allocate_fixed_ips and allocate_fixed_ip to
        perform network lookup on the far side of rpc.
        """
        network = self._get_network_by_id(context, network_id)
        return self.allocate_fixed_ip(context, instance_id, network, **kwargs)

    def deallocate_fixed_ip(self, context, address, host=None, teardown=True):
        """Call the superclass deallocate_fixed_ip if i'm the correct host
        otherwise call to the correct host
        """
        fixed_ip = self.db.fixed_ip_get_by_address(context, address)
        network = self._get_network_by_id(context, fixed_ip['network_id'])

        # NOTE(vish): if we are not multi_host pass to the network host
        # NOTE(tr3buchet): but if we are, host came from instance['host']
        if not network['multi_host']:
            host = network['host']
        if host == self.host:
            # NOTE(vish): deallocate the fixed ip locally
            return super(RPCAllocateFixedIP, self).deallocate_fixed_ip(context,
                    address)

        if network['multi_host']:
            service = self.db.service_get_by_host_and_topic(context,
                                                            host,
                                                            CONF.network_topic)
            if not service or not self.servicegroup_api.service_is_up(service):
                # NOTE(vish): deallocate the fixed ip locally but don't
                #             teardown network devices
                return super(RPCAllocateFixedIP, self).deallocate_fixed_ip(
                        context, address, teardown=False)

        self.network_rpcapi.deallocate_fixed_ip(context, address, host)


class NetworkManager(manager.Manager):
    """Implements common network manager functionality.

    This class must be subclassed to support specific topologies.

    host management:
        hosts configure themselves for networks they are assigned to in the
        table upon startup. If there are networks in the table which do not
        have hosts, those will be filled in and have hosts configured
        as the hosts pick them up one at time during their periodic task.
        The one at a time part is to flatten the layout to help scale
    """

    RPC_API_VERSION = '1.10'

    # If True, this manager requires VIF to create a bridge.
    SHOULD_CREATE_BRIDGE = False

    # If True, this manager requires VIF to create VLAN tag.
    SHOULD_CREATE_VLAN = False

    # if True, this manager leverages DHCP
    DHCP = False

    timeout_fixed_ips = True

    required_create_args = []

    def __init__(self, network_driver=None, *args, **kwargs):
        self.driver = driver.load_network_driver(network_driver)
        self.instance_dns_manager = importutils.import_object(
                CONF.instance_dns_manager)
        self.instance_dns_domain = CONF.instance_dns_domain
        self.floating_dns_manager = importutils.import_object(
                CONF.floating_ip_dns_manager)
        self.network_api = network_api.API()
        self.network_rpcapi = network_rpcapi.NetworkAPI()
        self.security_group_api = (
            openstack_driver.get_openstack_security_group_driver())

        self.servicegroup_api = servicegroup.API()

        # NOTE(tr3buchet: unless manager subclassing NetworkManager has
        #                 already imported ipam, import nova ipam here
        if not hasattr(self, 'ipam'):
            self._import_ipam_lib('nova.network.nova_ipam_lib')
        l3_lib = kwargs.get("l3_lib", CONF.l3_lib)
        self.l3driver = importutils.import_object(l3_lib)

        self.quotas = quota.QUOTAS

        super(NetworkManager, self).__init__(service_name='network',
                                             *args, **kwargs)

    def _import_ipam_lib(self, ipam_lib):
        self.ipam = importutils.import_module(ipam_lib).get_ipam_lib(self)

    @utils.synchronized('get_dhcp')
    def _get_dhcp_ip(self, context, network_ref, host=None):
        """Get the proper dhcp address to listen on."""
        # NOTE(vish): this is for compatibility
        if not network_ref.get('multi_host') or CONF.share_dhcp_address:
            return network_ref['gateway']

        if not host:
            host = self.host
        network_id = network_ref['id']
        try:
            fip = self.db.fixed_ip_get_by_network_host(context,
                                                       network_id,
                                                       host)
            return fip['address']
        except exception.FixedIpNotFoundForNetworkHost:
            elevated = context.elevated()
            return self.db.fixed_ip_associate_pool(elevated,
                                                   network_id,
                                                   host=host)

    def get_dhcp_leases(self, ctxt, network_ref):
        """Broker the request to the driver to fetch the dhcp leases."""
        return self.driver.get_dhcp_leases(ctxt, network_ref)

    def init_host(self):
        """Do any initialization that needs to be run if this is a
        standalone service.
        """
        # NOTE(vish): Set up networks for which this host already has
        #             an ip address.
        ctxt = context.get_admin_context()
        for network in self.db.network_get_all_by_host(ctxt, self.host):
            self._setup_network_on_host(ctxt, network)
            if CONF.update_dns_entries:
                dev = self.driver.get_dev(network)
                self.driver.update_dns(ctxt, dev, network)

    @periodic_task.periodic_task
    def _disassociate_stale_fixed_ips(self, context):
        if self.timeout_fixed_ips:
            now = timeutils.utcnow()
            timeout = CONF.fixed_ip_disassociate_timeout
            time = now - datetime.timedelta(seconds=timeout)
            num = self.db.fixed_ip_disassociate_all_by_timeout(context,
                                                               self.host,
                                                               time)
            if num:
                LOG.debug(_('Disassociated %s stale fixed ip(s)'), num)

    def set_network_host(self, context, network_ref):
        """Safely sets the host of the network."""
        LOG.debug(_('setting network host'), context=context)
        host = self.db.network_set_host(context,
                                        network_ref['id'],
                                        self.host)
        return host

    def _do_trigger_security_group_members_refresh_for_instance(self,
                                                                instance_id):
        # NOTE(francois.charlier): the instance may have been deleted already
        # thus enabling `read_deleted`
        admin_context = context.get_admin_context(read_deleted='yes')
        instance = instance_obj.Instance.get_by_uuid(admin_context,
                                                     instance_id)

        try:
            # NOTE(vish): We need to make sure the instance info cache has been
            #             updated with new ip info before we trigger the
            #             security group refresh. This is somewhat ineffecient
            #             but avoids doing some dangerous refactoring for a
            #             bug fix.
            nw_info = self.get_instance_nw_info(admin_context, instance_id,
                                                None, None)
            ic = info_cache_obj.InstanceInfoCache.new(admin_context,
                                                      instance_id)
            ic.network_info = nw_info
            ic.save(update_cells=False)
        except exception.InstanceInfoCacheNotFound:
            pass
        groups = instance.security_groups
        group_ids = [group.id for group in groups]

        self.security_group_api.trigger_members_refresh(admin_context,
                                                        group_ids)

    def get_floating_ips_by_fixed_address(self, context, fixed_address):
        # NOTE(jkoelker) This is just a stub function. Managers supporting
        #                floating ips MUST override this or use the Mixin
        return []

    def get_instance_uuids_by_ip_filter(self, context, filters):
        fixed_ip_filter = filters.get('fixed_ip')
        ip_filter = re.compile(str(filters.get('ip')))
        ipv6_filter = re.compile(str(filters.get('ip6')))

        # NOTE(jkoelker) Should probably figure out a better way to do
        #                this. But for now it "works", this could suck on
        #                large installs.

        vifs = self.db.virtual_interface_get_all(context)
        results = []

        for vif in vifs:
            if vif['instance_uuid'] is None:
                continue

            network = self._get_network_by_id(context, vif['network_id'])
            fixed_ipv6 = None
            if network['cidr_v6'] is not None:
                fixed_ipv6 = ipv6.to_global(network['cidr_v6'],
                                            vif['address'],
                                            context.project_id)

            if fixed_ipv6 and ipv6_filter.match(fixed_ipv6):
                results.append({'instance_uuid': vif['instance_uuid'],
                                'ip': fixed_ipv6})

            vif_id = vif['id']
            fixed_ips = self.db.fixed_ips_by_virtual_interface(context,
                                                               vif_id)
            for fixed_ip in fixed_ips:
                if not fixed_ip or not fixed_ip['address']:
                    continue
                if fixed_ip['address'] == fixed_ip_filter:
                    results.append({'instance_uuid': vif['instance_uuid'],
                                    'ip': fixed_ip['address']})
                    continue
                if ip_filter.match(fixed_ip['address']):
                    results.append({'instance_uuid': vif['instance_uuid'],
                                    'ip': fixed_ip['address']})
                    continue
                for floating_ip in fixed_ip.get('floating_ips', []):
                    if not floating_ip or not floating_ip['address']:
                        continue
                    if ip_filter.match(floating_ip['address']):
                        results.append({'instance_uuid': vif['instance_uuid'],
                                        'ip': floating_ip['address']})
                        continue

        return results

    def _get_networks_for_instance(self, context, instance_id, project_id,
                                   requested_networks=None):
        """Determine & return which networks an instance should connect to."""
        # TODO(tr3buchet) maybe this needs to be updated in the future if
        #                 there is a better way to determine which networks
        #                 a non-vlan instance should connect to
        if requested_networks is not None and len(requested_networks) != 0:
            network_uuids = [uuid for (uuid, fixed_ip) in requested_networks]
            networks = self._get_networks_by_uuids(context, network_uuids)
        else:
            try:
                networks = self.db.network_get_all(context)
            except exception.NoNetworksFound:
                return []
        # return only networks which are not vlan networks
        return [network for network in networks if
                not network['vlan']]

    def allocate_for_instance(self, context, **kwargs):
        """Handles allocating the various network resources for an instance.

        rpc.called by network_api
        """
        instance_uuid = kwargs['instance_id']
        if not uuidutils.is_uuid_like(instance_uuid):
            instance_uuid = kwargs.get('instance_uuid')
        host = kwargs['host']
        project_id = kwargs['project_id']
        rxtx_factor = kwargs['rxtx_factor']
        requested_networks = kwargs.get('requested_networks')
        vpn = kwargs['vpn']
        macs = kwargs['macs']
        admin_context = context.elevated()
        LOG.debug(_("network allocations"), instance_uuid=instance_uuid,
                  context=context)
        networks = self._get_networks_for_instance(admin_context,
                                        instance_uuid, project_id,
                                        requested_networks=requested_networks)
        networks_list = [self._get_network_dict(network)
                                 for network in networks]
        LOG.debug(_('networks retrieved for instance: |%s|'),
                  networks_list, context=context, instance_uuid=instance_uuid)

        try:
            self._allocate_mac_addresses(context, instance_uuid, networks,
                                         macs)
        except Exception as e:
            with excutils.save_and_reraise_exception():
                # If we fail to allocate any one mac address, clean up all
                # allocated VIFs
                self.db.virtual_interface_delete_by_instance(context,
                                                             instance_uuid)

        self._allocate_fixed_ips(admin_context, instance_uuid,
                                 host, networks, vpn=vpn,
                                 requested_networks=requested_networks)

        if CONF.update_dns_entries:
            network_ids = [network['id'] for network in networks]
            self.network_rpcapi.update_dns(context, network_ids)

        return self.get_instance_nw_info(context, instance_uuid, rxtx_factor,
                                         host)

    def deallocate_for_instance(self, context, **kwargs):
        """Handles deallocating various network resources for an instance.

        rpc.called by network_api
        kwargs can contain fixed_ips to circumvent another db lookup
        """
        # NOTE(francois.charlier): in some cases the instance might be
        # deleted before the IPs are released, so we need to get deleted
        # instances too
        read_deleted_context = context.elevated(read_deleted='yes')
        instance_uuid = kwargs['instance_id']
        if not uuidutils.is_uuid_like(instance_uuid):
            instance = self.db.instance_get(read_deleted_context,
                                            instance_uuid)
            instance_uuid = instance['uuid']

        host = kwargs.get('host')

        try:
            fixed_ips = (kwargs.get('fixed_ips') or
                         self.db.fixed_ip_get_by_instance(read_deleted_context,
                                                          instance_uuid))
        except exception.FixedIpNotFoundForInstance:
            fixed_ips = []
        LOG.debug(_("network deallocation for instance"),
                  context=context, instance_uuid=instance_uuid)
        # deallocate fixed ips
        for fixed_ip in fixed_ips:
            self.deallocate_fixed_ip(context, fixed_ip['address'], host=host)

        if CONF.update_dns_entries:
            network_ids = [fixed_ip['network_id'] for fixed_ip in fixed_ips]
            self.network_rpcapi.update_dns(context, network_ids)

        # deallocate vifs (mac addresses)
        self.db.virtual_interface_delete_by_instance(read_deleted_context,
                                                     instance_uuid)

    @rpc_common.client_exceptions(exception.InstanceNotFound)
    def get_instance_nw_info(self, context, instance_id, rxtx_factor,
                             host, instance_uuid=None, **kwargs):
        """Creates network info list for instance.

        called by allocate_for_instance and network_api
        context needs to be elevated
        :returns: network info list [(network,info),(network,info)...]
        where network = dict containing pertinent data from a network db object
        and info = dict containing pertinent networking data
        """
        use_subordinate = kwargs.get('use_subordinate') or False

        if not uuidutils.is_uuid_like(instance_id):
            instance_id = instance_uuid
        instance_uuid = instance_id

        # TODO(geekinutah): Is this worth objectifying as it's slated for
        #                   deprecation?
        vifs = self.db.virtual_interface_get_by_instance(context,
                                                         instance_uuid,
                                                         use_subordinate=use_subordinate)
        networks = {}

        for vif in vifs:
            if vif.get('network_id') is not None:
                network = self._get_network_by_id(context, vif['network_id'])
                networks[vif['uuid']] = network

        nw_info = self.build_network_info_model(context, vifs, networks,
                                                         rxtx_factor, host)
        return nw_info

    def build_network_info_model(self, context, vifs, networks,
                                 rxtx_factor, instance_host):
        """Builds a NetworkInfo object containing all network information
        for an instance.
        """
        nw_info = network_model.NetworkInfo()
        for vif in vifs:
            vif_dict = {'id': vif['uuid'],
                        'type': network_model.VIF_TYPE_BRIDGE,
                        'address': vif['address']}

            # handle case where vif doesn't have a network
            if not networks.get(vif['uuid']):
                vif = network_model.VIF(**vif_dict)
                nw_info.append(vif)
                continue

            # get network dict for vif from args and build the subnets
            network = networks[vif['uuid']]
            subnets = self._get_subnets_from_network(context, network, vif,
                                                     instance_host)

            # if rxtx_cap data are not set everywhere, set to none
            try:
                rxtx_cap = network['rxtx_base'] * rxtx_factor
            except (TypeError, KeyError):
                rxtx_cap = None

            # get fixed_ips
            v4_IPs = self.ipam.get_v4_ips_by_interface(context,
                                                       network['uuid'],
                                                       vif['uuid'],
                                                       network['project_id'])
            v6_IPs = self.ipam.get_v6_ips_by_interface(context,
                                                       network['uuid'],
                                                       vif['uuid'],
                                                       network['project_id'])

            # create model FixedIPs from these fixed_ips
            network_IPs = [network_model.FixedIP(address=ip_address)
                           for ip_address in v4_IPs + v6_IPs]

            # get floating_ips for each fixed_ip
            # add them to the fixed ip
            for fixed_ip in network_IPs:
                if fixed_ip['version'] == 6:
                    continue
                gfipbfa = self.ipam.get_floating_ips_by_fixed_address
                floating_ips = gfipbfa(context, fixed_ip['address'])
                floating_ips = [network_model.IP(address=ip['address'],
                                                 type='floating')
                                for ip in floating_ips]
                for ip in floating_ips:
                    fixed_ip.add_floating_ip(ip)

            # add ips to subnets they belong to
            for subnet in subnets:
                subnet['ips'] = [fixed_ip for fixed_ip in network_IPs
                                 if fixed_ip.is_in_subnet(subnet)]

            # convert network into a Network model object
            network = network_model.Network(**self._get_network_dict(network))

            # since network currently has no subnets, easily add them all
            network['subnets'] = subnets

            # add network and rxtx cap to vif_dict
            vif_dict['network'] = network
            if rxtx_cap:
                vif_dict['rxtx_cap'] = rxtx_cap

            # create the vif model and add to network_info
            vif = network_model.VIF(**vif_dict)
            nw_info.append(vif)

        return nw_info

    def _get_network_dict(self, network):
        """Returns the dict representing necessary and meta network fields."""
        # get generic network fields
        network_dict = {'id': network['uuid'],
                        'bridge': network['bridge'],
                        'label': network['label'],
                        'tenant_id': network['project_id']}

        # get extra information
        if network.get('injected'):
            network_dict['injected'] = network['injected']

        return network_dict

    def _get_subnets_from_network(self, context, network,
                                  vif, instance_host=None):
        """Returns the 1 or 2 possible subnets for a nova network."""
        # get subnets
        ipam_subnets = self.ipam.get_subnets_by_net_id(context,
                           network['project_id'], network['uuid'], vif['uuid'])

        subnets = []
        for subnet in ipam_subnets:
            subnet_dict = {'cidr': subnet['cidr'],
                           'gateway': network_model.IP(
                                             address=subnet['gateway'],
                                             type='gateway')}
            # deal with dhcp
            if self.DHCP:
                if network.get('multi_host'):
                    dhcp_server = self._get_dhcp_ip(context, network,
                                                    instance_host)
                else:
                    dhcp_server = self._get_dhcp_ip(context, subnet)
                subnet_dict['dhcp_server'] = dhcp_server

            subnet_object = network_model.Subnet(**subnet_dict)

            # add dns info
            for k in ['dns1', 'dns2']:
                if subnet.get(k):
                    subnet_object.add_dns(
                         network_model.IP(address=subnet[k], type='dns'))

            # get the routes for this subnet
            # NOTE(tr3buchet): default route comes from subnet gateway
            if subnet.get('id'):
                routes = self.ipam.get_routes_by_ip_block(context,
                                         subnet['id'], network['project_id'])
                for route in routes:
                    cidr = netaddr.IPNetwork('%s/%s' % (route['destination'],
                                                        route['netmask'])).cidr
                    subnet_object.add_route(
                            network_model.Route(cidr=str(cidr),
                                                gateway=network_model.IP(
                                                    address=route['gateway'],
                                                    type='gateway')))

            subnets.append(subnet_object)

        return subnets

    def _allocate_mac_addresses(self, context, instance_uuid, networks, macs):
        """Generates mac addresses and creates vif rows in db for them."""
        # make a copy we can mutate
        if macs is not None:
            available_macs = set(macs)

        for network in networks:
            if macs is None:
                self._add_virtual_interface(context, instance_uuid,
                                           network['id'])
            else:
                try:
                    mac = available_macs.pop()
                except KeyError:
                    raise exception.VirtualInterfaceCreateException()
                self._add_virtual_interface(context, instance_uuid,
                                           network['id'], mac)

    def _add_virtual_interface(self, context, instance_uuid, network_id,
                              mac=None):
        vif = {'address': mac,
               'instance_uuid': instance_uuid,
               'network_id': network_id,
               'uuid': str(uuid.uuid4())}

        if mac is None:
            vif['address'] = utils.generate_mac_address()
            attempts = CONF.create_unique_mac_address_attempts
        else:
            attempts = 1

        for i in range(attempts):
            try:
                return self.db.virtual_interface_create(context, vif)
            except exception.VirtualInterfaceCreateException:
                vif['address'] = utils.generate_mac_address()
        else:
            raise exception.VirtualInterfaceMacAddressException()

    def add_fixed_ip_to_instance(self, context, instance_id, host, network_id,
                                 rxtx_factor=None):
        """Adds a fixed ip to an instance from specified network."""
        if uuidutils.is_uuid_like(network_id):
            network = self.get_network(context, network_id)
        else:
            network = self._get_network_by_id(context, network_id)
        self._allocate_fixed_ips(context, instance_id, host, [network])
        return self.get_instance_nw_info(context, instance_id, rxtx_factor,
                                         host)

    # NOTE(russellb) This method can be removed in 2.0 of this API.  It is
    # deprecated in favor of the method in the base API.
    def get_backdoor_port(self, context):
        """Return backdoor port for eventlet_backdoor."""
        return self.backdoor_port

    def remove_fixed_ip_from_instance(self, context, instance_id, host,
                                      address, rxtx_factor=None):
        """Removes a fixed ip from an instance from specified network."""
        fixed_ips = self.db.fixed_ip_get_by_instance(context, instance_id)
        for fixed_ip in fixed_ips:
            if fixed_ip['address'] == address:
                self.deallocate_fixed_ip(context, address, host)
                # NOTE(vish): this probably isn't a dhcp ip so just
                #             deallocate it now. In the extremely rare
                #             case that this is a race condition, we
                #             will just get a warn in lease or release.
                if not fixed_ip.get('leased'):
                    self.db.fixed_ip_disassociate(context, address)
                return self.get_instance_nw_info(context, instance_id,
                                                 rxtx_factor, host)
        raise exception.FixedIpNotFoundForSpecificInstance(
                                    instance_uuid=instance_id, ip=address)

    def _validate_instance_zone_for_dns_domain(self, context, instance):
        if not self.instance_dns_domain:
            return True
        instance_domain = self.instance_dns_domain

        domainref = self.db.dnsdomain_get(context, instance_domain)
        if domainref is None:
            LOG.warn(_('instance-dns-zone not found |%s|.'),
                     instance_domain, instance=instance)
            return True
        dns_zone = domainref.availability_zone

        instance_zone = instance.get('availability_zone')
        if dns_zone and (dns_zone != instance_zone):
            LOG.warn(_('instance-dns-zone is |%(domain)s|, '
                       'which is in availability zone |%(zone)s|. '
                       'Instance is in zone |%(zone2)s|. '
                       'No DNS record will be created.'),
                     {'domain': instance_domain,
                      'zone': dns_zone,
                      'zone2': instance_zone},
                     instance=instance)
            return False
        else:
            return True

    def allocate_fixed_ip(self, context, instance_id, network, **kwargs):
        """Gets a fixed ip from the pool."""
        # TODO(vish): when this is called by compute, we can associate compute
        #             with a network, or a cluster of computes with a network
        #             and use that network here with a method like
        #             network_get_by_compute_host
        address = None

        # Check the quota; can't put this in the API because we get
        # called into from other places
        try:
            reservations = self.quotas.reserve(context, fixed_ips=1)
        except exception.OverQuota:
            LOG.warn(_("Quota exceeded for %s, tried to allocate "
                       "fixed IP"), context.project_id)
            raise exception.FixedIpLimitExceeded()

        try:
            if network['cidr']:
                address = kwargs.get('address', None)
                if address:
                    address = self.db.fixed_ip_associate(context,
                                                         address,
                                                         instance_id,
                                                         network['id'])
                else:
                    address = self.db.fixed_ip_associate_pool(
                        context.elevated(), network['id'], instance_id)
                get_vif = self.db.virtual_interface_get_by_instance_and_network
                vif = get_vif(context, instance_id, network['id'])
                values = {'allocated': True,
                          'virtual_interface_id': vif['id']}
                self.db.fixed_ip_update(context, address, values)
                self._do_trigger_security_group_members_refresh_for_instance(
                    instance_id)

            # NOTE(vish) This db query could be removed if we pass az and name
            #            (or the whole instance object).
            instance = self.db.instance_get_by_uuid(context, instance_id)
            name = instance['display_name']

            if self._validate_instance_zone_for_dns_domain(context, instance):
                self.instance_dns_manager.create_entry(
                    name, address, "A", self.instance_dns_domain)
                self.instance_dns_manager.create_entry(
                    instance_id, address, "A", self.instance_dns_domain)
            self._setup_network_on_host(context, network)

            self.quotas.commit(context, reservations)
            return address

        except Exception:
            with excutils.save_and_reraise_exception():
                self.quotas.rollback(context, reservations)

    def deallocate_fixed_ip(self, context, address, host=None, teardown=True):
        """Returns a fixed ip to the pool."""
        fixed_ip_ref = self.db.fixed_ip_get_by_address(context, address)
        instance_uuid = fixed_ip_ref['instance_uuid']
        vif_id = fixed_ip_ref['virtual_interface_id']

        # NOTE(vish) This db query could be removed if we pass az and name
        #            (or the whole instance object).
        instance = self.db.instance_get_by_uuid(
                context.elevated(read_deleted='yes'),
                instance_uuid)
        project_id = instance.project_id
        try:
            reservations = self.quotas.reserve(context,
                                               project_id=project_id,
                                               fixed_ips=-1)
        except Exception:
            reservations = None
            LOG.exception(_("Failed to update usages deallocating "
                            "fixed IP"))

        self._do_trigger_security_group_members_refresh_for_instance(
            instance_uuid)

        if self._validate_instance_zone_for_dns_domain(context, instance):
            for n in self.instance_dns_manager.get_entries_by_address(address,
                                                     self.instance_dns_domain):
                self.instance_dns_manager.delete_entry(n,
                                                      self.instance_dns_domain)

        self.db.fixed_ip_update(context, address,
                                {'allocated': False,
                                 'virtual_interface_id': None})

        if teardown:
            network = self._get_network_by_id(context,
                                              fixed_ip_ref['network_id'])

            if CONF.force_dhcp_release:
                dev = self.driver.get_dev(network)
                # NOTE(vish): The below errors should never happen, but there
                #             may be a race condition that is causing them per
                #             https://code.launchpad.net/bugs/968457, so we log
                #             an error to help track down the possible race.
                msg = _("Unable to release %s because vif doesn't exist.")
                if not vif_id:
                    LOG.error(msg % address)
                    return

                vif = self.db.virtual_interface_get(context, vif_id)

                if not vif:
                    LOG.error(msg % address)
                    return

                # NOTE(cfb): Call teardown before release_dhcp to ensure
                #            that the IP can't be re-leased after a release
                #            packet is sent.
                self._teardown_network_on_host(context, network)
                # NOTE(vish): This forces a packet so that the release_fixed_ip
                #             callback will get called by nova-dhcpbridge.
                self.driver.release_dhcp(dev, address, vif['address'])

                # NOTE(yufang521247): This is probably a failed dhcp fixed ip.
                # DHCPRELEASE packet sent to dnsmasq would not trigger
                # dhcp-bridge to run. Thus it is better to disassociate such
                # fixed ip here.
                fixed_ip_ref = self.db.fixed_ip_get_by_address(context,
                                                               address)
                if (instance_uuid == fixed_ip_ref['instance_uuid'] and
                        not fixed_ip_ref.get('leased')):
                    self.db.fixed_ip_disassociate(context, address)

            else:
                # We can't try to free the IP address so just call teardown
                self._teardown_network_on_host(context, network)

        # Commit the reservations
        if reservations:
            self.quotas.commit(context, reservations, project_id=project_id)

    def lease_fixed_ip(self, context, address):
        """Called by dhcp-bridge when ip is leased."""
        LOG.debug(_('Leased IP |%s|'), address, context=context)
        fixed_ip = self.db.fixed_ip_get_by_address(context, address)

        if fixed_ip['instance_uuid'] is None:
            LOG.warn(_('IP %s leased that is not associated'), address,
                       context=context)
            return
        now = timeutils.utcnow()
        self.db.fixed_ip_update(context,
                                fixed_ip['address'],
                                {'leased': True,
                                 'updated_at': now})
        if not fixed_ip['allocated']:
            LOG.warn(_('IP |%s| leased that isn\'t allocated'), address,
                     context=context)

    def release_fixed_ip(self, context, address):
        """Called by dhcp-bridge when ip is released."""
        LOG.debug(_('Released IP |%s|'), address, context=context)
        fixed_ip = self.db.fixed_ip_get_by_address(context, address)

        if fixed_ip['instance_uuid'] is None:
            LOG.warn(_('IP %s released that is not associated'), address,
                       context=context)
            return
        if not fixed_ip['leased']:
            LOG.warn(_('IP %s released that was not leased'), address,
                     context=context)
        self.db.fixed_ip_update(context,
                                fixed_ip['address'],
                                {'leased': False})
        if not fixed_ip['allocated']:
            self.db.fixed_ip_disassociate(context, address)

    @staticmethod
    def _convert_int_args(kwargs):
        int_args = ("network_size", "num_networks",
                    "vlan_start", "vpn_start")
        for key in int_args:
            try:
                value = kwargs.get(key)
                if value is None:
                    continue
                kwargs[key] = int(value)
            except ValueError:
                raise ValueError(_("%s must be an integer") % key)

    def create_networks(self, context,
                        label, cidr=None, multi_host=None, num_networks=None,
                        network_size=None, cidr_v6=None,
                        gateway=None, gateway_v6=None, bridge=None,
                        bridge_interface=None, dns1=None, dns2=None,
                        fixed_cidr=None, **kwargs):
        arg_names = ("label", "cidr", "multi_host", "num_networks",
                     "network_size", "cidr_v6",
                     "gateway", "gateway_v6", "bridge",
                     "bridge_interface", "dns1", "dns2",
                     "fixed_cidr")
        for name in arg_names:
            kwargs[name] = locals()[name]
        self._convert_int_args(kwargs)

        # check for certain required inputs
        label = kwargs["label"]
        if not label:
            raise exception.NetworkNotCreated(req="label")

        # Size of "label" column in nova.networks is 255, hence the restriction
        if len(label) > 255:
            raise ValueError(_("Maximum allowed length for 'label' is 255."))

        if not (kwargs["cidr"] or kwargs["cidr_v6"]):
            raise exception.NetworkNotCreated(req="cidr or cidr_v6")

        kwargs["bridge"] = kwargs["bridge"] or CONF.flat_network_bridge
        kwargs["bridge_interface"] = (kwargs["bridge_interface"] or
                                      CONF.flat_interface)

        for fld in self.required_create_args:
            if not kwargs[fld]:
                raise exception.NetworkNotCreated(req=fld)

        kwargs["num_networks"] = kwargs["num_networks"] or CONF.num_networks
        if not kwargs["network_size"]:
            if kwargs["cidr"]:
                fixnet = netaddr.IPNetwork(kwargs["cidr"])
                each_subnet_size = fixnet.size / kwargs["num_networks"]
                if each_subnet_size > CONF.network_size:
                    subnet = 32 - int(math.log(CONF.network_size, 2))
                    oversize_msg = _(
                        'Subnet(s) too large, defaulting to /%s.'
                        '  To override, specify network_size flag.') % subnet
                    LOG.warn(oversize_msg)
                    kwargs["network_size"] = CONF.network_size
                else:
                    kwargs["network_size"] = fixnet.size
            else:
                kwargs["network_size"] = CONF.network_size

        kwargs["multi_host"] = (
            CONF.multi_host
            if kwargs["multi_host"] is None
            else strutils.bool_from_string(kwargs["multi_host"]))

        kwargs["vlan_start"] = kwargs.get("vlan_start") or CONF.vlan_start
        kwargs["vpn_start"] = kwargs.get("vpn_start") or CONF.vpn_start
        kwargs["dns1"] = kwargs["dns1"] or CONF.flat_network_dns

        if kwargs["fixed_cidr"]:
            kwargs["fixed_cidr"] = netaddr.IPNetwork(kwargs["fixed_cidr"])

        return self._do_create_networks(context, **kwargs)

    def _do_create_networks(self, context,
                            label, cidr, multi_host, num_networks,
                            network_size, cidr_v6, gateway, gateway_v6, bridge,
                            bridge_interface, dns1=None, dns2=None,
                            fixed_cidr=None, **kwargs):
        """Create networks based on parameters."""
        # NOTE(jkoelker): these are dummy values to make sure iter works
        # TODO(tr3buchet): disallow carving up networks
        fixed_net_v4 = netaddr.IPNetwork('0/32')
        fixed_net_v6 = netaddr.IPNetwork('::0/128')
        subnets_v4 = []
        subnets_v6 = []

        if kwargs.get('ipam'):
            if cidr_v6:
                subnets_v6 = [netaddr.IPNetwork(cidr_v6)]
            if cidr:
                subnets_v4 = [netaddr.IPNetwork(cidr)]
        else:
            subnet_bits = int(math.ceil(math.log(network_size, 2)))
            if cidr_v6:
                fixed_net_v6 = netaddr.IPNetwork(cidr_v6)
                prefixlen_v6 = 128 - subnet_bits
                # smallest subnet in IPv6 ethernet network is /64
                if prefixlen_v6 > 64:
                    prefixlen_v6 = 64
                subnets_v6 = fixed_net_v6.subnet(prefixlen_v6,
                                                 count=num_networks)
            if cidr:
                fixed_net_v4 = netaddr.IPNetwork(cidr)
                prefixlen_v4 = 32 - subnet_bits
                subnets_v4 = list(fixed_net_v4.subnet(prefixlen_v4,
                                                      count=num_networks))

        if cidr:
            # NOTE(jkoelker): This replaces the _validate_cidrs call and
            #                 prevents looping multiple times
            try:
                nets = self.db.network_get_all(context)
            except exception.NoNetworksFound:
                nets = []
            num_used_nets = len(nets)
            used_subnets = [netaddr.IPNetwork(net['cidr']) for net in nets]

            def find_next(subnet):
                next_subnet = subnet.next()
                while next_subnet in subnets_v4:
                    next_subnet = next_subnet.next()
                if next_subnet in fixed_net_v4:
                    return next_subnet

            for subnet in list(subnets_v4):
                if subnet in used_subnets:
                    next_subnet = find_next(subnet)
                    if next_subnet:
                        subnets_v4.remove(subnet)
                        subnets_v4.append(next_subnet)
                        subnet = next_subnet
                    else:
                        raise exception.CidrConflict(_('cidr already in use'))
                for used_subnet in used_subnets:
                    if subnet in used_subnet:
                        msg = _('requested cidr (%(cidr)s) conflicts with '
                                'existing supernet (%(super)s)')
                        raise exception.CidrConflict(
                                  msg % {'cidr': subnet, 'super': used_subnet})
                    if used_subnet in subnet:
                        next_subnet = find_next(subnet)
                        if next_subnet:
                            subnets_v4.remove(subnet)
                            subnets_v4.append(next_subnet)
                            subnet = next_subnet
                        else:
                            msg = _('requested cidr (%(cidr)s) conflicts '
                                    'with existing smaller cidr '
                                    '(%(smaller)s)')
                            raise exception.CidrConflict(
                                msg % {'cidr': subnet, 'smaller': used_subnet})

        networks = []
        subnets = itertools.izip_longest(subnets_v4, subnets_v6)
        for index, (subnet_v4, subnet_v6) in enumerate(subnets):
            net = {}
            net['bridge'] = bridge
            net['bridge_interface'] = bridge_interface
            net['multi_host'] = multi_host

            net['dns1'] = dns1
            net['dns2'] = dns2

            net['project_id'] = kwargs.get('project_id')

            if num_networks > 1:
                net['label'] = '%s_%d' % (label, index)
            else:
                net['label'] = label

            if cidr and subnet_v4:
                net['cidr'] = str(subnet_v4)
                net['netmask'] = str(subnet_v4.netmask)
                net['gateway'] = gateway or str(subnet_v4[1])
                net['broadcast'] = str(subnet_v4.broadcast)
                net['dhcp_start'] = str(subnet_v4[2])

            if cidr_v6 and subnet_v6:
                net['cidr_v6'] = str(subnet_v6)
                if gateway_v6:
                    # use a pre-defined gateway if one is provided
                    net['gateway_v6'] = str(gateway_v6)
                else:
                    net['gateway_v6'] = str(subnet_v6[1])

                net['netmask_v6'] = str(subnet_v6._prefixlen)

            if CONF.network_manager == 'nova.network.manager.VlanManager':
                vlan = kwargs.get('vlan', None)
                if not vlan:
                    index_vlan = index + num_used_nets
                    vlan = kwargs['vlan_start'] + index_vlan
                    used_vlans = [x['vlan'] for x in nets]
                    if vlan in used_vlans:
                        # That vlan is used, try to get another one
                        used_vlans.sort()
                        vlan = used_vlans[-1] + 1

                net['vpn_private_address'] = str(subnet_v4[2])
                net['dhcp_start'] = str(subnet_v4[3])
                net['vlan'] = vlan
                net['bridge'] = 'br%s' % vlan

                # NOTE(vish): This makes ports unique across the cloud, a more
                #             robust solution would be to make them uniq per ip
                index_vpn = index + num_used_nets
                net['vpn_public_port'] = kwargs['vpn_start'] + index_vpn

            # None if network with cidr or cidr_v6 already exists
            network = self.db.network_create_safe(context, net)

            if not network:
                raise ValueError(_('Network already exists!'))
            else:
                networks.append(network)

            if network and cidr and subnet_v4:
                self._create_fixed_ips(context, network['id'], fixed_cidr)
        return jsonutils.to_primitive(networks)

    def delete_network(self, context, fixed_range, uuid,
            require_disassociated=True):

        # Prefer uuid but we'll also take cidr for backwards compatibility
        elevated = context.elevated()
        if uuid:
            network = self.db.network_get_by_uuid(elevated, uuid)
        elif fixed_range:
            network = self.db.network_get_by_cidr(elevated, fixed_range)

        if require_disassociated and network['project_id'] is not None:
            raise ValueError(_('Network must be disassociated from project %s'
                               ' before delete') % network['project_id'])
        self.db.network_delete_safe(context, network['id'])

    @property
    def _bottom_reserved_ips(self):  # pylint: disable=R0201
        """Number of reserved ips at the bottom of the range."""
        return 2  # network, gateway

    @property
    def _top_reserved_ips(self):  # pylint: disable=R0201
        """Number of reserved ips at the top of the range."""
        return 1  # broadcast

    def _create_fixed_ips(self, context, network_id, fixed_cidr=None):
        """Create all fixed ips for network."""
        network = self._get_network_by_id(context, network_id)
        # NOTE(vish): Should these be properties of the network as opposed
        #             to properties of the manager class?
        bottom_reserved = self._bottom_reserved_ips
        top_reserved = self._top_reserved_ips
        if not fixed_cidr:
            fixed_cidr = netaddr.IPNetwork(network['cidr'])
        num_ips = len(fixed_cidr)
        ips = []
        for index in range(num_ips):
            address = str(fixed_cidr[index])
            if index < bottom_reserved or num_ips - index <= top_reserved:
                reserved = True
            else:
                reserved = False

            ips.append({'network_id': network_id,
                        'address': address,
                        'reserved': reserved})
        self.db.fixed_ip_bulk_create(context, ips)

    def _allocate_fixed_ips(self, context, instance_id, host, networks,
                            **kwargs):
        """Calls allocate_fixed_ip once for each network."""
        raise NotImplementedError()

    def setup_networks_on_host(self, context, instance_id, host,
                               teardown=False):
        """calls setup/teardown on network hosts for an instance."""
        green_threads = []

        if teardown:
            call_func = self._teardown_network_on_host
        else:
            call_func = self._setup_network_on_host

        instance = self.db.instance_get(context, instance_id)
        vifs = self.db.virtual_interface_get_by_instance(context,
                                                         instance['uuid'])
        for vif in vifs:
            network = self.db.network_get(context, vif['network_id'])
            if not network['multi_host']:
                #NOTE (tr3buchet): if using multi_host, host is instance[host]
                host = network['host']
            if self.host == host or host is None:
                # at this point i am the correct host, or host doesn't
                # matter -> FlatManager
                call_func(context, network)
            else:
                # i'm not the right host, run call on correct host
                green_threads.append(eventlet.spawn(
                        self.network_rpcapi.rpc_setup_network_on_host, context,
                        network['id'], teardown, host))

        # wait for all of the setups (if any) to finish
        for gt in green_threads:
            gt.wait()

    def rpc_setup_network_on_host(self, context, network_id, teardown):
        if teardown:
            call_func = self._teardown_network_on_host
        else:
            call_func = self._setup_network_on_host

        # subcall from original setup_networks_on_host
        network = self.db.network_get(context, network_id)
        call_func(context, network)

    def _setup_network_on_host(self, context, network):
        """Sets up network on this host."""
        raise NotImplementedError()

    def _teardown_network_on_host(self, context, network):
        """Sets up network on this host."""
        raise NotImplementedError()

    def validate_networks(self, context, networks):
        """check if the networks exists and host
        is set to each network.
        """
        if networks is None or len(networks) == 0:
            return

        network_uuids = [uuid for (uuid, fixed_ip) in networks]

        self._get_networks_by_uuids(context, network_uuids)

        for network_uuid, address in networks:
            # check if the fixed IP address is valid and
            # it actually belongs to the network
            if address is not None:
                if not utils.is_valid_ipv4(address):
                    raise exception.FixedIpInvalid(address=address)

                fixed_ip_ref = self.db.fixed_ip_get_by_address(context,
                                                               address)
                network = self._get_network_by_id(context,
                                                  fixed_ip_ref['network_id'])
                if network['uuid'] != network_uuid:
                    raise exception.FixedIpNotFoundForNetwork(
                        address=address, network_uuid=network_uuid)
                if fixed_ip_ref['instance_uuid'] is not None:
                    raise exception.FixedIpAlreadyInUse(
                        address=address,
                        instance_uuid=fixed_ip_ref['instance_uuid'])

    def _get_network_by_id(self, context, network_id):
        return self.db.network_get(context, network_id,
                                   project_only="allow_none")

    def _get_networks_by_uuids(self, context, network_uuids):
        networks = self.db.network_get_all_by_uuids(context, network_uuids,
                                                    project_only="allow_none")
        networks.sort(key=lambda x: network_uuids.index(x['uuid']))
        return networks

    def get_vifs_by_instance(self, context, instance_id):
        """Returns the vifs associated with an instance."""
        # NOTE(vish): This is no longer used but can't be removed until
        #             we major version the network_rpcapi to 2.0.
        instance = self.db.instance_get(context, instance_id)
        vifs = self.db.virtual_interface_get_by_instance(context,
                                                         instance['uuid'])
        for vif in vifs:
            if vif.get('network_id') is not None:
                network = self._get_network_by_id(context, vif['network_id'])
                vif['net_uuid'] = network['uuid']
        return [dict(vif.iteritems()) for vif in vifs]

    def get_instance_id_by_floating_address(self, context, address):
        """Returns the instance id a floating ip's fixed ip is allocated to."""
        # NOTE(vish): This is no longer used but can't be removed until
        #             we major version the network_rpcapi to 2.0.
        fixed_ip = self.db.fixed_ip_get_by_floating_address(context, address)
        if fixed_ip is None:
            return None
        else:
            return fixed_ip['instance_uuid']

    def get_network(self, context, network_uuid):
        # NOTE(vish): used locally

        network = self.db.network_get_by_uuid(context.elevated(), network_uuid)
        return jsonutils.to_primitive(network)

    def get_all_networks(self, context):
        # NOTE(vish): This is no longer used but can't be removed until
        #             we major version the network_rpcapi to 2.0.
        try:
            networks = self.db.network_get_all(context)
        except exception.NoNetworksFound:
            return []
        return [jsonutils.to_primitive(network) for network in networks]

    def disassociate_network(self, context, network_uuid):
        # NOTE(vish): This is no longer used but can't be removed until
        #             we major version the network_rpcapi to 2.0.
        network = self.get_network(context, network_uuid)
        self.db.network_disassociate(context, network['id'])

    def get_fixed_ip(self, context, id):
        """Return a fixed ip."""
        # NOTE(vish): This is no longer used but can't be removed until
        #             we major version the network_rpcapi to 2.0.
        fixed = self.db.fixed_ip_get(context, id)
        return jsonutils.to_primitive(fixed)

    def get_fixed_ip_by_address(self, context, address):
        # NOTE(vish): This is no longer used but can't be removed until
        #             we major version the network_rpcapi to 2.0.
        fixed = self.db.fixed_ip_get_by_address(context, address)
        return jsonutils.to_primitive(fixed)

    def get_vif_by_mac_address(self, context, mac_address):
        """Returns the vifs record for the mac_address."""
        # NOTE(vish): This is no longer used but can't be removed until
        #             we major version the network_rpcapi to 2.0.
        vif = self.db.virtual_interface_get_by_address(context,
                                                        mac_address)
        if vif.get('network_id') is not None:
            network = self._get_network_by_id(context, vif['network_id'])
            vif['net_uuid'] = network['uuid']
        return vif

    @periodic_task.periodic_task(
        spacing=CONF.dns_update_periodic_interval)
    def _periodic_update_dns(self, context):
        """Update local DNS entries of all networks on this host."""
        networks = self.db.network_get_all_by_host(context, self.host)
        for network in networks:
            dev = self.driver.get_dev(network)
            self.driver.update_dns(context, dev, network)

    def update_dns(self, context, network_ids):
        """Called when fixed IP is allocated or deallocated."""
        if CONF.fake_network:
            return

        networks = [network for network in
                    self.db.network_get_all_by_host(context, self.host)
                    if network['multi_host'] and network['id'] in network_ids]
        for network in networks:
            dev = self.driver.get_dev(network)
            self.driver.update_dns(context, dev, network)

    def add_network_to_project(self, ctxt, project_id, network_uuid):
        raise NotImplementedError()


class FlatManager(NetworkManager):
    """Basic network where no vlans are used.

    FlatManager does not do any bridge or vlan creation.  The user is
    responsible for setting up whatever bridges are specified when creating
    networks through nova-manage. This bridge needs to be created on all
    compute hosts.

    The idea is to create a single network for the host with a command like:
    nova-manage network create 192.168.0.0/24 1 256. Creating multiple
    networks for for one manager is currently not supported, but could be
    added by modifying allocate_fixed_ip and get_network to get the network
    with new logic. Arbitrary lists of addresses in a single network can
    be accomplished with manual db editing.

    If flat_injected is True, the compute host will attempt to inject network
    config into the guest.  It attempts to modify /etc/network/interfaces and
    currently only works on debian based systems. To support a wider range of
    OSes, some other method may need to be devised to let the guest know which
    ip it should be using so that it can configure itself. Perhaps an attached
    disk or serial device with configuration info.

    Metadata forwarding must be handled by the gateway, and since nova does
    not do any setup in this mode, it must be done manually.  Requests to
    169.254.169.254 port 80 will need to be forwarded to the api server.

    """

    timeout_fixed_ips = False

    required_create_args = ['bridge']

    def _allocate_fixed_ips(self, context, instance_id, host, networks,
                            **kwargs):
        """Calls allocate_fixed_ip once for each network."""
        requested_networks = kwargs.get('requested_networks')
        for network in networks:
            address = None
            if requested_networks is not None:
                for address in (fixed_ip for (uuid, fixed_ip) in
                                requested_networks if network['uuid'] == uuid):
                    break

            self.allocate_fixed_ip(context, instance_id,
                                   network, address=address)

    def deallocate_fixed_ip(self, context, address, host=None, teardown=True):
        """Returns a fixed ip to the pool."""
        super(FlatManager, self).deallocate_fixed_ip(context, address, host,
                                                     teardown)
        self.db.fixed_ip_disassociate(context, address)

    def _setup_network_on_host(self, context, network):
        """Setup Network on this host."""
        # NOTE(tr3buchet): this does not need to happen on every ip
        # allocation, this functionality makes more sense in create_network
        # but we'd have to move the flat_injected flag to compute
        net = {}
        net['injected'] = CONF.flat_injected
        self.db.network_update(context, network['id'], net)

    def _teardown_network_on_host(self, context, network):
        """Tear down network on this host."""
        pass

    # NOTE(justinsb): The floating ip functions are stub-implemented.
    # We were throwing an exception, but this was messing up horizon.
    # Timing makes it difficult to implement floating ips here, in Essex.

    def get_floating_ip(self, context, id):
        """Returns a floating IP as a dict."""
        # NOTE(vish): This is no longer used but can't be removed until
        #             we major version the network_rpcapi to 2.0.
        return None

    def get_floating_pools(self, context):
        """Returns list of floating pools."""
        # NOTE(maurosr) This method should be removed in future, replaced by
        # get_floating_ip_pools. See bug #1091668
        return {}

    def get_floating_ip_pools(self, context):
        """Returns list of floating ip pools."""
        # NOTE(vish): This is no longer used but can't be removed until
        #             we major version the network_rpcapi to 2.0.
        return {}

    def get_floating_ip_by_address(self, context, address):
        """Returns a floating IP as a dict."""
        # NOTE(vish): This is no longer used but can't be removed until
        #             we major version the network_rpcapi to 2.0.
        return None

    def get_floating_ips_by_project(self, context):
        """Returns the floating IPs allocated to a project."""
        # NOTE(vish): This is no longer used but can't be removed until
        #             we major version the network_rpcapi to 2.0.
        return []

    def get_floating_ips_by_fixed_address(self, context, fixed_address):
        """Returns the floating IPs associated with a fixed_address."""
        # NOTE(vish): This is no longer used but can't be removed until
        #             we major version the network_rpcapi to 2.0.
        return []

    @network_api.wrap_check_policy
    def allocate_floating_ip(self, context, project_id, pool):
        """Gets a floating ip from the pool."""
        return None

    @network_api.wrap_check_policy
    def deallocate_floating_ip(self, context, address,
                               affect_auto_assigned):
        """Returns a floating ip to the pool."""
        return None

    @network_api.wrap_check_policy
    def associate_floating_ip(self, context, floating_address, fixed_address,
                              affect_auto_assigned=False):
        """Associates a floating ip with a fixed ip.

        Makes sure everything makes sense then calls _associate_floating_ip,
        rpc'ing to correct host if i'm not it.
        """
        return None

    @network_api.wrap_check_policy
    def disassociate_floating_ip(self, context, address,
                                 affect_auto_assigned=False):
        """Disassociates a floating ip from its fixed ip.

        Makes sure everything makes sense then calls _disassociate_floating_ip,
        rpc'ing to correct host if i'm not it.
        """
        return None

    def migrate_instance_start(self, context, instance_uuid,
                               floating_addresses,
                               rxtx_factor=None, project_id=None,
                               source=None, dest=None):
        pass

    def migrate_instance_finish(self, context, instance_uuid,
                                floating_addresses, host=None,
                                rxtx_factor=None, project_id=None,
                                source=None, dest=None):
        pass

    def update_dns(self, context, network_ids):
        """Called when fixed IP is allocated or deallocated."""
        pass


class FlatDHCPManager(RPCAllocateFixedIP, floating_ips.FloatingIP,
                      NetworkManager):
    """Flat networking with dhcp.

    FlatDHCPManager will start up one dhcp server to give out addresses.
    It never injects network settings into the guest. It also manages bridges.
    Otherwise it behaves like FlatManager.

    """

    SHOULD_CREATE_BRIDGE = True
    DHCP = True
    required_create_args = ['bridge']

    def init_host(self):
        """Do any initialization that needs to be run if this is a
        standalone service.
        """
        ctxt = context.get_admin_context()
        networks = self.db.network_get_all_by_host(ctxt, self.host)
        self.l3driver.initialize(fixed_range=False, networks=networks)
        super(FlatDHCPManager, self).init_host()
        self.init_host_floating_ips()

    def _setup_network_on_host(self, context, network):
        """Sets up network on this host."""
        network['dhcp_server'] = self._get_dhcp_ip(context, network)

        self.l3driver.initialize_network(network.get('cidr'))
        self.l3driver.initialize_gateway(network)

        if not CONF.fake_network:
            dev = self.driver.get_dev(network)
            # NOTE(dprince): dhcp DB queries require elevated context
            elevated = context.elevated()
            self.driver.update_dhcp(elevated, dev, network)
            if CONF.use_ipv6:
                self.driver.update_ra(context, dev, network)
                gateway = utils.get_my_linklocal(dev)
                self.db.network_update(context, network['id'],
                                       {'gateway_v6': gateway})

    def _teardown_network_on_host(self, context, network):
        if not CONF.fake_network:
            network['dhcp_server'] = self._get_dhcp_ip(context, network)
            dev = self.driver.get_dev(network)
            # NOTE(dprince): dhcp DB queries require elevated context
            elevated = context.elevated()
            self.driver.update_dhcp(elevated, dev, network)

    def _get_network_dict(self, network):
        """Returns the dict representing necessary and meta network fields."""

        # get generic network fields
        network_dict = super(FlatDHCPManager, self)._get_network_dict(network)

        # get flat dhcp specific fields
        if self.SHOULD_CREATE_BRIDGE:
            network_dict['should_create_bridge'] = self.SHOULD_CREATE_BRIDGE
        if network.get('bridge_interface'):
            network_dict['bridge_interface'] = network['bridge_interface']
        if network.get('multi_host'):
            network_dict['multi_host'] = network['multi_host']

        return network_dict


class VlanManager(RPCAllocateFixedIP, floating_ips.FloatingIP, NetworkManager):
    """Vlan network with dhcp.

    VlanManager is the most complicated.  It will create a host-managed
    vlan for each project.  Each project gets its own subnet.  The networks
    and associated subnets are created with nova-manage using a command like:
    nova-manage network create 10.0.0.0/8 3 16.  This will create 3 networks
    of 16 addresses from the beginning of the 10.0.0.0 range.

    A dhcp server is run for each subnet, so each project will have its own.
    For this mode to be useful, each project will need a vpn to access the
    instances in its subnet.

    """

    SHOULD_CREATE_BRIDGE = True
    SHOULD_CREATE_VLAN = True
    DHCP = True
    required_create_args = ['bridge_interface']

    def __init__(self, network_driver=None, *args, **kwargs):
        super(VlanManager, self).__init__(network_driver=network_driver,
                                          *args, **kwargs)
        # NOTE(cfb) VlanManager doesn't enforce quotas on fixed IP addresses
        #           because a project is assigned an entire network.
        self.quotas = quota.QuotaEngine(
                quota_driver_class='nova.quota.NoopQuotaDriver')

    def init_host(self):
        """Do any initialization that needs to be run if this is a
        standalone service.
        """

        ctxt = context.get_admin_context()
        networks = self.db.network_get_all_by_host(ctxt, self.host)
        self.l3driver.initialize(fixed_range=False, networks=networks)
        NetworkManager.init_host(self)
        self.init_host_floating_ips()

    def allocate_fixed_ip(self, context, instance_id, network, **kwargs):
        """Gets a fixed ip from the pool."""

        if kwargs.get('vpn', None):
            address = network['vpn_private_address']
            self.db.fixed_ip_associate(context,
                                       address,
                                       instance_id,
                                       network['id'],
                                       reserved=True)
        else:
            address = kwargs.get('address', None)
            if address:
                address = self.db.fixed_ip_associate(context, address,
                                                     instance_id,
                                                     network['id'])
            else:
                address = self.db.fixed_ip_associate_pool(context,
                                                          network['id'],
                                                          instance_id)

        vif = self.db.virtual_interface_get_by_instance_and_network(
            context, instance_id, network['id'])
        values = {'allocated': True,
                  'virtual_interface_id': vif['id']}
        self.db.fixed_ip_update(context, address, values)

        if not kwargs.get('vpn', None):
            self._do_trigger_security_group_members_refresh_for_instance(
                                                                   instance_id)

        # NOTE(vish) This db query could be removed if we pass az and name
        #            (or the whole instance object).
        instance = self.db.instance_get_by_uuid(context, instance_id)

        name = instance['display_name']
        if self._validate_instance_zone_for_dns_domain(context, instance):
            name = instance['display_name']
            self.instance_dns_manager.create_entry(name, address,
                                                   "A",
                                                   self.instance_dns_domain)
            self.instance_dns_manager.create_entry(instance_id, address,
                                                   "A",
                                                   self.instance_dns_domain)

        self._setup_network_on_host(context, network)
        return address

    def add_network_to_project(self, context, project_id, network_uuid=None):
        """Force adds another network to a project."""
        if network_uuid is not None:
            network_id = self.get_network(context, network_uuid)['id']
        else:
            network_id = None
        self.db.network_associate(context, project_id, network_id, force=True)

    def associate(self, context, network_uuid, associations):
        """Associate or disassociate host or project to network."""
        # NOTE(vish): This is no longer used but can't be removed until
        #             we major version the network_rpcapi to 2.0.
        network_id = self.get_network(context, network_uuid)['id']
        if 'host' in associations:
            host = associations['host']
            if host is None:
                self.db.network_disassociate(context, network_id,
                                             disassociate_host=True,
                                             disassociate_project=False)
            else:
                self.db.network_set_host(context, network_id, host)
        if 'project' in associations:
            project = associations['project']
            if project is None:
                self.db.network_disassociate(context, network_id,
                                             disassociate_host=False,
                                             disassociate_project=True)
            else:
                self.db.network_associate(context, project, network_id, True)

    def _get_network_by_id(self, context, network_id):
        # NOTE(vish): Don't allow access to networks with project_id=None as
        #             these are networks that haven't been allocated to a
        #             project yet.
        return self.db.network_get(context, network_id, project_only=True)

    def _get_networks_by_uuids(self, context, network_uuids):
        # NOTE(vish): Don't allow access to networks with project_id=None as
        #             these are networks that haven't been allocated to a
        #             project yet.
        networks = self.db.network_get_all_by_uuids(context, network_uuids,
                                                    project_only=True)
        networks.sort(key=lambda x: network_uuids.index(x['uuid']))
        return networks

    def _get_networks_for_instance(self, context, instance_id, project_id,
                                   requested_networks=None):
        """Determine which networks an instance should connect to."""
        # get networks associated with project
        if requested_networks is not None and len(requested_networks) != 0:
            network_uuids = [uuid for (uuid, fixed_ip) in requested_networks]
            networks = self._get_networks_by_uuids(context, network_uuids)
        else:
            networks = self.db.project_get_networks(context, project_id)
        return networks

    def create_networks(self, context, **kwargs):
        """Create networks based on parameters."""
        self._convert_int_args(kwargs)

        kwargs["vlan_start"] = kwargs.get("vlan_start") or CONF.vlan_start
        kwargs["num_networks"] = (kwargs.get("num_networks") or
                                  CONF.num_networks)
        kwargs["network_size"] = (kwargs.get("network_size") or
                                  CONF.network_size)
        # Check that num_networks + vlan_start is not > 4094, fixes lp708025
        if kwargs["num_networks"] + kwargs["vlan_start"] > 4094:
            raise ValueError(_('The sum between the number of networks and'
                               ' the vlan start cannot be greater'
                               ' than 4094'))

        # check that num networks and network size fits in fixed_net
        fixed_net = netaddr.IPNetwork(kwargs['cidr'])
        if fixed_net.size < kwargs['num_networks'] * kwargs['network_size']:
            raise ValueError(_('The network range is not '
                  'big enough to fit %(num_networks)s networks. Network '
                  'size is %(network_size)s') % kwargs)

        kwargs['bridge_interface'] = (kwargs.get('bridge_interface') or
                                      CONF.vlan_interface)
        return NetworkManager.create_networks(
            self, context, vpn=True, **kwargs)

    @utils.synchronized('setup_network', external=True)
    def _setup_network_on_host(self, context, network):
        """Sets up network on this host."""
        if not network['vpn_public_address']:
            net = {}
            address = CONF.vpn_ip
            net['vpn_public_address'] = address
            network = self.db.network_update(context, network['id'], net)
        else:
            address = network['vpn_public_address']
        network['dhcp_server'] = self._get_dhcp_ip(context, network)

        self.l3driver.initialize_network(network.get('cidr'))
        self.l3driver.initialize_gateway(network)

        # NOTE(vish): only ensure this forward if the address hasn't been set
        #             manually.
        if address == CONF.vpn_ip and hasattr(self.driver,
                                               "ensure_vpn_forward"):
            self.l3driver.add_vpn(CONF.vpn_ip,
                    network['vpn_public_port'],
                    network['vpn_private_address'])
        if not CONF.fake_network:
            dev = self.driver.get_dev(network)
            # NOTE(dprince): dhcp DB queries require elevated context
            elevated = context.elevated()
            self.driver.update_dhcp(elevated, dev, network)
            if CONF.use_ipv6:
                self.driver.update_ra(context, dev, network)
                gateway = utils.get_my_linklocal(dev)
                self.db.network_update(context, network['id'],
                                       {'gateway_v6': gateway})

    @utils.synchronized('setup_network', external=True)
    def _teardown_network_on_host(self, context, network):
        if not CONF.fake_network:
            network['dhcp_server'] = self._get_dhcp_ip(context, network)
            dev = self.driver.get_dev(network)
            # NOTE(dprince): dhcp DB queries require elevated context
            elevated = context.elevated()
            self.driver.update_dhcp(elevated, dev, network)

            # NOTE(ethuleau): For multi hosted networks, if the network is no
            # more used on this host and if VPN forwarding rule aren't handed
            # by the host, we delete the network gateway.
            vpn_address = network['vpn_public_address']
            if (CONF.teardown_unused_network_gateway and
                network['multi_host'] and vpn_address != CONF.vpn_ip and
                not self.db.network_in_use_on_host(context, network['id'],
                                                   self.host)):
                LOG.debug("Remove unused gateway %s", network['bridge'])
                self.driver.kill_dhcp(dev)
                self.l3driver.remove_gateway(network)
                if not CONF.share_dhcp_address:
                    values = {'allocated': False,
                              'host': None}
                    self.db.fixed_ip_update(context, network['dhcp_server'],
                                            values)
            else:
                self.driver.update_dhcp(elevated, dev, network)

    def _get_network_dict(self, network):
        """Returns the dict representing necessary and meta network fields."""

        # get generic network fields
        network_dict = super(VlanManager, self)._get_network_dict(network)

        # get vlan specific network fields
        if self.SHOULD_CREATE_BRIDGE:
            network_dict['should_create_bridge'] = self.SHOULD_CREATE_BRIDGE
        if self.SHOULD_CREATE_VLAN:
            network_dict['should_create_vlan'] = self.SHOULD_CREATE_VLAN
        for k in ['vlan', 'bridge_interface', 'multi_host']:
            if network.get(k):
                network_dict[k] = network[k]

        return network_dict

    @property
    def _bottom_reserved_ips(self):
        """Number of reserved ips at the bottom of the range."""
        return super(VlanManager, self)._bottom_reserved_ips + 1  # vpn server

    @property
    def _top_reserved_ips(self):
        """Number of reserved ips at the top of the range."""
        parent_reserved = super(VlanManager, self)._top_reserved_ips
        return parent_reserved + CONF.cnt_vpn_clients
