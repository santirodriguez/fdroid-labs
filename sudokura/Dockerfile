# Disposable, offline-only execution image. Built on a GitHub-hosted runner.
# No credentials, signing tools, or source code are baked into this image.
FROM golang:1.24-bookworm

ENV DEBIAN_FRONTEND=noninteractive
RUN apt-get update \
    && apt-get install -y --no-install-recommends \
         ca-certificates git make python3 python3-venv python3-pip \
         openjdk-17-jdk-headless fonts-dejavu-core file libmagic1 \
         unzip zip xz-utils rsync patch \
    && rm -rf /var/lib/apt/lists/*

# fdroidserver is fetched solely from PyPI during image preparation, never
# from its GitLab repository. Verify the source distribution before installing.
RUN python3 -m venv /opt/fdroid-venv \
    && /opt/fdroid-venv/bin/pip download --index-url https://pypi.org/simple \
         --no-deps --no-binary=:all: --dest /tmp 'fdroidserver==2.4.5' \
    && echo 'f9b52646264c732678e32e37e23a995db20cc61d45622dda5830ce23255547f4  /tmp/fdroidserver-2.4.5.tar.gz' | sha256sum -c - \
    && /opt/fdroid-venv/bin/pip install --no-cache-dir \
         --index-url https://pypi.org/simple /tmp/fdroidserver-2.4.5.tar.gz \
    && /opt/fdroid-venv/bin/pip freeze > /opt/fdroid-package-versions.txt \
    && rm -f /tmp/fdroidserver-2.4.5.tar.gz

ENV PATH="/opt/fdroid-venv/bin:/usr/local/go/bin:${PATH}"
ENV JAVA_HOME="/usr/lib/jvm/java-17-openjdk-amd64"
