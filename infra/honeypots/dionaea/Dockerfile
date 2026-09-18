FROM dinotools/dionaea:latest

LABEL maintainer="HoneyML"
LABEL description="Honeypot multiprotocolo Dionaea: SMB, HTTP, FTP, MySQL, MSSQL"

# El entrypoint siembra /opt/dionaea/etc copiando desde /opt/dionaea/template/etc en el primer
# arranque, solo si etc/dionaea no existe. Por eso la configuración va cocinada en el template y no
# bind-montada: un montaje sobre etc/ crearía el directorio, el entrypoint saltearía esa copia y los
# servicios quedarían sin cargar.

# 1. Registro de texto recortado a advertencias; la telemetría de eventos sale por log_json (JSON).
COPY dionaea.cfg /opt/dionaea/template/etc/dionaea/dionaea.cfg

# 2. Salida JSON estructurada para el pipeline ECS (la sigue Filebeat).
COPY log_json.yaml /opt/dionaea/template/etc/dionaea/ihandlers-enabled/log_json.yaml

# 3. SIP apagado (falla con sqlite "database is locked") y pptp apagado (ruidoso).
RUN rm -f /opt/dionaea/template/etc/dionaea/services-enabled/sip.yaml \
          /opt/dionaea/template/etc/dionaea/services-enabled/pptp.yaml

# 4. Neutraliza el pretty-print de paquetes, que es la causa de los cuelgues.
#    Cada paquete recibido pasa por Packet.show(), que recorre campo por campo armando la
#    representación de cada valor y emite un registro de depuración por campo. Un flujo con muchas
#    cabeceras al puerto MSSQL hace que el manejador llame a show() miles de veces sobre el único
#    hilo del sensor: se clava un núcleo al 100 % y deja de aceptar conexiones sin morirse. El texto
#    que arma ya se descarta, porque el registro está en advertencias, así que la captura no cambia:
#    la telemetría sale por log_json y por los bistreams, no por show(). La clase Packet vive en
#    smb/include/packet.py y de ella heredan los paquetes de MSSQL, SMB y MySQL, así que un solo
#    reemplazo los cubre a los tres. El archivo original deja ese corte previsto y comentado al
#    inicio del método.
RUN F=/opt/dionaea/lib/dionaea/python/dionaea/smb/include/packet.py; \
    grep -q '^class Packet(' "$F" || { echo "packet.py: no está la clase Packet; revisar antes de neutralizar show()"; exit 1; }; \
    printf '\n\ndef _honeyml_show_desactivado(self, *args, **kwargs):\n    return None\n\n\nPacket.show = _honeyml_show_desactivado\n' >> "$F"

EXPOSE 21 80 443 445 135 1433 3306
