FROM dinotools/dionaea:latest

LABEL maintainer="HoneyML Project"
LABEL description="Dionaea multiprotocol honeypot — SMB, HTTP, FTP, MySQL, MSSQL"

# El entrypoint inicializa /opt/dionaea/etc copiando desde /opt/dionaea/template/etc en el primer
# arranque, solo si etc/dionaea no existe. Por eso la config se hornea en el template y no se
# bind-montea: un mount sobre etc/ crearia el directorio y el entrypoint saltearia esa copia,
# dejando los servicios sin cargar.

# 1. Logging de texto acotado a warning+; la telemetria de eventos sale por log_json (JSON).
COPY dionaea.cfg /opt/dionaea/template/etc/dionaea/dionaea.cfg

# 2. Salida estructurada JSON para el pipeline ECS (Filebeat la tail-ea).
COPY log_json.yaml /opt/dionaea/template/etc/dionaea/ihandlers-enabled/log_json.yaml

# 3. Desactivar SIP (inestable: falla con sqlite "database is locked") y pptp (ruidoso).
RUN rm -f /opt/dionaea/template/etc/dionaea/services-enabled/sip.yaml \
          /opt/dionaea/template/etc/dionaea/services-enabled/pptp.yaml

EXPOSE 21 80 443 445 135 1433 3306
