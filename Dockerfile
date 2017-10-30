#####
# Base docker image for running Evennia-based games in a container.
#
# Install:
#   install `docker` (http://docker.com)
#
# Usage:
#    cd to a folder where you want your game data to be (or where it already is).
#
#	docker run -it -p 4000:4000 -p 4001:4001 -p 4005:4005 -v $PWD:/usr/src/game evennia/evennia
#
#    (If your OS does not support $PWD, replace it with the full path to your current
#    folder).
#
#    You will end up in a shell where the `evennia` command is available. From here you
#    can install and run the game normally. Use Ctrl-D to exit the evennia docker container.
#
# The evennia/evennia base image is found on DockerHub and can also be used
# as a base for creating your own custom containerized Evennia game. For more
# info, see https://github.com/evennia/evennia/wiki/Running%20Evennia%20in%20Docker .
#
FROM alpine

MAINTAINER www.evennia.com

ENV LANG en_US.utf8

ARG USER=evennia
ENV USER=${USER}
ARG BUILD_VERSION=UNKNOWN
ENV EVENNIA_BUILD_VERSION=${BUILD_VERSION}


RUN set -x; \
  addgroup ${USER} \
  && adduser -D -S -G ${USER} ${USER} \
  && apk add --no-cache \
    bash \
    ca-certificates \
    drill \
    gcc \
    libffi-dev \
    musl-dev \
    net-tools \
    jpeg-dev \    
    postgresql-client \
    postgresql-dev \
    python \
    python-dev \
    py-pip \
    py-setuptools \
    su-exec \
    tini \
    zlib-dev

# add the project source
ADD . /usr/src/evennia
ADD bin/docker/docker-entrypoint.sh /entrypoint.sh

# install dependencies
RUN chown -R ${USER}:${USER} /usr/src/evennia \
  && pip install psycopg2 \
  && pip install cryptography \
  && pip install -e /usr/src/evennia

# add the game source when rebuilding a new docker image from inside
# a game dir
ONBUILD ADD . /usr/src/game

# make the game source hierarchy persistent with a named volume.
# mount on-disk game location here when using the container
# to just get an evennia environment.
VOLUME /usr/src/game

# set the working directory
WORKDIR /usr/src/game

# expose the telnet, webserver and websocket client ports
EXPOSE 4000 4001 4005

# set bash prompt
ENV PS1 "evennia|docker \w $ "

# startup a shell when we start the container
ENTRYPOINT  ["/sbin/tini","--","/entrypoint.sh"]

CMD ["evennia","-i","start"]
