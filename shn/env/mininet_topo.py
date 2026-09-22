from functools import partial

from mininet.link import TCLink
from mininet.net import Mininet
from mininet.node import OVSSwitch, RemoteController
from mininet.topo import Topo


class MeshTopo(Topo):
    def build(self, topology: dict) -> None:
        for switch in topology["switches"]:
            self.addSwitch(switch)
        for host in topology["hosts"]:
            self.addHost(host["name"])
        for link in topology["links"]:
            self.addLink(
                link["a"],
                link["b"],
                cls=TCLink,
                bw=float(link["bw_mbps"]),
                delay=f"{link['delay_ms']}ms",
            )
        for host in topology["hosts"]:
            self.addLink(host["name"], host["switch"])


def build_network(topology: dict) -> Mininet:
    network = Mininet(
        topo=MeshTopo(topology),
        controller=partial(RemoteController, ip="127.0.0.1", port=6653),
        switch=partial(OVSSwitch, protocols="OpenFlow13"),
        link=TCLink,
        autoSetMacs=True,
        autoStaticArp=True,
    )
    network.start()
    return network
