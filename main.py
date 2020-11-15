import argparse
import collections
import itertools
import logging
import math
import os
import re
import time
import subprocess

import pykube
from jinja2 import Template

FACTORS = {
    'm': 1 / 1000,
    'K': 1000,
    'M': 1000**2,
    'G': 1000**3,
    'T': 1000**4,
    'P': 1000**5,
    'E': 1000**6,
    'Ki': 1024,
    'Mi': 1024**2,
    'Gi': 1024**3,
    'Ti': 1024**4,
    'Pi': 1024**5,
    'Ei': 1024**6
}

RESOURCE_PATTERN = re.compile('^(\d*)(\D*)$')

def parse_resource(v: str):
    '''Parse Kubernetes resource string'''
    match = RESOURCE_PATTERN.match(v)
    factor = FACTORS.get(match.group(2), 1)
    return int(match.group(1)) * factor

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
    # TODO: Check for master label and ingore it. 
    # Currently incluse_master_node functionality is WIP

    nodes = {}
    for node in pykube.Node.objects(api):
        allocatable = {}
        # Use the Node Allocatable Resources to account for any kube/system reservations:
        # https://github.com/kubernetes/community/blob/master/contributors/design-proposals/node-allocatable.md
        for key, val in node.obj['status']['allocatable'].items():
            allocatable[key] = parse_resource(val)

        instance_id = ""

        obj = {'name': node.name,
               'instance_id': instance_id,
               'allocatable': allocatable,
               'ready': is_node_ready(node),
               'unschedulable': node.obj['spec'].get('unschedulable', False),
               'master': node.labels.get('master', 'false') == 'true',
               'address': node.obj["status"]["addresses"][0]["address"]
            }
        if include_master_nodes or not obj['master']:
            nodes[node.name] = obj
    return nodes

def get_pods(api):
    pods = pykube.Pod.objects(api, namespace=pykube.all)
    

if __name__ == "__main__":
    api = get_kube_api()

    HA_PROXY_CONFIG_FILE = "/etc/haproxy/haproxy.cfg"

    last_nodes = []

    while True:
        all_nodes = get_nodes(api)
        print(all_nodes)
        if(set(all_nodes) != set(last_nodes)):
            with open('haproxy.cfg.jinja2') as file_:
                template = Template(file_.read())
            output = template.render(nodes = [all_nodes[x]['address'] for x in all_nodes])

            with open(HA_PROXY_CONFIG_FILE, "w") as f:
                f.write(output)
                print("written to haproxy")
            
            # subprocess.call("sudo service haproxy reload", shell=True)

        time.sleep(120)
        last_nodes = all_nodes
