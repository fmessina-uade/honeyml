# Imagen del motor de triaje y de la API del panel.
#
# Una sola para los dos: comparten el paquete y sus dependencias, y cada servicio del compose elige
# qué proceso corre. Lleva también las dependencias de análisis porque las herramientas del motor
# importan el módulo de arquetipos, que carga pandas y scikit-learn apenas se importa.
#
# Se construye desde la raíz del repositorio, cuyo .dockerignore deja pasar solo el paquete y el
# archivo de versiones. La base va fijada por digest y las dependencias por versión exacta, así una
# reconstrucción da la misma imagen que corre y las cifras del motor se pueden reproducir.
FROM python:3.12-slim@sha256:f77ac9e44ae96ef2c90b8053ea08c31f8be030f824196b0ae4db6d462c84e51f

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1

WORKDIR /app

COPY pyproject.toml ./
COPY infra/analisis/versiones.txt ./
COPY src ./src

# El código queda instalado en site-packages, así que la copia de trabajo se borra: con el sistema
# de archivos de solo lectura no hay nada que editar ahí y solo confundiría al que entre a mirar.
RUN pip install ".[agent,api,analysis]" -c versiones.txt \
    && rm -rf src build versiones.txt \
    && useradd --system --uid 10001 --home-dir /app --shell /usr/sbin/nologin honeyml

# Las rutas del código a los artefactos derivados son relativas a este directorio, y el compose monta
# ahí data/processed de solo lectura.
USER honeyml
