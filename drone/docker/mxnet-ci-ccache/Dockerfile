FROM alpine:3.7

ENV AWS_CLI_VERSION=1.15.40

RUN apk --update --no-cache add \
    python \
    py-pip \
    jq \
    bash \
    git \
    && pip install --no-cache-dir awscli==$AWS_CLI_VERSION \
    && apk del py-pip \
    && rm -rf /var/cache/apk/* /root/.cache/pip/* /usr/lib/python2.7/site-packages/awscli/examples

COPY cache_sync.sh /bin/cache_sync.sh


