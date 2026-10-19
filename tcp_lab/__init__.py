"""
TCP Congestion Control Lab.

A separate add-on to the SDN load balancer project. It has two parts:

  simulator/  - pure Python, per-packet, event-driven TCP simulation of
                Tahoe, Reno and New Reno (no Mininet needed).
  mininet/    - real Linux TCP traffic through a Mininet dumbbell topology
                (Linux has no Tahoe; "reno" with SACK off behaves like New Reno).
"""
