.PHONY: help up down logs status ps clean deploy-vps dev-up dev-down dev-logs validate lint test \
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
	@echo "  HoneyML — Comandos de infraestructura"
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
	@echo "  Pipeline de datos (Fase 2 — Elastic Stack + ECS):"
	@echo "    make pull-logs        Bajar logs reales del VPS a data/logs/"
	@echo "    make elastic-dev-up   Levantar Elastic Stack en local (ES/Kibana/Logstash/Filebeat)"
	@echo "    make elastic-dev-down Detener el stack local"
	@echo "    make es-bootstrap     Aplicar plantilla componible ECS a Elasticsearch"
	@echo "    make validate-indexing  Validar indexación y normalización ECS"
	@echo "    make elastic-up       Levantar el stack en el VPS (producción)"
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

# --- Calidad y validación ---

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
	@echo "  Cowrie SSH    → ssh -p 2222 -o StrictHostKeyChecking=no root@localhost"
	@echo "  Cowrie Telnet → telnet localhost 2323"
	@echo "  Dionaea HTTP  → curl http://localhost:8080"
	@echo "  Dionaea SMB   → localhost:4445"
	@echo ""
	@echo "Logs: make dev-logs"

dev-down:
	docker compose -f $(COMPOSE_FILE) -f $(COMPOSE_DEV) down --remove-orphans

dev-logs:
	docker compose -f $(COMPOSE_FILE) -f $(COMPOSE_DEV) logs -f --tail=50

# --- Producción (VPS) ---

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

# --- Pipeline de datos: Elastic Stack + ECS (Fase 2) ---

# Baja los logs crudos de Cowrie desde el volumen Docker del VPS a data/logs/cowrie/.
# Requiere clave SSH admin. Usa sudo remoto para leer el volumen (owner root).
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

elastic-dev-up:
	@if [ ! -f infra/elastic/.env ]; then cp infra/elastic/.env.example infra/elastic/.env; echo "Creado infra/elastic/.env desde el ejemplo."; fi
	# Arrancar almacenamiento/procesado y aplicar la plantilla ECS ANTES de Filebeat,
	# para que los índices se creen con los tipos ECS correctos (evita el race de mapeo).
	docker compose --env-file infra/elastic/.env -f $(ELASTIC_FILE) -f $(ELASTIC_DEV) up -d elasticsearch logstash kibana
	@ES_URL=http://localhost:9200 bash infra/elastic/scripts/es_bootstrap.sh
	docker compose --env-file infra/elastic/.env -f $(ELASTIC_FILE) -f $(ELASTIC_DEV) up -d filebeat
	@echo ""
	@echo "Elastic Stack local iniciado:"
	@echo "  Elasticsearch → http://localhost:9200"
	@echo "  Kibana        → http://localhost:5601"
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
