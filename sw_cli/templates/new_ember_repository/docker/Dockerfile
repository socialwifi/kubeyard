FROM node:6.10.1

ENV NPM_CONFIG_LOGLEVEL http
# npm install -g npm@4.4.4 Does not work in this version. https://github.com/npm/npm/issues/15611#issuecomment-289133810
RUN cd ~ && npm install npm@4.4.4 && rm -rf /usr/local/lib/node_modules && mv node_modules /usr/local/lib/
RUN npm install --global bower@1.8.0
RUN npm install --global phantomjs@1.9.8
RUN git clone https://github.com/facebook/watchman.git && \
    cd watchman && \
    git checkout v4.5.0 && \
    ./autogen.sh && \
    ./configure --without-python && \
    make && \
    make install && \
    cd .. && \
    rm -r watchman
RUN npm install --global ember-cli@2.12.1

WORKDIR /ember-app/
COPY source/package.json package.json
RUN npm install
COPY source/bower.json bower.json
RUN bower install --allow-root

COPY source/. .
COPY source/bin /scripts
RUN cd /usr/local/bin && for f in /scripts/*; do ln -s "$f" $(basename "${f%.*}"); done
