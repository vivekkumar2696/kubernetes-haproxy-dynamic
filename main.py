import argparse
import os
import time

import pykube
from jinja2 import Template


def get_kube_api():
    try:
        config = pykube.KubeConfig.from_service_account()
    except FileNotFoundError:
        # local testing
        config = pykube.KubeConfig.from_file(os.path.expanduser('~/.kube/config'))
    api = pykube.HTTPClient(config)
    return api

def is_node_ready(node):
    for condition in node.obj['status'].get('conditions', []):
        if condition['type'] == 'Ready' and condition['status'] == 'True':
            return True
    return False

def get_nodes(api, include_master_nodes: bool=False):
    nodes = {}
    for node in pykube.Node.objects(api):
        allocatable = {}
        # Use the Node Allocatable Resources to account for any kube/system reservations:
        # https://github.com/kubernetes/community/blob/master/contributors/design-proposals/node-allocatable.md
        for key, val in node.obj['status']['allocatable'].items():
            allocatable[key] = parse_resource(val)

        instance_id = ""

        if int(node.obj['status']['nodeInfo']['kubeletVersion'].split(".")[1]) < 11:
            instance_id = node.obj['spec']['externalID']
        else:
            instance_id = node.obj['spec']['providerID'].split("/")[4]

        obj = {'name': node.name,
               'instance_id': instance_id,
               'allocatable': allocatable,
               'ready': is_node_ready(node),
               'unschedulable': node.obj['spec'].get('unschedulable', False),
               'master': node.labels.get('master', 'false') == 'true'}
        if include_master_nodes or not obj['master']:
            nodes[node.name] = obj
    return nodes

def get_pods(api):
    pods = pykube.Pod.objects(api, namespace=pykube.all)
    

if __name__ == "__main__":
    api = get_kube_api()
    all_nodes = get_nodes(api, include_master_nodes)
    print(all_nodes)

    HA_PROXY_CONFIG_FILE = "/etc/haproxy/haproxy.cfg"

    last_nodes = []

    while True:
        time.sleep(120)
        all_nodes = get_nodes(api, include_master_nodes)
        if(set(all_nodes) != set(last_nodes)):
            with open('haproxy.cfg.jinja2') as file_:
                template = Template(file_.read())
            template.render(nodes = all_nodes)

            with open("haproxy.cfg", "w") as f:
                f.write(template)

        last_nodes = all_nodes
