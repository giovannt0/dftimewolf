#!/usr/bin/env bash
#
# This file is generated by l2tdevtools update-dependencies.py any dependency
# related changes should be made in dependencies.ini.

# Exit on error.
set -e

# Dependencies for running dftimewolf, alphabetized, one per line.
# This should not include packages only required for testing or development.
PYTHON2_DEPENDENCIES="python-bs4
                      python-certifi
                      python-chardet
                      python-idna
                      python-requests
                      python-tz
                      python-urllib3";

# Additional dependencies for running dftimewolf tests, alphabetized,
# one per line.
TEST_DEPENDENCIES="python-mock";

# Additional dependencies for doing dftimewolf development, alphabetized,
# one per line.
DEVELOPMENT_DEPENDENCIES="python-sphinx
                          pylint";

sudo add-apt-repository ppa:gift/dev -y
sudo apt-get update -qq
sudo apt-get install -qq -y ${PYTHON2_DEPENDENCIES}

# Pending resolution of https://github.com/log2timeline/l2tdevtools/issues/233.
sudo apt-get install -y python3-pip
sudo pip3 install grr-api-client

if [[ "$*" =~ "include-development" ]]; then
    sudo apt-get install -qq -y ${DEVELOPMENT_DEPENDENCIES}
fi

if [[ "$*" =~ "include-test" ]]; then
    sudo apt-get install -qq -y ${TEST_DEPENDENCIES}
fi

if [[ "$*" =~ "include-docker" ]]; then
    curl -fsSL https://download.docker.com/linux/ubuntu/gpg | sudo apt-key add -
    sudo add-apt-repository \
       "deb [arch=amd64] https://download.docker.com/linux/ubuntu \
       $(lsb_release -cs) \
       stable"
    sudo apt-get update -qq
    sudo apt-get install -qq -y docker-ce
    curl -L https://github.com/docker/compose/releases/download/1.26.1/docker-compose-$(uname -s)-$(uname -m) -o docker-compose
    sudo cp docker-compose /usr/local/bin/docker-compose
    sudo chmod +x /usr/local/bin/docker-compose
fi

if [[ "$*" =~ "include-grr" ]]; then
    # Start the GRR server container.
    mkdir ~/grr-docker
    sudo docker run \
      --name grr-server -v ~/grr-docker/db:/var/grr-datastore \
      -v ~/grr-docker/logs:/var/log \
      -e EXTERNAL_HOSTNAME="localhost" \
      -e ADMIN_PASSWORD="admin" \
      --ulimit nofile=1048576:1048576 \
      -p 127.0.0.1:8000:8000 -p 127.0.0.1:8080:8080 \
      -d grrdocker/grr:v3.2.2.0 grr

    # Wait for GRR to initialize.
    /bin/sleep 120

    # Install the client.
    sudo docker cp grr-server:/usr/share/grr-server/executables/installers .
    sudo dpkg -i installers/*amd64.deb
fi

if [[ "$*" =~ "include-timesketch" ]]; then
    # Start the Timesketch server container.
     export TIMESKETCH_USER="your_username"
     export TIMESKETCH_PASSWORD="your_password"
     git clone https://github.com/google/timesketch.git
     cd timesketch
     cd docker
     cd e2e
     sudo -E docker-compose up -d
     # Wait for Timesketch to initialize
     /bin/sleep 300
     cd ../../..
fi

if [[ "$*" =~ "include-plaso" ]]; then
    sudo apt-get -qq -y install plaso-tools
fi

# pending resolution of https://github.com/log2timeline/l2tdevtools/issues/595
if [[ "$*" =~ "include-turbinia" ]]; then
    echo "Installing Turbinia"
    sudo pip3 install turbinia
fi

echo "Installing dftimewolf requirements"
# Install dftimewolf's pinned requirements
pip3 install -r requirements.txt
