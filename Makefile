.PHONY: help up down logs status ps clean deploy-vps dev-up dev-down dev-logs validate lint test \
        test-integration consumer triaje grafo arquetipos modelo evaluacion \
        api dash replays \
        elastic-up elastic-down elastic-logs elastic-dev-up elastic-dev-down elastic-dev-logs \
        es-bootstrap validate-indexing pull-logs

COMPOSE_FILE = infra/honeypots/docker-compose.yml
COMPOSE_DEV  = infra/honeypots/docker-compose.dev.yml
ELASTIC_FILE = infra/elastic/docker-compose.yml
ELASTIC_DEV  = infra/elastic/docker-compose.dev.yml
VPS_IP       ?= $(shell cat .vps_ip 2>/dev/null || echo "")
SSH_PORT     ?= 2200
SSH_USER     ?= honeyml
SSH_KEY      ?= ~/.ssh/honeyml_ed25519_v2


help:
	@echo ""
	@echo "  HoneyML - Comandos de infraestructura"
	@echo ""
	@echo "  Calidad y validación:"
	@echo "    make validate  Validación completa: config, contenedores, conectividad"
	@echo "    make lint      Linting: shellcheck, yamllint, Python (ruff + mypy)"
	@echo "    make test      Tests unitarios con pytest (Fases 2 y 3)"
	@echo ""
	@echo "  Desarrollo local (puertos seguros, sin tocar el sistema):"
	@echo "    make dev-up    Levantar honeypots en local (Cowrie:2222, Dionaea:8080)"
	@echo "    make dev-down  Detener entorno local"
	@echo "    make dev-logs  Ver logs del entorno local"
	@echo ""
	@echo "  Pipeline de datos (Fase 2 - Elastic Stack + ECS):"
	@echo "    make pull-logs        Bajar logs reales del VPS a data/logs/"
	@echo "    make elastic-dev-up   Levantar Elastic Stack en local (ES/Kibana/Logstash/Filebeat)"
	@echo "    make elastic-dev-down Detener el stack local"
	@echo "    make es-bootstrap     Aplicar plantilla componible ECS a Elasticsearch"
	@echo "    make validate-indexing  Validar indexación y normalización ECS"
	@echo "    make elastic-up       Levantar el stack en el VPS (producción)"
	@echo ""
	@echo "  Panel educativo (demo):"
	@echo "    make replays   Extraer sesiones de ataque anotadas"
	@echo "    make api       Levantar la API (FastAPI, puerto 8000)"
	@echo "    make dash      Levantar el panel (Vite, puerto 5173)"
	@echo ""
	@echo "  Producción (VPS):"
	@echo "    make up        Iniciar contenedores en el VPS (puertos reales)"
	@echo "    make down      Detener contenedores"
	@echo "    make logs      Ver logs en tiempo real"
	@echo "    make ps        Estado de contenedores"
	@echo "    make status    Resumen de estado del sistema"
	@echo "    make deploy-vps  Copiar scripts de infraestructura al VPS"
	@echo ""
	@echo "  Variables:"
	@echo "    VPS_IP    IP del VPS de DigitalOcean (o definir en .vps_ip)"
	@echo "    SSH_PORT  Puerto SSH admin (default: 2200)"
	@echo "    SSH_USER  Usuario SSH (default: honeyml)"
	@echo ""

# quality & validation

validate:
	@/bin/bash scripts/validate_local.sh

lint:
	@echo "--- shellcheck ---"
	@# -S warning: los scripts de verificación usan `comando && ok ... || fallo ...` a propósito,
	@# y shellcheck lo marca como nota de estilo (SC2015). Con el umbral por defecto la puerta
	@# quedaba siempre en rojo por doce avisos cosméticos, que es la forma más segura de que nadie
	@# vuelva a mirarla. Los errores y advertencias reales siguen deteniendo la corrida.
	@if command -v shellcheck >/dev/null 2>&1; then \
		shellcheck -S warning infra/vps/scripts/*.sh scripts/validate_local.sh && echo "  shellcheck OK"; \
	else \
		echo "  shellcheck no instalado (brew install shellcheck)"; \
	fi
	@echo "--- yamllint ---"
	@if command -v yamllint >/dev/null 2>&1; then \
		yamllint infra/honeypots/docker-compose.yml infra/honeypots/docker-compose.dev.yml && echo "  yamllint OK"; \
	else \
		echo "  yamllint no instalado (pip install yamllint)"; \
	fi
	@# Se usan los ejecutables del entorno del proyecto, no los del PATH: nadie activa el entorno
	@# para correr make, y buscarlos en el PATH hacía que la comprobación se saltara en silencio
	@# aunque estuvieran instalados.
	@echo "--- ruff (Python) ---"
	@if [ -x ./.venv/bin/ruff ]; then \
		./.venv/bin/ruff check src/ scripts/ tests/ && ./.venv/bin/ruff format --check src/ scripts/ tests/; \
	else \
		echo "  ruff no instalado (pip install -e \".[dev]\")"; \
	fi
	@echo "--- mypy (tipos Python) ---"
	@if [ -x ./.venv/bin/mypy ]; then \
		./.venv/bin/mypy src/; \
	else \
		echo "  mypy no instalado (pip install -e \".[dev]\")"; \
	fi

test:
	@# Sin `|| echo`: una suite que falla tiene que detener la corrida. Antes cualquier fallo se
	@# convertía en "Sin tests todavía" y make devolvía éxito, con lo que la verificación existía
	@# en el Makefile pero no en la práctica.
	@# Las de integración quedan fuera por defecto: piden los sensores escuchando en la máquina
	@# local, y los sensores viven en el servidor. Están marcadas desde que se escribieron, pero el
	@# Makefile nunca usó la marca, así que corrían siempre y fallaban siempre.
	@if [ -x ./.venv/bin/pytest ]; then \
		./.venv/bin/pytest tests/ -v --tb=short -m "not integration"; \
	else \
		echo "pytest no instalado. Instalar con: pip install -e \".[dev]\""; \
		exit 1; \
	fi

# Solo tiene sentido con los sensores corriendo acá: make dev-up primero.
test-integration:
	@./.venv/bin/pytest tests/ -v --tb=short -m integration

dev-up:
	docker compose -f $(COMPOSE_FILE) -f $(COMPOSE_DEV) up -d
	@echo ""
	@echo "Honeypots locales iniciados:"
	@echo "  Cowrie SSH    -> ssh -p 2222 -o StrictHostKeyChecking=no root@localhost"
	@echo "  Cowrie Telnet -> telnet localhost 2323"
	@echo "  Dionaea HTTP  -> curl http://localhost:8080"
	@echo "  Dionaea SMB   -> localhost:4445"
	@echo ""
	@echo "Logs: make dev-logs"

dev-down:
	docker compose -f $(COMPOSE_FILE) -f $(COMPOSE_DEV) down --remove-orphans

dev-logs:
	docker compose -f $(COMPOSE_FILE) -f $(COMPOSE_DEV) logs -f --tail=50

# production (VPS)

up:
	docker compose -f $(COMPOSE_FILE) up -d
	@echo "Honeypots iniciados. Ver logs con: make logs"

down:
	docker compose -f $(COMPOSE_FILE) down

logs:
	docker compose -f $(COMPOSE_FILE) logs -f --tail=100

ps:
	docker compose -f $(COMPOSE_FILE) ps

status:
	@echo "=== Contenedores ==="
	@docker compose -f $(COMPOSE_FILE) ps 2>/dev/null || echo "Docker Compose no disponible"
	@echo ""
	@echo "=== Red honeypot_net ==="
	@docker network inspect honeypot_net 2>/dev/null | grep -E '"Name"|"IPv4Address"' || echo "Red no creada"
	@echo ""
	@echo "=== Últimas entradas Cowrie ==="
	@docker exec cowrie cat /cowrie/cowrie-git/var/log/cowrie/cowrie.log 2>/dev/null | tail -5 || echo "Contenedor cowrie no activo"

clean:
	docker compose -f $(COMPOSE_FILE) down -v
	@echo "Contenedores y volúmenes eliminados."

deploy-vps:
ifndef VPS_IP
	$(error VPS_IP no definido. Crear archivo .vps_ip o exportar: export VPS_IP=<ip>)
endif
	rsync -avz --progress \
		-e "ssh -p $(SSH_PORT) -o StrictHostKeyChecking=accept-new" \
		infra/ \
		$(SSH_USER)@$(VPS_IP):/home/$(SSH_USER)/honeyml/infra/
	@echo "Archivos de infraestructura copiados al VPS $(VPS_IP)"
	@echo "Siguiente paso: ssh -p $(SSH_PORT) $(SSH_USER)@$(VPS_IP)"

# pipeline de datos: Elastic Stack + ECS

# Baja los registros crudos de Cowrie desde el volumen de Docker del VPS a data/logs/cowrie/.
# Necesita la clave SSH de administración. Usa sudo remoto para leer el volumen, que es de root.
pull-logs:
ifndef VPS_IP
	$(error VPS_IP no definido. Crear archivo .vps_ip o exportar: export VPS_IP=<ip>)
endif
	@mkdir -p data/logs/cowrie data/logs/dionaea
	rsync -avz --progress --rsync-path="sudo rsync" \
		-e "ssh -p $(SSH_PORT) -i $(SSH_KEY) -o IdentitiesOnly=yes -o StrictHostKeyChecking=accept-new" \
		$(SSH_USER)@$(VPS_IP):/var/lib/docker/volumes/honeypots_cowrie_logs/_data/ \
		data/logs/cowrie/
	@echo "Logs de Cowrie descargados en data/logs/cowrie/"
	# El log_json de Dionaea escribe bajo var/lib/dionaea/, y el Filebeat de desarrollo lo espera
	# plano. Van include/exclude en lugar de un glob: con --rsync-path="sudo rsync" el shell remoto
	# nunca lo expande, y los archivos vecinos (la base sqlite, binarios capturados) tienen que
	# quedar afuera.
	rsync -avz --progress --rsync-path="sudo rsync" \
		--include='dionaea.json' --include='dionaea.json.[0-9]*' --exclude='*' \
		-e "ssh -p $(SSH_PORT) -i $(SSH_KEY) -o IdentitiesOnly=yes -o StrictHostKeyChecking=accept-new" \
		$(SSH_USER)@$(VPS_IP):/var/lib/docker/volumes/honeypots_dionaea_var/_data/lib/dionaea/ \
		data/logs/dionaea/
	@echo "Logs de Dionaea descargados en data/logs/dionaea/"

elastic-dev-up:
	@if [ ! -f infra/elastic/.env ]; then cp infra/elastic/.env.example infra/elastic/.env; echo "Creado infra/elastic/.env desde el ejemplo."; fi
	# Se levantan almacenamiento y procesamiento, y se aplica la plantilla ECS ANTES que Filebeat,
	# así los índices salen con los tipos ECS correctos y no hay carrera con el mapeo.
	docker compose --env-file infra/elastic/.env -f $(ELASTIC_FILE) -f $(ELASTIC_DEV) up -d elasticsearch logstash kibana
	@ES_URL=http://localhost:9200 bash infra/elastic/scripts/es_bootstrap.sh
	docker compose --env-file infra/elastic/.env -f $(ELASTIC_FILE) -f $(ELASTIC_DEV) up -d filebeat
	@echo ""
	@echo "Elastic Stack local iniciado:"
	@echo "  Elasticsearch -> http://localhost:9200"
	@echo "  Kibana        -> http://localhost:5601"
	@echo ""
	@echo "Siguiente: make validate-indexing"

elastic-dev-down:
	docker compose -f $(ELASTIC_FILE) -f $(ELASTIC_DEV) down --remove-orphans

elastic-dev-logs:
	docker compose -f $(ELASTIC_FILE) -f $(ELASTIC_DEV) logs -f --tail=80

elastic-up:
	@if [ ! -f infra/elastic/.env ]; then cp infra/elastic/.env.example infra/elastic/.env; fi
	docker compose --env-file infra/elastic/.env -f $(ELASTIC_FILE) up -d elasticsearch logstash kibana
	@ES_URL=http://localhost:9200 bash infra/elastic/scripts/es_bootstrap.sh
	docker compose --env-file infra/elastic/.env -f $(ELASTIC_FILE) up -d filebeat
	@echo "Elastic Stack iniciado en el VPS. Acceso privado por túnel SSH:"
	@echo "  ssh -L 5601:localhost:5601 -L 9200:localhost:9200 -p $(SSH_PORT) $(SSH_USER)@$(VPS_IP)"

elastic-down:
	docker compose -f $(ELASTIC_FILE) down

elastic-logs:
	docker compose -f $(ELASTIC_FILE) logs -f --tail=100

es-bootstrap:
	@ES_URL=$${ES_URL:-http://localhost:9200} bash infra/elastic/scripts/es_bootstrap.sh

validate-indexing:
	@python3 infra/elastic/scripts/validate_indexing.py --es-url $${ES_URL:-http://localhost:9200}

# salida compacta para las capturas del informe: sin lista de índices por día ni direcciones
validate-indexing-resumen:
	@python3 infra/elastic/scripts/validate_indexing.py --es-url $${ES_URL:-http://localhost:9200} --resumen

# panel educativo: API + SPA. Se corren `make api` y `make dash` en dos terminales.

REDIS_FILE   = infra/redis/docker-compose.yml

# Bus de eventos (Redis Streams). Vive en la zona de análisis y se une a elastic_net, así que el
# stack tiene que estar arriba antes: la red se crea ahí.
bus-up:
	@if [ ! -f infra/redis/.env ]; then cp infra/redis/.env.example infra/redis/.env; echo "Creado infra/redis/.env desde el ejemplo."; fi
	docker compose --env-file infra/redis/.env -f $(REDIS_FILE) up -d
	@echo ""
	@echo "Bus de eventos disponible en 127.0.0.1:6379"

bus-down:
	docker compose --env-file infra/redis/.env -f $(REDIS_FILE) down

bus-status:
	@./.venv/bin/python scripts/bus_status.py

# Consumidor del bus. Sigue el stream hasta que se lo interrumpe; con LIMITE=N atiende N eventos
# y sale, que es la forma de inspeccionar sin quedarse escuchando.
#   make consumer            make consumer LIMITE=20
consumer:
	@./.venv/bin/python -m honeyml.agent.consumer $(if $(LIMITE),--limite $(LIMITE),)

# El motor completo: consume el bus, tría cada evento por el grafo y persiste la decisión. Necesita
# el stack y el bus arriba, y la credencial del proveedor de inferencia exportada.
#
# Con LIMITE=N tría N eventos y sale, que es la forma de probarlo sin quedarse escuchando y sin
# gastar más llamadas pagas de las que uno quería.
# Antes de arrancar informa el atraso del grupo y lo que costaría triarlo. Si son más de dos mil
# eventos y no se pidió un límite, no arranca: el bus llegó a tener 52.165 mensajes acumulados, que
# son entre siete y quince dólares de inferencia, y eso no se gasta sin pedirlo.
#   make triaje LIMITE=5      prueba con cinco eventos
#   make triaje TODO=1        tría el atraso completo
triaje:
	@./.venv/bin/python -m honeyml.agent.motor $(if $(LIMITE),--limite $(LIMITE),) $(if $(TODO),--todo,)

# Topología del motor de triaje y qué nodo tiene implementación hoy.
grafo:
	@./.venv/bin/python -m honeyml.agent.graph

# La escala de severidad tal como se le publica al proveedor de inferencia.
severidad:
	@./.venv/bin/python -m honeyml.agent.severidad

# Entrena el clasificador final, lo persiste y calcula el ranking por permutación.
# Tarda unos dos minutos: la parte lenta son las probabilidades fuera de muestra del umbral.
modelo:
	@./.venv/bin/python -m honeyml.features.uwf_export

# Las cuatro preguntas que la comparación y el ajuste no contestan: si el modelo le gana a un
# clasificador trivial, adónde se equivoca, cuánto pesa el puerto de destino frente a las otras
# catorce columnas, y cuánto se mueve el resultado al cambiar la partición.
# Ajusta siete veces sobre 1,4 millones de filas, así que tarda unos minutos.
#   make evaluacion RAPIDO=1     submuestreado, para validar el armado
evaluacion:
	@./.venv/bin/python -m honeyml.features.uwf_evaluacion $(if $(RAPIDO),--rapido,)

# Un solo comando para todo el ciclo de datos: bajar registros frescos de los sensores, esperar a
# que el pipeline los ingiera, y regenerar todos los artefactos derivados. Reemplaza correr cinco
# objetivos a mano.
#
# NO levanta el stack: primero hay que correr `make elastic-dev-up`. Mantenerlos separados hace que
# un refresh no pueda levantar contenedores que uno no esperaba, y en silencio.
refresh:
	@echo "==> 1/3  Descargando registros de los sensores"
	@$(MAKE) --no-print-directory pull-logs
	@echo ""
	@echo "==> 2/3  Esperando a que el pipeline ingiera lo nuevo"
	@./.venv/bin/python scripts/wait_for_ingest.py
	@echo ""
	@echo "==> 3/3  Regenerando artefactos derivados"
	@$(MAKE) --no-print-directory artifacts

# Telemetría consolidada: el primer eslabón de la cadena de artefactos derivados.
consolidate:
	@./.venv/bin/python -m honeyml.eda.es_loader

# Ingeniería de características: lee la tabla consolidada, así que va después de `consolidate`.
features:
	@./.venv/bin/python -m honeyml.features.build_features
	@./.venv/bin/python -m honeyml.features.command_encoding

# Todo lo que lee del índice o de la tabla consolidada. El orden importa:
# `consolidate` produce la tabla de la que dependen tanto la ingeniería de características como la
# serie horaria, y `arquetipos` necesita las características ya calculadas.
#
# `arquetipos` faltaba en esta lista: una regeneración dejaba la tabla de características nueva y el
# agrupamiento viejo, así que la sección de tipos de atacante mostraba números de otro corpus que el
# resto del panel.
artifacts: consolidate features snapshot serie-horaria replays fingerprints passwords arquetipos
	@echo ""
	@echo "Artefactos al día."

snapshot:
	@./.venv/bin/python -m honeyml.api.offline

# Serie horaria del respaldo, calculada desde la tabla consolidada y no desde el índice. Es lo que
# hace que la vista por hora del panel funcione con el stack apagado.
serie-horaria:
	@./.venv/bin/python -m honeyml.api.offline --horario

fingerprints:
	@./.venv/bin/python -m honeyml.education.fingerprints

# Arquetipos de atacante: agrupamiento no supervisado sobre las características por dirección.
# Depende de `features`, que es quien genera la tabla que consume.
arquetipos:
	@./.venv/bin/python -m honeyml.features.arquetipos

passwords:
	@./.venv/bin/python -m honeyml.education.password_index

replays:
	@./.venv/bin/python -m honeyml.education.session_replay

api:
	@./.venv/bin/uvicorn honeyml.api.main:app --port 8000 --reload

dash:
	@cd dashboard && npm run dev

# Comprobación en vivo del proveedor de inferencia. Necesita GROQ_API_KEY exportada.
inferencia-ok:
	@./.venv/bin/python -c "import sys; from honeyml.agent.adapters.servicio import comprobar; sys.exit(comprobar())"
