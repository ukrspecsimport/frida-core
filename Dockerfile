FROM ubuntu:22.04 AS frida-base
ARG DEBIAN_FRONTEND=noninteractive
RUN apt-get update
RUN apt-get install -y \
    awscli \
    bison \
    curl \
    file \
    flex \
    git \
    gperf \
    make \
    ninja-build \
    pip \
    pkg-config \
    python-is-python3 \
    unzip \
    valac \
    libncurses5
RUN curl -fsSL https://deb.nodesource.com/setup_20.x | bash -
RUN apt-get install -y nodejs

FROM frida-base AS frida-core-builder
# Download and install the Android NDK and delete the downloaded archive so
# it doesn't take up space in the image layer.
RUN curl -L https://dl.google.com/android/repository/android-ndk-r25c-linux.zip -o android-ndk-r25c-linux.zip \
    && unzip android-ndk-r25c-linux.zip -d /opt \
    && rm android-ndk-r25c-linux.zip
ENV ANDROID_NDK_ROOT=/opt/android-ndk-r25c

# Set up working directory
WORKDIR /frida-core

# Copy the project files
COPY . .

RUN ./configure --host=android-arm64

CMD ["make"]