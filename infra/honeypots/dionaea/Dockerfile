FROM dinotools/dionaea:latest

LABEL maintainer="HoneyML Project"
LABEL description="Dionaea multiprotocol honeypot — SMB, HTTP, FTP, MySQL, MSSQL, SIP"

# La imagen base de dinotools/dionaea ya incluye todos los servicios habilitados
# y gestiona sus propios directorios de trabajo. La configuración personalizada
# para producción se aplica vía variables de entorno o montando archivos YAML
# individuales en /etc/dionaea/services-enabled/ (ver dionaea.cfg para referencia).

EXPOSE 21 80 443 445 135 1433 3306 5060/tcp 5060/udp
