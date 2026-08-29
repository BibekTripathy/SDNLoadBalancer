# Backend Setup & Execution Guide

## 1. Virtual Environment & Dependencies

The project uses Python 3.10 to ensure compatibility with Ryu and Eventlet:

```bash
# Create virtual environment with Python 3.10
python3.10 -m venv .venv
source .venv/bin/activate

# Install all development and runtime dependencies
pip install -r requirements-dev.txt
```

## 2. System Dependencies

Mininet and Open vSwitch require kernel network modules and should be installed via your system package manager:

### Arch Linux:
```bash
sudo pacman -S openvswitch tcpdump iperf3
# Install mininet via AUR (e.g. yay or paru):
yay -S mininet wrk
```

### Ubuntu / Debian:
```bash
sudo apt update
sudo apt install -y mininet openvswitch-switch openvswitch-testcontroller iperf3 wrk tcpdump
```

## 3. Ryu Manager Workaround Launcher

Ryu 4.34 relies on Eventlet APIs that evolved in Python 3.10+. We provide a launcher script [`scripts/ryu_manager.py`](../scripts/ryu_manager.py) that injects the required `eventlet.wsgi.ALREADY_HANDLED = True` compatibility attribute and sets `sys.path` before launching Ryu.

Check version:
```bash
.venv/bin/python scripts/ryu_manager.py --version
```

## 4. Running the Components

### Step 1: Start Ryu SDN Controller
```bash
./scripts/run_ryu.sh
```
*Listens on port `6653` for Open vSwitch connections and OpenFlow 1.3 messages.*

### Step 2: Start Mininet Topology (in a second terminal)
```bash
./scripts/run_mininet.sh
```
*Creates 1 client (`10.0.0.1`), 1 switch (`s1`), and 3 servers (`10.0.0.2`, `10.0.0.3`, `10.0.0.4`), connecting to the Ryu controller.*

### Step 3: Start FastAPI REST & WebSocket Gateway (in a third terminal)
```bash
./scripts/run_api.sh
```
*API is accessible at `http://localhost:8000`, docs at `http://localhost:8000/docs`, and WebSocket at `ws://localhost:8000/ws/events`.*

## 5. Running Automated Tests

Run the test suite covering all 6 load balancing algorithms and API endpoints:

```bash
.venv/bin/pytest -v
```
