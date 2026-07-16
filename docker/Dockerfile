FROM ubuntu:22.04

# Necessary to avoid prompts to configure timezone data.
ENV DEBIAN_FRONTEND=noninteractive

# Install common dependencies
# build-essential: For compiling ASPN-C, etc.
# ccache: To decrease compile times when building C/C++ code.
# curl: For installing uv
# cmake: For building the LCM subproject
# git: For development
# gradle: For building LCM jar
# libasio-dev: For building Fast-DDS
# libglib2.0-dev: To run LCM
# libpython3-dev: For building python modules via pybind
# libtinyxml2-dev: For building Fast-DDS
# ninja-build: For building source code projects
# openjdk-8-jdk : For Java development
RUN apt-get update && apt-get install -y --no-install-recommends \
  build-essential \
  ccache \
  curl \
  cmake \
  git \
  gradle \
  libasio-dev \
  libglib2.0-dev \
  libpython3-dev \
  libtinyxml2-dev \
  ninja-build \
  openssh-server \
  openjdk-8-jdk \
  && apt-get clean \
  && rm -rf /var/lib/apt/lists/*

# Set up work directory
WORKDIR /opt/fastdds_docker_ws

# Clone and build Fast-DDS dependency foonathan_memory_vendor
RUN git clone https://github.com/eProsima/foonathan_memory_vendor.git src/foonathan_memory_vendor \
  && cd src/foonathan_memory_vendor \
  && git checkout v1.3.1 \
  && mkdir build \
  && cd build \
  && cmake .. \
  && cmake --build . --target install -- -j$(nproc) \
  && ldconfig

# Clone and setup Fast-CDR
RUN git clone https://github.com/eProsima/Fast-CDR.git src/Fast-CDR \
  && cd src/Fast-CDR \
  && git checkout v2.2.0 \
  && mkdir build \
  && cd build \
  && cmake .. \
  && cmake --build . --target install -- -j$(nproc) \
  && ldconfig

# Clone and setup Fast-DDS
RUN git clone https://github.com/eProsima/Fast-DDS.git src/Fast-DDS \
  && cd src/Fast-DDS \
  && git checkout v2.14.0 \
  && mkdir build \
  && cd build \
  && cmake .. \
  && cmake --build . --target install -- -j$(nproc) \
  && ldconfig

# Clone and setup Fast-DDS-Gen
RUN git clone https://github.com/eProsima/Fast-DDS-Gen.git src/Fast-DDS-Gen \
  && cd src/Fast-DDS-Gen \
  && git checkout v3.3.0 \
  && ./gradlew assemble \
  && ./gradlew install --install_path=/usr/local/

# Install uv
RUN curl -LsSf https://astral.sh/uv/install.sh | UV_UNMANAGED_INSTALL="/usr/local/bin" bash

WORKDIR /firehose

# Necessary to encode certain characters when compiling the Java code.
ENV LANG=C.UTF-8

# Set up non-root user account
ARG GID
ARG UID
RUN groupadd docker --non-unique -g $GID
RUN useradd docker --non-unique -m -u $UID -g $GID
RUN chown docker:docker /home/docker
RUN echo "ALL ALL=(ALL) NOPASSWD: ALL" >> /etc/sudoers
ENV HOME="/home/docker"
USER docker

ENV PATH=/firehose/.venv/bin:$PATH
ENV VIRTUAL_ENV=/firehose/.venv
