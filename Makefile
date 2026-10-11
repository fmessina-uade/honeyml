.PHONY: help up down logs status ps clean deploy-vps dev-up dev-down dev-logs validate lint test \
        test-integration consumer triaje retriaje grafo arquetipos uwf-verificar modelo evaluacion comparacion clasificar muestra tasa procedencia \
        api dash demo replays \
        elastic-up elastic-down elastic-logs elastic-dev-up elastic-dev-down elastic-dev-logs \
        es-bootstrap validate-indexing pull-logs \
        analisis-up analisis-down analisis-logs publicar-artefactos tunel \
        respaldar-decisiones

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
	@echo "    make elastic-dev-up   Levantar Elasticsearch, Logstash y Filebeat en local"
	@echo "    make elastic-dev-down Detener el stack local"
	@echo "    make es-bootstrap     Aplicar plantilla componible ECS a Elasticsearch"
	@echo "    make validate-indexing  Validar indexación y normalización ECS"
	@echo "    make elastic-up       Levantar el stack en el VPS (producción)"
	@echo ""
	@echo "  Clasificador supervisado (conjunto de referencia UWF-ZeekData24):"
	@echo "    make uwf-verificar  Comparar la copia local con la de referencia"
	@echo "    make modelo      Reentrenar y exportar el modelo final con su tarjeta"
	@echo "    make evaluacion  Las cuatro mediciones del modelo"
	@echo "    make comparacion Las cuatro familias comparadas"
	@echo "    make clasificar  Demostración sobre flujos de prueba no vistos"
	@echo ""
	@echo "  Panel educativo (demo):"
	@echo "    make replays   Extraer sesiones de ataque anotadas"
	@echo "    make api       Levantar la API (FastAPI, puerto 8000)"
	@echo "    make dash      Levantar el panel (Vite, puerto 5173)"
	@echo "    make demo      Publicar el panel en la red local para los teléfonos (con make tunel)"
	@echo ""
	@echo "  Producción (VPS):"
	@echo "    make up        Iniciar contenedores en el VPS (puertos reales)"
	@echo "    make down      Detener contenedores"
	@echo "    make logs      Ver logs en tiempo real"
	@echo "    make ps        Estado de contenedores"
	@echo "    make status    Resumen de estado del sistema"
	@echo "    make deploy-vps  Llevar el último commit al VPS (SECO=1 muestra qué cambiaría)"
	@echo "    make analisis-up Levantar el motor de triaje y la API en contenedores"
	@echo "    make muestra     Muestra para la revisión a ciegas (en el servidor)"
	@echo "    make tasa        Falsos positivos y negativos, auditados a ciegas (en el servidor)"
	@echo "    make procedencia De dónde viene cada evento del corpus (en el servidor)"
	@echo "    make publicar-artefactos  Subir los artefactos derivados al VPS"
	@echo "    make tunel     La API del VPS en esta máquina, por túnel SSH"
	@echo "    make respaldar-decisiones  Traer los volcados de decisiones del VPS"
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
		yamllint infra/honeypots/docker-compose.yml infra/honeypots/docker-compose.dev.yml \
			infra/analisis/docker-compose.yml && echo "  yamllint OK"; \
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

# Lleva al servidor el último commit. El servidor no guarda credenciales de GitHub: la máquina que
# recibe ataques no tiene con qué leer el repositorio. Se despliega lo commiteado y nada más, así lo
# que corre allá siempre corresponde a un commit. --delete saca lo que ya no está en el repositorio,
# salvo lo que solo existe en el servidor: las claves en los .env y los artefactos de data/.
deploy-vps:
ifndef VPS_IP
	$(error VPS_IP no definido. Crear archivo .vps_ip o exportar: export VPS_IP=<ip>)
endif
	@if [ -n "$$(git status --porcelain)" ]; then \
		echo "Aviso: hay cambios sin commitear, y no se despliegan."; \
	fi
	@# mktemp crea el directorio con 700, y rsync le copiaría ese permiso a la raíz del repositorio en
	@# el servidor: el usuario de administración dejaría de poder leerlo.
	@tmp=$$(mktemp -d) && trap 'rm -rf "$$tmp"' EXIT && chmod 755 "$$tmp" && \
		git archive HEAD | tar -x -C "$$tmp" && \
		rsync -rlptz --delete $(if $(SECO),--dry-run --itemize-changes,) \
			--exclude='/.env' --exclude='/data/' --exclude='/infra/*/.env' \
			--rsync-path="sudo rsync" \
			-e "ssh -p $(SSH_PORT) -i $(SSH_KEY) -o IdentitiesOnly=yes" \
			"$$tmp/" $(SSH_USER)@$(VPS_IP):/opt/honeyml/honeyml/ && \
		echo "$(if $(SECO),Simulado,Desplegado) $$(git rev-parse --short HEAD) en /opt/honeyml/honeyml"
	@# Cada despliegue queda en un registro del servidor que lee la auditoría del panel. La línea
	@# viaja por la entrada estándar y no como argumento: así el asunto del commit nunca llega a la
	@# línea de comandos del servidor.
	@$(if $(SECO),true,printf '[%s] Desplegado %s por %s: %s\n' \
		"$$(date -u '+%Y-%m-%d %H:%M:%S')" "$$(git rev-parse --short HEAD)" \
		"$$(git config user.name)" "$$(git log -1 --format=%s)" \
		| ssh -p $(SSH_PORT) -i $(SSH_KEY) -o IdentitiesOnly=yes $(SSH_USER)@$(VPS_IP) \
			"sudo tee -a /var/log/honeyml_despliegues.log >/dev/null")

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
	# Se levantan almacenamiento y procesamiento, y se aplica la plantilla ECS antes que Filebeat,
	# así los índices salen con los tipos ECS correctos y no hay carrera con el mapeo.
	docker compose --env-file infra/elastic/.env -f $(ELASTIC_FILE) -f $(ELASTIC_DEV) up -d elasticsearch logstash
	@ES_URL=http://localhost:9200 bash infra/elastic/scripts/es_bootstrap.sh
	docker compose --env-file infra/elastic/.env -f $(ELASTIC_FILE) -f $(ELASTIC_DEV) up -d filebeat
	@echo ""
	@echo "Elastic Stack local iniciado:"
	@echo "  Elasticsearch -> http://localhost:9200"
	@echo ""
	@echo "Siguiente: make validate-indexing"

elastic-dev-down:
	docker compose -f $(ELASTIC_FILE) -f $(ELASTIC_DEV) down --remove-orphans

elastic-dev-logs:
	docker compose -f $(ELASTIC_FILE) -f $(ELASTIC_DEV) logs -f --tail=80

elastic-up:
	@if [ ! -f infra/elastic/.env ]; then cp infra/elastic/.env.example infra/elastic/.env; fi
	@# El orden importa. La plantilla ECS va antes que Filebeat, así los índices salen con los tipos
	@# correctos. Y el bus va antes que Logstash: un evento que no se logra publicar se indexa igual,
	@# marcado con _bus_publish_failed, pero el motor no lo recibe nunca.
	docker compose --env-file infra/elastic/.env -f $(ELASTIC_FILE) up -d elasticsearch
	@ES_URL=http://localhost:9200 bash infra/elastic/scripts/es_bootstrap.sh
	@$(MAKE) --no-print-directory bus-up
	docker compose --env-file infra/elastic/.env -f $(ELASTIC_FILE) up -d logstash
	docker compose --env-file infra/elastic/.env -f $(ELASTIC_FILE) up -d filebeat
	@echo "Elastic Stack iniciado en el servidor. Acceso privado desde la estación: make tunel"

elastic-down:
	docker compose -f $(ELASTIC_FILE) down

elastic-logs:
	docker compose -f $(ELASTIC_FILE) logs -f --tail=100

es-bootstrap:
	@ES_URL=$${ES_URL:-http://localhost:9200} bash infra/elastic/scripts/es_bootstrap.sh

validate-indexing:
	@python3 infra/elastic/scripts/validate_indexing.py --es-url $${ES_URL:-http://localhost:9200}

# salida compacta para capturas de pantalla: sin lista de índices por día, direcciones ni usuarios.
# Con HASTA cuenta solo hasta ese instante, para reproducir un corte de cifras.
#   make validate-indexing-resumen HASTA=2026-10-03T22:00:59Z
validate-indexing-resumen:
	@python3 infra/elastic/scripts/validate_indexing.py --es-url $${ES_URL:-http://localhost:9200} --resumen $(if $(HASTA),--hasta $(HASTA),)

# panel educativo: API + SPA. Se corren `make api` y `make dash` en dos terminales.

BUS_FILE     = infra/valkey/docker-compose.yml

# Bus de eventos, sobre los streams de Valkey. Vive en la zona de análisis y se une a elastic_net,
# así que el stack tiene que estar arriba antes: la red se crea ahí.
bus-up:
	@if [ ! -f infra/valkey/.env ]; then cp infra/valkey/.env.example infra/valkey/.env; echo "Creado infra/valkey/.env desde el ejemplo."; fi
	docker compose --env-file infra/valkey/.env -f $(BUS_FILE) up -d
	@echo ""
	@echo "Bus de eventos disponible en 127.0.0.1:6379"

bus-down:
	docker compose --env-file infra/valkey/.env -f $(BUS_FILE) down

bus-status:
	@./.venv/bin/python scripts/bus_status.py

ANALISIS_FILE = infra/analisis/docker-compose.yml

# Motor de triaje y API del panel en contenedores, sobre la red de análisis. Es como corren en el
# servidor; en la estación de trabajo siguen estando `make triaje` y `make api`.
analisis-up:
	docker compose -f $(ANALISIS_FILE) up -d --build

analisis-down:
	docker compose -f $(ANALISIS_FILE) down

analisis-logs:
	docker compose -f $(ANALISIS_FILE) logs -f --tail=100

# El motor y la API del servidor leen los artefactos derivados (familias de comandos, arquetipos,
# replays, índice de contraseñas) de solo lectura. Se generan acá con `make artifacts` y se publican.
publicar-artefactos:
ifndef VPS_IP
	$(error VPS_IP no definido. Crear archivo .vps_ip o exportar: export VPS_IP=<ip>)
endif
	rsync -rlptvz --include='*.json' --exclude='*' \
		--rsync-path="sudo mkdir -p /opt/honeyml/honeyml/data/processed && sudo rsync" \
		-e "ssh -p $(SSH_PORT) -i $(SSH_KEY) -o IdentitiesOnly=yes" \
		data/processed/ $(SSH_USER)@$(VPS_IP):/opt/honeyml/honeyml/data/processed/

# La API del servidor en esta máquina. Usa el mismo puerto que la API local, así que va con esa
# apagada.
tunel:
ifndef VPS_IP
	$(error VPS_IP no definido. Crear archivo .vps_ip o exportar: export VPS_IP=<ip>)
endif
	@echo "La API en http://localhost:8000. Ctrl+C para cerrar."
	@ssh -N -L 8000:127.0.0.1:8000 \
		-p $(SSH_PORT) -i $(SSH_KEY) -o IdentitiesOnly=yes $(SSH_USER)@$(VPS_IP)

# Saca del servidor los volcados diarios de decisiones y de veredictos del analista. El respaldo del
# servidor vive en el mismo disco que los produce, así que por sí solo no protege de perder la
# máquina. Cada decisión costó una llamada paga y cada veredicto es trabajo de una persona; los
# eventos, en cambio, se reingieren desde los registros crudos.
respaldar-decisiones:
ifndef VPS_IP
	$(error VPS_IP no definido. Crear archivo .vps_ip o exportar: export VPS_IP=<ip>)
endif
	@mkdir -p data/respaldos/decisiones
	rsync -rlptvz --rsync-path="sudo rsync" \
		-e "ssh -p $(SSH_PORT) -i $(SSH_KEY) -o IdentitiesOnly=yes" \
		$(SSH_USER)@$(VPS_IP):/home/$(SSH_USER)/backups/decisiones/ data/respaldos/decisiones/
	@echo "Volcados en data/respaldos/decisiones/"

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
# eventos y no se pidió un límite, no arranca: un reprocesamiento histórico de decenas de miles de
# mensajes cuesta decenas de dólares de inferencia, y eso no se gasta sin pedirlo.
#
# Con REUTILIZAR=1 copia la decisión cuando otro evento ya resolvió la misma conducta (mismo sensor,
# categoría, acción, resultado, protocolo, usuario y comando). Las conductas distintas son muchas
# menos que los eventos, así que la gran mayoría se resuelve sin pagar una llamada. Cada documento
# dice de qué decisión copió, así que la reutilización es auditable y no un atajo.
#
# Una decisión ya guardada no se pisa nunca: si el evento vuelve a llegar, se confirma y se cuenta
# como repetido. Con REESCRIBIR=1 se sobrescribe, para triar otra vez a propósito; no se combina
# con REUTILIZAR, que copiaría justamente las decisiones que se quieren rehacer.
#   make triaje LIMITE=5                prueba con cinco eventos
#   make triaje LIMITE=200 REUTILIZAR=1 pone a prueba la reutilización sobre una tanda
#   make triaje TODO=1 REUTILIZAR=1     tría el atraso completo
#   make triaje LIMITE=20 REESCRIBIR=1  vuelve a decidir veinte eventos, pisando lo guardado
triaje:
	@./.venv/bin/python -m honeyml.agent.motor $(if $(LIMITE),--limite $(LIMITE),) $(if $(TODO),--todo,) $(if $(REUTILIZAR),--reutilizar,) $(if $(REESCRIBIR),--reescribir,)

# Vuelve a triar los eventos de una categoría cuando cambió lo que el motor puede decir de ellos,
# por ejemplo al sumar una táctica. Olvida sus firmas del repertorio y sobrescribe lo guardado, así
# que conviene correrlo después del respaldo del día. SECO=1 solo cuenta y estima el gasto. En el
# servidor corre dentro del contenedor del motor:
#   sudo docker exec motor python -m honeyml.agent.retriaje --categoria authentication
#   make retriaje CATEGORIA=authentication SECO=1
retriaje:
	@./.venv/bin/python -m honeyml.agent.retriaje --categoria $(CATEGORIA) $(if $(SECO),--seco,)

# Topología del motor de triaje y qué nodo tiene implementación.
grafo:
	@./.venv/bin/python -m honeyml.agent.graph

# La escala de severidad tal como se le publica al proveedor de inferencia.
severidad:
	@./.venv/bin/python -m honeyml.agent.severidad

# Antes de reentrenar: dice si la copia local de UWF-ZeekData24 es la misma con la que se entrenó el
# modelo informado, semana por semana.
uwf-verificar:
	@./.venv/bin/python -m honeyml.eda.uwf_loader --verificar

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

# La muestra estratificada por conducta para la revisión a ciegas del motor. Corre en el servidor,
# que es donde está el índice, en un contenedor de una sola vez con la imagen de análisis: la API
# monta los artefactos de solo lectura y no puede escribirla. El nombre y la etiqueta avisan que no
# se toca mientras corre.
#   sudo make muestra SECO=1      los estratos, sin escribir
#   sudo make muestra             arma la muestra; se niega a pisar una existente
#   sudo make muestra REEMPLAZAR=1
muestra:
	@docker run --rm --name honeyml-muestra-no-modificar --label honeyml.aviso="no modificar" \
		--network host --memory 1g --user 0 -e ES_URL=http://127.0.0.1:9200 \
		-v $(CURDIR)/data/processed:/app/data/processed honeyml-analisis \
		python -m honeyml.medicion.muestra $(if $(SECO),--seco,) $(if $(REEMPLAZAR),--reemplazar,)

# Las tasas de falsos positivos y negativos del motor, con la regla de referencia y con la revisión
# a ciegas del analista, estrato por estrato. Solo lee la muestra y las revisiones.
#   sudo make tasa
tasa:
	@docker run --rm --name honeyml-tasa-no-modificar --label honeyml.aviso="no modificar" \
		--network host --memory 512m --user 0 -e ES_URL=http://127.0.0.1:9200 \
		-v $(CURDIR)/data/processed:/app/data/processed:ro honeyml-analisis \
		python -m honeyml.medicion.tasa

# De dónde viene cada evento del corpus: direcciones públicas, loopback, redes privadas o ninguna,
# con el conjunto de datos y los días de cada grupo. Solo lee y no imprime direcciones. Corre en el
# servidor, igual que la muestra.
#   sudo make procedencia
procedencia:
	@docker run --rm --name honeyml-procedencia-no-modificar --label honeyml.aviso="no modificar" \
		--network host --memory 256m -e ES_URL=http://127.0.0.1:9200 honeyml-analisis \
		python -m honeyml.medicion.procedencia

# La comparación de las cuatro familias de modelos, ordenada por F1 macro. Imprime la última
# guardada; con REENTRENAR=1 vuelve a entrenarlas, que tarda unos seis minutos y la reescribe.
#   make comparacion               make comparacion REENTRENAR=1
comparacion:
	@./.venv/bin/python -m honeyml.features.uwf_comparison $(if $(REENTRENAR),,--mostrar)

# Demostración del clasificador: flujos de prueba que el modelo no vio, táctica real contra
# predicha, y el F1 macro recalculado en el momento contra el de la tarjeta. Usa el modelo que
# exportó `make modelo`, sin reentrenar.
#   make clasificar                        dos flujos por clase y un error real
#   make clasificar POR_CLASE=4 SEMILLA=7  otra muestra
#   make clasificar MATRIZ=1               suma la matriz de confusión con el umbral
clasificar:
	@./.venv/bin/python -m honeyml.features.uwf_clasificar $(if $(POR_CLASE),--por-clase $(POR_CLASE),) $(if $(SEMILLA),--semilla $(SEMILLA),) $(if $(MATRIZ),--matriz,)

# Un solo comando para todo el ciclo de datos: bajar registros frescos de los sensores, esperar a
# que el pipeline los ingiera, y regenerar todos los artefactos derivados. Reemplaza correr cinco
# objetivos a mano.
#
# No levanta el stack: primero hay que correr `make elastic-dev-up`. Mantenerlos separados hace que
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

# El panel para una demostración con teléfonos: lo compila y lo publica en la red local, con /api
# reenviado al túnel. Necesita `make tunel` corriendo en otra terminal. El porqué de cada cosa
# está en dashboard/demo.mjs.
demo:
	@cd dashboard && npm run build && node demo.mjs

# Comprobación en vivo del proveedor de inferencia. Necesita la clave en .env o en el entorno.
inferencia-ok:
	@./.venv/bin/python -c "import sys; from honeyml.agent.adapters.servicio import comprobar; sys.exit(comprobar())"
