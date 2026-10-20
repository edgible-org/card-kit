# card-secrets: the one-shot service a card runs before its apps, which makes the card's internal
# and human secrets on the device (see card-secrets.sh). The card-secrets workflow publishes it as
# ghcr.io/edgible-org/card-secrets:<VERSION>.
FROM alpine:3.20
LABEL org.opencontainers.image.source=https://github.com/edgible-org/card-kit
LABEL org.opencontainers.image.description="Makes a card's secrets on the device at first start"
LABEL org.opencontainers.image.licenses=MIT
RUN apk add --no-cache openssl
COPY card-secrets.sh /usr/local/bin/card-secrets
ENTRYPOINT ["card-secrets"]
CMD ["generate"]
