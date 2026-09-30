# Dionaea 0.11.0, fijada por digest por la misma razón que Cowrie: que una reconstrucción no cambie
# el sensor sin que nadie lo decida.
FROM dinotools/dionaea@sha256:6f06d0a6035c865cb60ef51bd96ff3b1f25ee4bfcd852dad3f551bc2d93464ca

LABEL maintainer="HoneyML"
LABEL description="Honeypot multiprotocolo Dionaea: SMB, HTTP, FTP, MySQL, MSSQL"

# El entrypoint siembra /opt/dionaea/etc copiando desde /opt/dionaea/template/etc en el primer
# arranque, solo si etc/dionaea no existe. Por eso la configuración va cocinada en el template y no
# bind-montada: un montaje sobre etc/ crearía el directorio, el entrypoint saltearía esa copia y los
# servicios quedarían sin cargar.

# Registro de texto recortado a advertencias: la telemetría de eventos sale por log_json.
COPY dionaea.cfg /opt/dionaea/template/etc/dionaea/dionaea.cfg

# Salida JSON estructurada para el pipeline ECS, la que sigue Filebeat.
COPY log_json.yaml /opt/dionaea/template/etc/dionaea/ihandlers-enabled/log_json.yaml

# SIP apagado, porque falla con sqlite "database is locked", y pptp apagado por ruidoso.
RUN rm -f /opt/dionaea/template/etc/dionaea/services-enabled/sip.yaml \
          /opt/dionaea/template/etc/dionaea/services-enabled/pptp.yaml

# Corta el bucle de MSSQL ante una cabecera TDS imposible, que es la causa de los cuelgues. El largo
# que declara la cabecera incluye sus propios 8 bytes, pero el manejador solo descarta el largo 0.
# Con un largo de 1 o 2 vuelve a leer la cabecera sobre ese pedazo corto, el campo queda en su valor
# por defecto, que es 0, y la posición no avanza nunca. Alcanza un paquete de 8 bytes al 1433 para
# clavar el único hilo del sensor al 100 % sin límite de tiempo: deja de aceptar conexiones sin
# morirse, y solo lo saca el watchdog. Rechazar todo largo menor a 8 deja afuera únicamente
# cabeceras que el protocolo no admite.
RUN F=/opt/dionaea/lib/dionaea/python/dionaea/mssql/mssql.py; \
    [ "$(grep -c '^ *if p.Length == 0:$' "$F")" = 1 ] || { echo "mssql.py: no está la validación del largo; revisar antes de reemplazarla"; exit 1; }; \
    sed -i 's/^\( *\)if p.Length == 0:$/\1if p.Length < 8:/' "$F" && \
    grep -q '^ *if p.Length < 8:$' "$F"

# Neutraliza el pretty-print de paquetes. Cada paquete recibido pasa por Packet.show(), que recorre
# campo por campo armando la representación de cada valor y emite un registro de depuración por
# campo. El texto se descarta, porque el registro está en advertencias, pero el costo se paga igual
# sobre el único hilo: una ráfaga de miles de cabeceras al 1433 lo ocupa varios segundos. La captura
# no cambia, porque la telemetría sale por log_json y por los bistreams y no por show(). La clase
# Packet vive en smb/include/packet.py y de ella heredan los paquetes de MSSQL, SMB y MySQL, así que
# un solo reemplazo los cubre a los tres. El archivo original deja ese corte previsto y comentado al
# inicio del método.
RUN F=/opt/dionaea/lib/dionaea/python/dionaea/smb/include/packet.py; \
    grep -q '^class Packet(' "$F" || { echo "packet.py: no está la clase Packet; revisar antes de neutralizar show()"; exit 1; }; \
    printf '\n\ndef _honeyml_show_desactivado(self, *args, **kwargs):\n    return None\n\n\nPacket.show = _honeyml_show_desactivado\n' >> "$F"

EXPOSE 21 80 443 445 135 1433 3306
