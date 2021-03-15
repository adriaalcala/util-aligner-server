FROM python:3.9

ARG APP_ENV=base

ENV APP_ENV=$APP_ENV
ENV PYTHONUNBUFFERED=1
ENV DEBIAN_FRONTEND=noninteractive

COPY ./requirements /requirements
COPY ./r-requirements /r-requirements

RUN apt-get update && apt-get -y install tzdata
RUN ln -fs /usr/share/zoneinfo/Europe/Madrid /etc/localtime
RUN dpkg-reconfigure --frontend noninteractive tzdata

RUN apt-get update \
    && apt-get -y install build-essential libxml2-dev zlib1g-dev pkg-config libffi6 libffi-dev libssl-dev libcurl4-openssl-dev \
                          r-base gfortran \
                          libc6-i386 lib32stdc++6

RUN python3.9 -m pip install pip --upgrade
RUN python3.9 -m pip install wheel
RUN pip install -r /requirements/${APP_ENV}.txt

RUN Rscript --vanilla /r-requirements/${APP_ENV}.R

CMD ["bash"]


ENV PYTHONPATH /opt/server:/opt/libs/stringdb-tools/scripts:/opt/libs/geneontology-tools/scripts:/opt/libs/semantic-similarity:/opt/libs/ppi-sources
WORKDIR /opt

