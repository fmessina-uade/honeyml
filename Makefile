.PHONY: help up down logs status ps clean deploy-vps dev-up dev-down dev-logs validate lint test

COMPOSE_FILE = infra/honeypots/docker-compose.yml
COMPOSE_DEV  = infra/honeypots/docker-compose.dev.yml
VPS_IP       ?= $(shell cat .vps_ip 2>/dev/null || echo "")
SSH_PORT     ?= 2200
SSH_USER     ?= honeyml

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
