FROM bielr/util-aligner-server

ARG APP_ENV=base

ENV APP_ENV=$APP_ENV
ENV PYTHONUNBUFFERED=1

COPY ./requirements /requirements
COPY ./r-requirements /r-requirements

RUN pip install -r /requirements/${APP_ENV}.txt

RUN Rscript --vanilla /r-requirements/${APP_ENV}.R

CMD ["bash"]

ENV PYTHONPATH /opt/server:/opt/libs/stringdb-tools/scripts:/opt/libs/geneontology-tools/scripts:/opt/libs/semantic-similarity:/opt/libs/ppi-sources
WORKDIR /opt

