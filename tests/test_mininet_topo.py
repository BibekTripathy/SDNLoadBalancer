"""Tests for how topology/mininet_topo.py starts the backend servers (no Mininet needed)."""

import os
import sys

from topology import mininet_topo

SS_LISTENING = "LISTEN 0      5            0.0.0.0:80        0.0.0.0:*\n"
SS_OTHER_PORT = "LISTEN 0      5            0.0.0.0:8080      0.0.0.0:*\n"


class FakeNode:
    """Stands in for a Mininet host: records commands and answers ss/tail."""

    def __init__(self, ip, listening=True):
        self.ip = ip
        self.listening = listening
        self.commands = []

    def IP(self):
        return self.ip

    def cmd(self, command):
        self.commands.append(command)
        if command.startswith("ss "):
            return SS_LISTENING if self.listening else ""
        if command.startswith("tail "):
            return "Traceback: boom\n"
        return ""


class FakeNet:
    def __init__(self, nodes):
        self.nodes = nodes

    def get(self, name):
        return self.nodes[name]


def test_pick_python_falls_back_to_sys_executable(monkeypatch, tmp_path):
    monkeypatch.setattr(mininet_topo, "REPO_DIR", str(tmp_path))
    assert mininet_topo.pick_python() == sys.executable


def test_pick_python_prefers_existing_venv(monkeypatch, tmp_path):
    venv_python = tmp_path / ".venv" / "bin" / "python"
    venv_python.parent.mkdir(parents=True)
    venv_python.write_text("#!/bin/sh\n")
    venv_python.chmod(0o755)
    monkeypatch.setattr(mininet_topo, "REPO_DIR", str(tmp_path))
    assert mininet_topo.pick_python() == str(venv_python)


def test_server_command_uses_absolute_server_app_path():
    command = mininet_topo.server_command("server2", 80, python="/usr/bin/python3")
    assert os.path.isabs(mininet_topo.SERVER_APP)
    assert os.path.isfile(mininet_topo.SERVER_APP)
    assert command.startswith("/usr/bin/python3 -u ")
    assert mininet_topo.SERVER_APP in command
    assert "--name server2 --port 80" in command
    assert "$(pwd)" not in command and ".venv" not in command
    assert command.endswith("> /tmp/server2.log 2>&1 &")


def test_is_listening_matches_only_the_port():
    assert mininet_topo.is_listening(SS_LISTENING, 80)
    assert not mininet_topo.is_listening(SS_OTHER_PORT, 80)
    assert not mininet_topo.is_listening("", 80)
    assert mininet_topo.is_listening("LISTEN 0 5 [::]:80 [::]:*\n", 80)


def test_start_backends_reports_real_ips_and_log_tail(monkeypatch):
    messages = []
    monkeypatch.setattr(mininet_topo, "info", messages.append, raising=False)
    nodes = {
        "server1": FakeNode("10.0.0.2"),
        "server2": FakeNode("10.0.0.3", listening=False),
        "server3": FakeNode("10.0.0.4"),
    }
    monkeypatch.setattr(
        mininet_topo,
        "wait_until_listening",
        lambda node, port=80, timeout=5.0: node.listening,
    )

    assert mininet_topo.start_backends(FakeNet(nodes)) is False
    text = "".join(messages)
    assert "server1 is listening on 10.0.0.2:80" in text
    assert "server3 is listening on 10.0.0.4:80" in text
    assert "server2 (10.0.0.3:80) is not listening" in text
    assert "Traceback: boom" in text
    assert "10.0.0.1:80" not in text
    for node in nodes.values():
        assert any(SERVER_APP_NAME in c for c in node.commands)


SERVER_APP_NAME = "server_app.py"


def test_find_subnet_conflict():
    docker = (
        "1: lo    inet 127.0.0.1/8 scope host lo\n"
        "2: eth0@if9    inet 172.17.0.2/16 brd 172.17.255.255 scope global eth0\n"
        "5: mgmt0    inet 10.0.0.254/24 scope global mgmt0\n"
    )
    assert mininet_topo.find_subnet_conflict(docker) is None
    home_lan = "3: wlan0    inet 10.0.0.37/24 brd 10.0.0.255 scope global wlan0\n"
    assert mininet_topo.find_subnet_conflict(home_lan) == "wlan0"
    assert mininet_topo.find_subnet_conflict("") is None


def test_mgmt_commands_are_idempotent():
    add = mininet_topo.mgmt_add_command("s1")
    assert add.startswith("ovs-vsctl --may-exist add-port s1 mgmt0")
    assert "type=internal" in add and "ofport_request=1000" in add
    # Above the 2-254 range the API accepts for backend switch ports
    assert mininet_topo.MGMT_OFPORT > 254
    assert mininet_topo.mgmt_address_commands() == [
        "ip addr replace 10.0.0.254/24 dev mgmt0",
        "ip link set mgmt0 up",
    ]


def fake_root(answers, ran):
    """run_root stand-in: the first matching prefix in answers gives (code, output)."""

    def run(command):
        ran.append(command)
        for prefix, answer in answers:
            if command.startswith(prefix):
                return answer
        return 0, ""

    return run


def test_add_mgmt_port_adds_when_missing(monkeypatch):
    ran = []
    monkeypatch.setattr(mininet_topo, "info", lambda text: None, raising=False)
    monkeypatch.delenv("SDN_MGMT_PORT", raising=False)
    monkeypatch.setattr(
        mininet_topo,
        "run_root",
        fake_root(
            [("ovs-vsctl port-to-br", (1, "no port")), ("ip link show", (1, ""))], ran
        ),
    )
    assert mininet_topo.add_mgmt_port("s1") is True
    assert mininet_topo.mgmt_add_command("s1") in ran
    assert "ip addr replace 10.0.0.254/24 dev mgmt0" in ran


def test_add_mgmt_port_skips_add_when_already_on_bridge(monkeypatch):
    ran = []
    monkeypatch.setattr(mininet_topo, "info", lambda text: None, raising=False)
    monkeypatch.delenv("SDN_MGMT_PORT", raising=False)
    monkeypatch.setattr(
        mininet_topo,
        "run_root",
        fake_root([("ovs-vsctl port-to-br", (0, "s1\n"))], ran),
    )
    assert mininet_topo.add_mgmt_port("s1") is True
    assert mininet_topo.mgmt_add_command("s1") not in ran


def test_add_mgmt_port_refuses_on_a_10_0_0_lan(monkeypatch):
    ran = []
    monkeypatch.setattr(mininet_topo, "info", lambda text: None, raising=False)
    monkeypatch.delenv("SDN_MGMT_PORT", raising=False)
    lan = (0, "3: wlan0    inet 10.0.0.37/24 brd 10.0.0.255 scope global wlan0\n")
    monkeypatch.setattr(
        mininet_topo, "run_root", fake_root([("ip -o -4 addr", lan)], ran)
    )
    assert mininet_topo.add_mgmt_port("s1") is False
    assert not any(c.startswith("ovs-vsctl --may-exist") for c in ran)


def test_add_mgmt_port_can_be_switched_off(monkeypatch):
    ran = []
    monkeypatch.setattr(mininet_topo, "info", lambda text: None, raising=False)
    monkeypatch.setenv("SDN_MGMT_PORT", "0")
    monkeypatch.setattr(mininet_topo, "run_root", fake_root([], ran))
    assert mininet_topo.add_mgmt_port("s1") is False
    assert ran == []


def test_remove_mgmt_port(monkeypatch):
    ran = []
    monkeypatch.setattr(mininet_topo, "run_root", fake_root([], ran))
    mininet_topo.remove_mgmt_port("s1")
    assert ran == ["ovs-vsctl --if-exists del-port s1 mgmt0"]
