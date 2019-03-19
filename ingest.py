#!/usr/bin/env python3
import json
import yaml
import requests
import logging
import argparse
import urllib3
import re
import os

urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

LLDP_NODES = "/analytics/network/v1/topology/nodes"
LLDP_EDGES = "/analytics/network/v1/topology/edges"
CONF_DIR = "./config"
TOPO_FILE = "cvp_topology.yml"

def parse_args():
    parser = argparse.ArgumentParser(description="Tool to ingest topology information from CVP")
    parser.add_argument(
        '-d', '--debug',
        help='Enable Debug',
        action='store_true'
    )
    parser.add_argument(
        '-i', '--ignore',
        help='Ignore 3rd party devices',
        action='store_true'
    )
    parser.add_argument(
        '-f', '--filter',
        help='Match specified string in hostnames',
        type=str
    )
    parser.add_argument(
        '-v', '--veos',
        help='Produce artefacts for vEOS',
        action='store_true'
    )
    parser.add_argument(
        "cvp",
        help='CVP address',
        type=str
    )
    parser.add_argument(
        "user",
        help='CVP username',
        type=str
    )
    parser.add_argument(
        "pwd",
        help='CVP password',
        type=str
    )
    args = parser.parse_args()
    return args

class CVP(object):

    def __init__(self, ip, user, pwd):
        self.ip = ip
        self.user = user
        self.pwd = pwd
        self.cookie = None
        self.headers = {'content-type': "application/json"}
        self.baseUrl = f"https://{self.ip}/api/v1/rest"
        if not self._auth():
            raise Exception(f"Failed to authenticate with CVP {self.ip}")
        self.headers['Cookie'] = self.cookie
    
    def _auth(self):
        url = f"https://{self.ip}/cvpservice/login/authenticate.do"
        data = {
            'userId': self.user,
            'password': self.pwd
        }
        
        response = requests.request("POST", url, data=json.dumps(data), headers=self.headers, verify=False)
        if response.status_code == 200:
            data = response.json()
            self.cookie = f"session_id={data.get('sessionId')}"
            logging.debug(f"Successfully authenticated on {self.ip}")
            return True
        else:
            False


    def get(self, url):
        full_url = self.baseUrl + url
        logging.debug(f"HTTP GET for {full_url}")
        response = requests.request("GET", full_url, headers = self.headers, verify = False)
        if response.status_code != 200:
            logging.info(f"Failed to GET data from CVP: {response.reason}")
            logging.debug(f"{print(response.text)}")
            return {}
        else:
            return response.json()


class Device(object):

    def __init__(self, hostname, serial, model, mlag=dict()):
        self.hostname = hostname.split('.')[0]
        self.serial = serial
        self.model = model
        self.config = ''
        self.mlag = mlag
        self.interfaces = dict()
        self.real_to_lab = dict()

    def __str__(self):
        return f"""
        Hostname: {self.hostname}
        Serial: {self.serial}
        Model: {self.model}
        """

    def init_lab_intfs(self):
        idx = 0
        logging.info(f"Converting interfaces for {self.hostname}")
        for intf in sort_numerically(self.interfaces.keys()):
            if not self.interfaces[intf].is_ignored:
                logging.debug(f"Converting {intf} to Ethernet{idx+1}")
                self.real_to_lab[intf] = f"Ethernet{idx+1}"
                idx += 1

    def key(self):
        return self.serial

    def get_config(self, cvp, veos):
        logging.info(f"Getting configuration for {self.hostname}")
        url = f"/{self.serial}/Config/running/lines"
        response = cvp.get(url)
        if response and response.get("notifications"):
            parsed_config = Config(response["notifications"], self.real_to_lab)
            self.config = parsed_config.config
            logging.debug(f"{self.hostname} config:\n {self.config}")
        else:
            self.config = ''
        return self.config

    def connect(self, intf, link):
        if not intf in self.interfaces:
            self.interfaces[intf] = link
        else:
            logging.info(f"WARNING! duplicate interface definition. \n\tExisting: \t{self.interfaces[intf]} \n\tNew (ignoring): {link}")
            link.ignore()

class Config(object):

    def __init__(self, config_lines, intf_mapping, mgmt_intf = ''):
        """
        self.lines = {
            line_uuid: {
                prev: prev_uuid,
                next: next_uuid,
                text: str
            }
        }
        """
        self.lines_batches = [x.get('updates') for x in config_lines]
        self.raw_lines = {k:v for d in self.lines_batches for k,v in d.items()}
        self.lines = {k:v.get('value') for k,v in self.raw_lines.items()}
        self.mgmt_intf = mgmt_intf
        self.intf_mapping = intf_mapping
        self.config = self._build()

    def _build(self):
        config = ''
        first_lines = [v for k,v in self.lines.items() if not v.get('previous')]
        if len(first_lines) != 1:
            raise Exception(f"Unexpected number of first lines {len(first_lines)}")
        current_line = first_lines[0]
        while current_line.get('next'):
            if self.mgmt_intf: # In case mgmt interface is defined, we replace it with eth0
                if self.mgmt_intf in current_line['text']:
                    current_line['text'] = current_line['text'].replace(self.mgmt_intf, "Ethernet0")
            if 'ethernet' in current_line['text'].lower(): # Special treatment for interface names
                if self.intf_mapping: # If we need to change interface names
                    for old, new in self.intf_mapping.items():
                        if old in current_line['text']: # If there's a match
                            #match = f"{old}([\D])|{old}$" # Prevent eth1 from matching eth12
                            current_line['text'] = re.sub(r"%s([\D])|%s$" % (old, old), r"%s\1" % new, current_line['text'])
            if 'password' in current_line['text'].lower(): # Removing all passwords
                current_line['text'] = ""
            config += f"\n{current_line['text']}"
            current_lines = [v for k,v in self.lines.items() if k == current_line['next']]
            if len(current_lines) != 1:
                raise Exception(f"Unexpected number of next lines {len(current_lines)}")
            current_line = current_lines[0]
        return config



class Link(object):

    def __init__(self, device_a, intf_a, device_b, intf_b):
        self.device_a = device_a
        self.intf_a = intf_a
        self.device_b = device_b
        self.intf_b = intf_b
        self.is_ignored = False
        logging.debug(f"Created link {self}")
    
    def ignore(self):
        logging.debug(f"Ignoring link between {self.device_a.hostname} and {self.device_b.hostname}")
        self.is_ignored = True
    
    def __str__(self):
        return f"{self.device_a.hostname}:{self.intf_a} <-> {self.device_b.hostname}:{self.intf_b}"

def sort_numerically(l):
    convert = lambda text: int(text) if text.isdigit() else text
    alphanum_key = lambda key: [convert(c) for c in re.split('([0-9]+)', key)]
    return sorted(l, key = alphanum_key)

def write_file(fn, text):
    if text:
        with open(fn, 'w') as f:
            f.write(text)

def is_macaddress(address):
    return re.match("[0-9a-f]{2}([-:]?)[0-9a-f]{2}(\\1[0-9a-f]{2}){4}$", address.lower())

def archive_topo(confdir, topofile):
    logging.info("Archiving {} and {}".format(confdir, topofile))
    outfile = os.path.splitext(topofile)[0] + '.tar.gz'
    confdir = os.path.basename(confdir)
    import tarfile
    with tarfile.open(outfile, 'w:gz') as tar:
        tar.add(confdir)
        tar.add(topofile)
    return outfile

def main():
    args = parse_args()
    debug = args.debug
    cvp_ip = args.cvp
    cvp_user = args.user
    cvp_pwd = args.pwd
    ignore = args.ignore
    veos = args.veos
    pattern = args.filter
    
    
    if debug:
        log_level = logging.DEBUG
    else:
        log_level = logging.INFO
    logging.basicConfig(level=log_level, format='%(name)s ~> %(message)s')

    cvp = CVP(cvp_ip, cvp_user, cvp_pwd)

    nodes = cvp.get(LLDP_NODES)["notifications"]
    write_file("nodes.json",json.dumps(nodes))

    devices = dict()
    for node in nodes:
        for _,v in node["updates"].items():
            serial = v.get('key')
            index = len(devices)
            hostname = v.get('value', {}).get('hostName')
            if not hostname: # case for 3rd party devices
                hostname = f"host-{index}"
            model = v.get('value', {}).get('modelName')
            mlag = v.get('value', {}).get('mlag')
            devices[serial] = Device(hostname, serial, model, mlag)


    edges = cvp.get(LLDP_EDGES)["notifications"]
    write_file("edges.json",json.dumps(edges))

    links = list()
    for edge in edges:
        for _,v in edge["updates"].items(): 
            from_device = v["key"]["from"] 
            to_device = v["key"]["to"] 
            for k,v2 in v["value"].items(): 
                from_intf = k
                for k,v3 in v2.items(): 
                    to_intf = v3['_key']['neighborPort']
                    if is_macaddress(from_intf): # Corner case for 3rd party LLDP device
                        from_intf = "eth0"
                    elif is_macaddress(to_intf):
                        to_intf =  "eth0"
                    device_a = devices.get(from_device, Device(f"host-{len(devices)}", from_device, "Unknown"))
                    device_b = devices.get(to_device, Device(f"host-{len(devices)}", to_device, "Unknown"))
                    link = Link(device_a, from_intf, device_b, to_intf)
                    links.append(link)  
                    device_a.connect(from_intf, link)
                    device_b.connect(to_intf, link)
                    devices[from_device] = device_a
                    devices[to_device] = device_b
    logging.debug(f"New number of devices {len(devices)}")
    
    if ignore:
        devices = {k:v for k,v in devices.items() if not 'host' in v.hostname}
        for link in links:
            if 'host' in link.device_a.hostname or 'host' in link.device_b.hostname:
                link.ignore()
    if pattern:
        devices = {k:v for k,v in devices.items() if pattern in v.hostname}
        for link in links:
            if not (pattern in link.device_a.hostname and pattern in link.device_b.hostname):
                link.ignore()
    if veos:
        [v.init_lab_intfs() for _,v in devices.items()]

    endpoints = list()
    for link in links:
        if link.is_ignored:
            continue
        from_hostname = link.device_a.hostname
        to_hostname = link.device_b.hostname
        from_intf = link.intf_a
        to_intf = link.intf_b
        logging.debug(f"EP => {from_hostname}:{from_intf}, {to_hostname}:{to_intf}")
        if veos: # Replacing real intf with lab
            from_intf = link.device_a.real_to_lab[from_intf]
            to_intf = link.device_b.real_to_lab[to_intf]
            logging.debug(f"EP converted => {from_hostname}:{from_intf}, {to_hostname}:{to_intf}")
        endpoints.append([f"{from_hostname}:{from_intf}", f"{to_hostname}:{to_intf}"])
    
    topology = {
        'etcd_port': 32379,
        'publish_base': {22:30001},
        'conf_dir': "./config",
        'links': [ {"endpoints": x } for x in endpoints ]
    }
    write_file(TOPO_FILE, yaml.dump(topology))

    
    [write_file(os.path.join(CONF_DIR, v.hostname), v.get_config(cvp, veos)) for _,v in devices.items()]
    archive_topo(CONF_DIR, TOPO_FILE)
  


if __name__ == '__main__':
    main()
