import pytest
import time
import traceback
from libs.rhevm import RhevmAction
from libs.network import NetworkAction
from fabric.api import run, env, settings
from libs.util import *
from conf import *
from constants import *

# Get rhvm info
rhvm_fqdn = RHVM_FQDN
rhvm_pass = RHVM_INFO[RHVM_FQDN]['password']

# Get host to be used
host_ip = MACHINE_INFO[TEST_HOST]['ip']
host_pass = MACHINE_INFO[TEST_HOST]['password']

# Get the bv info
bv_flag = MACHINE_INFO[TEST_HOST].get('network', None).get('bv')
if not bv_flag:
    raise RuntimeError("%s not support for test_bv_anaconda" % TEST_HOST)

bv_info = MACHINE_INFO[TEST_HOST]["network"]["bv"]
bond_name = MACHINE_INFO[TEST_HOST]["network"]["bv"]["bond_name"]
vlan_id = MACHINE_INFO[TEST_HOST]["network"]["bv"]["vlan_id"]
bv = bond_name + '.' + vlan_id

dc_name = "vdsm_bva_dc"
cluster_name = "vdsm_bva_cluster"
host_name = "vdsm_bva_host"

env.host_string = 'root@' + host_ip
env.password = host_pass


@pytest.fixture(scope="session")
def rhvm(request):
    mrhvm = RhevmAction(rhvm_fqdn)

    mrhvm.create_datacenter(dc_name)
    print "Creating datacenter..."
    time.sleep(10)

    print "Creating cluster..."
    cpu_type = get_cpu_type(host_ip, host_pass)
    mrhvm.create_cluster(dc_name, cluster_name, cpu_type)

    def fin():
        if mrhvm.list_datacenter(dc_name):
            print "Force removing datacenter..."
            mrhvm.remove_datacenter(dc_name, force=True)
        if mrhvm.list_host(host_name):
            print "Removing host..."
            mrhvm.remove_host(host_name)
        print "Removing cluster..."
        mrhvm.remove_cluster(cluster_name)

    request.addfinalizer(fin)
    return mrhvm


def test_bvi(rhvm):
    """
    Add rhvh to engine over static bond+vlan after anaconda installation
    """
    # Setup bv
    nk = NetworkAction()
    nk.host_ip = host_ip
    nk.host_pass = host_pass
    nk.setup_vlan(bv_info)

    # Check bv is configured
    with settings(warn_ony=True):
        cmd = "ip a s|grep %s|grep inet" % bv
        res = run(cmd)
    if res.failed:
        assert 0, "%s is not configured or name incorrect" % bv
    bv_ip = res.split()[1].split('/')[0]

    # Update the default network with a vlan tag
    print "Updating the network of datacenter with vlan tag..."
    try:
        rhvm.update_dc_network(
            dc_name, "ovirtmgmt", key="vlan", value=vlan_id)
    except Exception as e:
        print e
        print traceback.print_exc()
        assert 0, "Failed to update the network"
    time.sleep(10)

    # Add new host to above cluster
    print "Adding new host..."
    try:
        rhvm.create_new_host(
            bv_ip, host_name, host_pass, cluster_name=cluster_name)
    except Exception as e:
        print e
        print traceback.print_exc()
        assert 0, "Failed to add new host to cluster"
    time.sleep(30)

    # Wait host is up
    i = 0
    while True:
        if i > 60:
            assert 0, "Failed to add host %s to %s" % (host_name, dc_name)
        host_status = rhvm.list_host(host_name)['status']
        print "HOST: %s" % host_status
        if host_status == 'up':
            break
        elif host_status == 'install_failed':
            assert 0, "Failed to add host %s to %s" % (host_name, dc_name)
        time.sleep(10)
        i += 1


def test_unset(rhvm):
    # Remove host
    if rhvm.list_host(host_name):
        print "Removing the host..."
        try:
            rhvm.remove_host(host_name)
        except Exception as e:
            print e
            print traceback.print_exc()
        time.sleep(30)
