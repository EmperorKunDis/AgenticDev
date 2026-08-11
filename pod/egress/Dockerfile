FROM alpine:3.20
RUN apk add --no-cache tinyproxy
COPY entrypoint.sh /entrypoint.sh
RUN chmod 0555 /entrypoint.sh
EXPOSE 8888
ENTRYPOINT ["/entrypoint.sh"]
