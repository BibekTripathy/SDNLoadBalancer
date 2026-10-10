FROM ubuntu:22.04

# Prevent interactive prompts during apt install
ENV DEBIAN_FRONTEND=noninteractive

# Install System Dependencies (Mininet, Open vSwitch, Python)
RUN apt-get update && apt-get install -y \
    mininet \
    openvswitch-switch \
    openvswitch-testcontroller \
    python3 \
    python3-pip \
    iproute2 \
    iputils-ping \
    net-tools \
    curl \
    sudo \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

# Ryu requires older setuptools to build correctly
RUN pip3 install --no-cache-dir "setuptools<59.6.0" wheel

# Install Python Requirements
COPY requirements.txt .
RUN pip3 install --no-cache-dir -r requirements.txt

# Copy all project files
COPY . .

# Expose the API Port
EXPOSE 8000

# Run the unified start script
CMD ["/app/scripts/start_docker.sh"]
