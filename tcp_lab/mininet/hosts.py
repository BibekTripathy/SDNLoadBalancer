"""
Names and addresses of the dumbbell hosts.

Kept apart from dumbbell_topo.py (which needs the mininet package) so that
the scenario plans can be built and unit tested without Mininet.
"""

CLIENTS = [("c1", "10.0.0.11"), ("c2", "10.0.0.12"), ("c3", "10.0.0.13")]
SERVERS = [("sv1", "10.0.0.21"), ("sv2", "10.0.0.22")]
