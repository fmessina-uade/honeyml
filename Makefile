.PHONY: help up down logs status ps clean deploy-vps dev-up dev-down dev-logs validate lint test \
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
	@if command -v shellcheck >/dev/null 2>&1; then \
		shellcheck infra/vps/scripts/*.sh scripts/validate_local.sh && echo "  shellcheck OK"; \
	else \
		echo "  shellcheck no instalado (brew install shellcheck)"; \
	fi
	@echo "--- yamllint ---"
	@if command -v yamllint >/dev/null 2>&1; then \
		yamllint infra/honeypots/docker-compose.yml infra/honeypots/docker-compose.dev.yml && echo "  yamllint OK"; \
	else \
		echo "  yamllint no instalado (pip install yamllint)"; \
	fi
	@echo "--- ruff (Python) ---"
	@if command -v ruff >/dev/null 2>&1; then \
		ruff check src/ tests/ 2>/dev/null && echo "  ruff OK" || echo "  ruff: sin código Python todavía"; \
	else \
		echo "  ruff no instalado (pip install ruff)"; \
	fi
	@echo "--- mypy (tipos Python) ---"
	@if command -v mypy >/dev/null 2>&1; then \
		mypy src/ 2>/dev/null && echo "  mypy OK" || echo "  mypy: sin código Python todavía"; \
	else \
		echo "  mypy no instalado (pip install mypy)"; \
	fi

test:
	@if command -v pytest >/dev/null 2>&1; then \
		pytest tests/ -v --tb=short 2>/dev/null || echo "  Sin tests todavía (Fase 2+)"; \
	else \
		echo "pytest no instalado. Instalar con: pip install pytest"; \
	fi

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

# data pipeline: Elastic Stack + ECS

# Pull Cowrie's raw logs from the VPS Docker volume to data/logs/cowrie/.
# Needs the admin SSH key. Uses remote sudo to read the volume (owned by root).
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
	# Dionaea's log_json writes under var/lib/dionaea/; the dev Filebeat expects it flat
	# include/exclude instead of a glob: with --rsync-path="sudo rsync" the remote shell
	# never expands it, and the sibling files (sqlite db, captured binaries) must stay out
	rsync -avz --progress --rsync-path="sudo rsync" \
		--include='dionaea.json' --include='dionaea.json.[0-9]*' --exclude='*' \
		-e "ssh -p $(SSH_PORT) -i $(SSH_KEY) -o IdentitiesOnly=yes -o StrictHostKeyChecking=accept-new" \
		$(SSH_USER)@$(VPS_IP):/var/lib/docker/volumes/honeypots_dionaea_var/_data/lib/dionaea/ \
		data/logs/dionaea/
	@echo "Logs de Dionaea descargados en data/logs/dionaea/"

elastic-dev-up:
	@if [ ! -f infra/elastic/.env ]; then cp infra/elastic/.env.example infra/elastic/.env; echo "Creado infra/elastic/.env desde el ejemplo."; fi
	# bring up storage/processing and apply the ECS template BEFORE Filebeat,
	# so indices get the right ECS types (avoids the mapping race).
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

# compact output for the report's screenshots: no per-day index list, no source addresses
validate-indexing-resumen:
	@python3 infra/elastic/scripts/validate_indexing.py --es-url $${ES_URL:-http://localhost:9200} --resumen

# educational dashboard: API + SPA. Run `make api` and `make dash` in two terminals.

snapshot:
	@./.venv/bin/python -m honeyml.api.offline

replays:
	@./.venv/bin/python -m honeyml.education.session_replay

api:
	@./.venv/bin/uvicorn honeyml.api.main:app --port 8000 --reload

dash:
	@cd dashboard && npm run dev
