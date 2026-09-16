# py-spy en su propia imagen, para leer la pila de un sensor colgado sin instalar nada en el
# anfitrión. La usa honeyml_watchdog.sh desde un contenedor que comparte el espacio de procesos del
# sensor.
FROM python:3.12-slim
RUN pip install --no-cache-dir py-spy==0.4.2
ENTRYPOINT ["py-spy"]
