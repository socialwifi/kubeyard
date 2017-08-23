FROM node:6.10.1

RUN yarn global add bower@1.8.0
RUN yarn global add phantomjs-prebuilt@2.1.14
RUN yarn global add ember-cli@2.12.1

WORKDIR /ember-app/
COPY source/package.json source/yarn.lock /ember-app/
RUN yarn
COPY source/bower.json bower.json
RUN bower install --allow-root

COPY source/. .
COPY source/bin /scripts
RUN cd /usr/local/bin && for f in /scripts/*; do ln -s "$f" $(basename "${f%.*}"); done
