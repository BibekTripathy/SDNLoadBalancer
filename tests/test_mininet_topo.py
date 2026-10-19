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
