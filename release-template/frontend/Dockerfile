FROM FOUNDRY_WEB_IMAGE AS build
USER 1000:1000
COPY --chown=1000:1000 src /app/src
COPY --chown=1000:1000 public /app/public
RUN /app/node_modules/.bin/vite build --configLoader runner --outDir /tmp/release-dist
FROM FOUNDRY_WEB_IMAGE
COPY --from=build /tmp/release-dist /srv/app
COPY server.mjs /opt/foundry/server.mjs
USER 1000:1000
EXPOSE 8080
CMD ["node", "/opt/foundry/server.mjs"]
