FROM dinotools/dionaea:latest

LABEL maintainer="HoneyML Project"
LABEL description="Dionaea multiprotocol honeypot - SMB, HTTP, FTP, MySQL, MSSQL"

# The entrypoint seeds /opt/dionaea/etc by copying from /opt/dionaea/template/etc on first boot,
# only if etc/dionaea doesn't exist. So we bake the config into the template instead of
# bind-mounting: a mount over etc/ would create the dir and the entrypoint would skip that copy,
# leaving the services unloaded.

# 1. Text logging trimmed to warning+; event telemetry goes out via log_json (JSON).
COPY dionaea.cfg /opt/dionaea/template/etc/dionaea/dionaea.cfg

# 2. Structured JSON output for the ECS pipeline (Filebeat tails it).
COPY log_json.yaml /opt/dionaea/template/etc/dionaea/ihandlers-enabled/log_json.yaml

# 3. Disable SIP (flaky: fails with sqlite "database is locked") and pptp (noisy).
RUN rm -f /opt/dionaea/template/etc/dionaea/services-enabled/sip.yaml \
          /opt/dionaea/template/etc/dionaea/services-enabled/pptp.yaml

EXPOSE 21 80 443 445 135 1433 3306
