from dataclasses import dataclass
from itertools import islice

import networkx as nx


@dataclass(frozen=True)
class CandidatePath:
    demand_id: str
    index: int
    switches: tuple[str, ...]
    links: tuple[tuple[str, str], ...]
    hops: int
    delay_ms: float


def switch_graph(topology: dict) -> nx.Graph:
    graph = nx.Graph()
    graph.add_nodes_from(topology["switches"])
    for link in topology["links"]:
        delay = float(link["delay_ms"])
        graph.add_edge(
            link["a"],
            link["b"],
            delay_ms=delay,
            bw_mbps=float(link["bw_mbps"]),
            weight=1.0 + delay * 1e-6,
        )
    return graph


def compute_candidates(topology: dict, k: int) -> list[list[CandidatePath]]:
    graph = switch_graph(topology)
    host_switch = {host["name"]: host["switch"] for host in topology["hosts"]}
    result: list[list[CandidatePath]] = []
    for demand in topology["demands"]:
        source = host_switch[demand["src"]]
        destination = host_switch[demand["dst"]]
        paths = list(islice(nx.shortest_simple_paths(graph, source, destination, weight="weight"), k))
        if len(paths) < k:
            raise ValueError(f"demand {demand['id']} has {len(paths)} paths; need {k}")
        demand_paths: list[CandidatePath] = []
        for index, path in enumerate(paths):
            links = tuple(zip(path, path[1:]))
            bottleneck = min(graph[a][b]["bw_mbps"] for a, b in links)
            if bottleneck < float(demand["rate_mbps"]):
                raise ValueError(f"candidate path cannot carry demand {demand['id']}: {path}")
            demand_paths.append(
                CandidatePath(
                    demand_id=demand["id"],
                    index=index,
                    switches=tuple(path),
                    links=links,
                    hops=len(links),
                    delay_ms=sum(graph[a][b]["delay_ms"] for a, b in links),
                )
            )
        result.append(demand_paths)
    return result


def action_space_size(demand_count: int, k: int) -> int:
    return demand_count * k + 1


def decode_action(action: int, demand_count: int, k: int) -> tuple[int, int] | None:
    if action == 0:
        return None
    offset = action - 1
    demand_index, path_index = divmod(offset, k)
    if demand_index >= demand_count:
        raise ValueError(f"action {action} is outside the configured action space")
    return demand_index, path_index
