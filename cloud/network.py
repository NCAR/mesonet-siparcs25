import numpy as np
import networkx as nx
import logging
import json

logger = logging.getLogger(__name__)

class Station:
    def __init__(self, station_id, seen_by):
        self.id = station_id
        self.seen_by = seen_by  # Dict[edge_id: rssi]
        logger.debug(f"Station {station_id} created with seen_by: {seen_by}")

class EdgeServer:
    def __init__(self, edge_id):
        self.id = edge_id
        self.assigned_stations = set()
        logger.debug(f"EdgeServer {edge_id} created")

class DynamicAssignmentNetwork:
    def __init__(self, mqtt_client, config, hysteresis=0.1, rssi_min=-120, rssi_max=-30):
        self.mqtt_client = mqtt_client
        self.config = config
        self.stations = {}  # station_id -> Station
        self.edges = {}     # edge_id -> EdgeServer
        self.station_to_edge = {}  # station_id -> edge_id
        self.hysteresis = hysteresis
        self.rssi_min = rssi_min
        self.rssi_max = rssi_max
        logger.info(f"DynamicAssignmentNetwork initialized with hysteresis={hysteresis}, rssi_min={rssi_min}, rssi_max={rssi_max}")

    def score(self, station, edge_id):
        if not self.stations:
            logger.warning("No stations available for scoring")
            return 0
        rssi_score = (station.seen_by[edge_id] - self.rssi_min) / (self.rssi_max - self.rssi_min)
        load_score = 1 - (len(self.edges[edge_id].assigned_stations) / len(self.stations))
        score = 0.7 * rssi_score + 0.3 * load_score
        current_edge = self.station_to_edge.get(station.id)
        if current_edge == edge_id:
            score += self.hysteresis
        logger.debug(f"Score for station {station.id} to edge {edge_id}: rssi_score={rssi_score:.2f}, load_score={load_score:.2f}, total={score:.2f}")
        return score

    def assign_station(self, station):
        reachable_edges = station.seen_by
        if not reachable_edges:
            self.station_to_edge[station.id] = None
            logger.warning(f"No reachable edges for station {station.id}")
            return None
        best_edge = max(reachable_edges, key=lambda e: self.score(station, e))
        self.station_to_edge[station.id] = best_edge
        self.edges.setdefault(best_edge, EdgeServer(best_edge)).assigned_stations.add(station.id)
        logger.info(f"Assigned station {station.id} to edge {best_edge}")
        # Publish assignment
        if self.mqtt_client:
            try:
                self.mqtt_client.publish_assignment(best_edge, station.id, "assigned")
                logger.debug(f"Published assignment: station {station.id} to edge {best_edge}")
            except Exception as e:
                logger.error(f"Failed to publish assignment for station {station.id} to edge {best_edge}: {e}")
        return best_edge

    def rebalance_all(self):
        station_ids = list(self.stations.keys())
        edge_ids = list(self.edges.keys())
        logger.info(f"Rebalancing: {len(station_ids)} stations, {len(edge_ids)} edges")

        if not station_ids or not edge_ids:
            logger.warning("No stations or edges to rebalance")
            for sid in station_ids:
                if self.station_to_edge.get(sid):
                    old_edge = self.station_to_edge[sid]
                    self.station_to_edge[sid] = None
                    if self.mqtt_client and old_edge in self.edges:
                        try:
                            self.mqtt_client.publish_assignment(old_edge, sid, "unassigned")
                            logger.debug(f"Published unassignment: station {sid} from edge {old_edge}")
                        except Exception as e:
                            logger.error(f"Failed to publish unassignment for station {sid} from edge {old_edge}: {e}")
            for es in self.edges.values():
                es.assigned_stations.clear()
            return

        valid_stations = [sid for sid in station_ids if self.stations[sid].seen_by]
        if not valid_stations:
            logger.warning("No valid stations with seen_by data")
            self.station_to_edge.clear()
            return

        # Store old assignments for comparison
        old_assignments = dict(self.station_to_edge)
        logger.debug(f"Old assignments: {json.dumps(old_assignments, indent=2)}")

        G = nx.DiGraph()
        source = 'source'
        sink = 'sink'
        G.add_node(source, demand=-len(valid_stations))
        G.add_node(sink, demand=len(valid_stations))
        for sid in valid_stations:
            G.add_node(f'station_{sid}')
        for eid in edge_ids:
            G.add_node(f'edge_{eid}')

        for sid in valid_stations:
            G.add_edge(source, f'station_{sid}', capacity=1, weight=0)
            station = self.stations[sid]
            for eid in edge_ids:
                if eid in station.seen_by:
                    score = self.score(station, eid)
                    G.add_edge(f'station_{sid}', f'edge_{eid}', capacity=1, weight=-score)

        for eid in edge_ids:
            G.add_edge(f'edge_{eid}', sink, capacity=len(valid_stations), weight=0)

        try:
            flow_dict = nx.min_cost_flow(G)
            logger.debug(f"Min-cost flow computed: {json.dumps(flow_dict, indent=2)}")
            for es in self.edges.values():
                es.assigned_stations.clear()
            self.station_to_edge.clear()
            for sid in station_ids:
                self.station_to_edge[sid] = None

            for sid in valid_stations:
                station_node = f'station_{sid}'
                for edge_node, flow in flow_dict[station_node].items():
                    if flow > 0 and edge_node.startswith('edge_'):
                        eid = edge_node[5:]
                        self.station_to_edge[sid] = eid
                        self.edges[eid].assigned_stations.add(sid)
                        logger.info(f"Assigned station {sid} to edge {eid}")

            # Publish assignment changes
            if self.mqtt_client:
                for sid in valid_stations:
                    old_edge = old_assignments.get(sid)
                    new_edge = self.station_to_edge.get(sid)
                    if old_edge != new_edge:
                        if old_edge and old_edge in self.edges:
                            try:
                                self.mqtt_client.publish_assignment(old_edge, sid, "unassigned")
                                logger.debug(f"Published unassignment: station {sid} from edge {old_edge}")
                            except Exception as e:
                                logger.error(f"Failed to publish unassignment for station {sid} from edge {old_edge}: {e}")
                        if new_edge:
                            try:
                                self.mqtt_client.publish_assignment(new_edge, sid, "assigned")
                                logger.debug(f"Published assignment: station {sid} to edge {new_edge}")
                            except Exception as e:
                                logger.error(f"Failed to publish assignment for station {sid} to edge {new_edge}: {e}")

        except nx.NetworkXUnfeasible:
            logger.error("No feasible flow found; falling back to greedy assignment")
            for es in self.edges.values():
                es.assigned_stations.clear()
            for sid in valid_stations:
                self.assign_station(self.stations[sid])

    def on_station_join(self, station_id, seen_by):
        valid_seen_by = {eid: rssi for eid, rssi in seen_by.items() if eid in self.edges}
        if not valid_seen_by and seen_by:
            logger.warning(f"No valid edge IDs in seen_by for station {station_id}: {seen_by}")
        station = Station(station_id, valid_seen_by)
        self.stations[station_id] = station
        logger.info(f"Station {station_id} joined with seen_by: {valid_seen_by}")
        self.assign_station(station)
        # self.rebalance_all()

    def on_station_leave(self, station_id):
        current_edge = self.station_to_edge.get(station_id)
        if current_edge and current_edge in self.edges:
            self.edges[current_edge].assigned_stations.discard(station_id)
            logger.info(f"Station {station_id} unassigned from edge {current_edge}")
        self.stations.pop(station_id, None)
        self.station_to_edge.pop(station_id, None)
        logger.info(f"Station {station_id} left")
        # self.rebalance_all()

    def on_edge_join(self, edge_id):
        self.edges[edge_id] = EdgeServer(edge_id)
        logger.info(f"Edge {edge_id} joined")
        # self.rebalance_all()

    def on_edge_leave(self, edge_id):
        if edge_id not in self.edges:
            logger.warning(f"Edge {edge_id} not found for removal")
            return
        reassigned_stations = self.edges[edge_id].assigned_stations.copy()
        self.edges.pop(edge_id)
        logger.info(f"Edge {edge_id} left, reassigning {len(reassigned_stations)} stations")
        for station_id in reassigned_stations:
            self.station_to_edge[station_id] = None
            if station_id in self.stations:
                self.stations[station_id].seen_by.pop(edge_id, None)
            if self.mqtt_client:
                try:
                    self.mqtt_client.publish_assignment(edge_id, station_id, "unassigned")
                    logger.debug(f"Published unassignment: station {station_id} from edge {edge_id}")
                except Exception as e:
                    logger.error(f"Failed to publish unassignment for station {station_id} from edge {edge_id}: {e}")
        # self.rebalance_all()

    def get_assignments(self):
        logger.debug(f"Current assignments: {json.dumps(self.station_to_edge, indent=2)}")
        return dict(self.station_to_edge)

    def get_edge_loads(self):
        loads = {eid: len(es.assigned_stations) for eid, es in self.edges.items()}
        logger.debug(f"Edge loads: {json.dumps(loads, indent=2)}")
        return loads