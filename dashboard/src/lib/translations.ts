// Full ES/EN copy for the educational panel. Both objects share the exact same shape —
// `Dict` is derived from the Spanish source of truth, so a missing English key is a type error.
//
// What is NOT here: the per-command explanations of the replay. Those come from the API, which
// serves both languages (see honeyml/education/annotations.py).

const es = {
  brand: {
    name: 'HoneyML',
    subtitle: 'Panel educativo',
  },
  footer: {
    live: 'Datos reales capturados',
    frozen: 'Snapshot congelado',
    frozenTitle: 'Snapshot tomado el',
  },
  loading: 'Cargando…',
  error: {
    title: 'No se pudo cargar la telemetría',
    hint: 'Verificá que la API esté corriendo:',
  },
  nav: {
    pulso: 'El pulso',
    anatomia: 'Anatomía de un ataque',
    protocolos: 'Más allá de SSH',
    diccionario: 'Diccionario del atacante',
    huellas: 'Huella de las botnets',
    mitre: 'Tácticas MITRE',
  },
  lead: {
    pulso: 'Un equipo que nadie publicó en ningún lado, expuesto a internet. Esto es lo que recibe.',
    anatomia: 'Una intrusión real capturada, reproducida paso a paso. Cada comando, explicado.',
    protocolos:
      'SSH es la puerta que todos se acuerdan de cerrar. Estas son las otras, y lo que llegó a cada una.',
    diccionario:
      'Qué credenciales prueban y por qué. La evidencia detrás de cada consejo de seguridad.',
    huellas:
      'Miles de sesiones, un puñado de guiones. Lo que queda cuando se agrupan por lo que ejecutan.',
    mitre: 'El marco con el que se clasifica cada acción, iluminado con las capturas propias.',
  },
  pulse: {
    events: 'Eventos capturados',
    addresses: 'Direcciones atacantes',
    logins: 'Intentos de acceso',
    commands: 'Comandos ejecutados',
    perDay: (n: string) => `${n} por día en promedio`,
    inDays: (n: number) => `en ${n} días con captura`,
    gotIn: (n: string) => `${n} lograron entrar`,
    insideDecoy: 'dentro del señuelo',
    peak: (n: string, d: string) => `Pico de ${n} eventos el ${d}.`,
    oneEvery: (n: number) => `Una dirección distinta cada ${n} minutos.`,
    hitRate: (p: string) => `${p}% de los intentos acertó una credencial del señuelo.`,
    perSession: (n: string) => `${n} comandos por sesión que logró entrar.`,
    chartTitle: 'Actividad diaria por sensor',
    chartNote:
      'Las líneas punteadas son interrupciones de captura documentadas, no ausencia de ataques. Pasá el cursor por cualquier día para ver el detalle.',
    noCapture: 'Sin captura. Interrupción documentada, no ausencia de ataques.',
    ofTotal: (p: string) => `${p}% del total capturado`,
    busiest: 'Cuándo atacan',
    busiestNote:
      'Hora del día en que llegan los ataques, en horario universal. La distribución es plana: no hay horario de oficina del otro lado, son procesos automáticos corriendo sin pausa.',
    hour: 'hora',
    ratio: (r: string) => `${r}× entre pico y valle`,
    loginsAtThisHour: 'intentos de acceso en esa hora',
    events_short: 'eventos',
    outages: 'Interrupciones de captura',
    outagesNote:
      'Declaradas y documentadas. Los huecos del gráfico corresponden a estos períodos, no a ausencia de ataques.',
    days: (n: number) => (n === 1 ? '1 día' : `${n} días`),
  },
  replay: {
    speed: 'Velocidad',
    pause: 'Pausar',
    play: 'Reproducir',
    restart: 'Reiniciar',
    accessGranted: (u: string, p: string) => `Acceso concedido con ${u}:${p}`,
    sessionEnded: 'sesión finalizada',
    step: (i: number, n: number) => `Paso ${i} de ${n}`,
    keys: 'espacio pausa · ← → paso a paso',
    goToStep: 'Ir a este paso',
    why: 'Por qué lo hace',
    others: 'Otras sesiones capturadas',
    attackers: (n: number) => `${n} atacantes`,
    cmd: 'cmd',
    empty: 'No hay sesiones con comandos para reproducir.',
    emptyHint: 'Generalas con make replays después de bajar logs frescos.',
    seeInMitre: 'Ver la técnica en MITRE ATT&CK',
    search: 'Buscar atacante, credencial o táctica',
    noMatch: 'Ninguna sesión coincide.',
  },
  protocols: {
    intro1: 'El señuelo no expone solo SSH. Estos son los otros servicios que dejó abiertos, y lo que llegó a cada uno.',
    introStrong: 'Nadie publicó esta dirección:',
    intro2: 'todo lo que ves lo encontró un escáner recorriendo internet.',
    volume: 'volumen',
    reach: 'alcance',
    events: 'eventos',
    sources: 'direcciones',
    port: 'puerto',
    tipEvents: 'eventos capturados',
    tipSources: 'direcciones distintas',
    tipPerSource: 'eventos por dirección',
    tipShare: 'del tráfico multiprotocolo',
    lessonTitle: 'Lo que enseña la comparación',
    lesson:
      'Mirá las dos barras de SMB y las de HTTP. SMB acumula el grueso del volumen desde muy pocas direcciones: es un puñado de gusanos reintentando sin parar contra el mismo puerto. HTTP es al revés, mucho menos tráfico repartido entre muchísimas más direcciones: son escáneres distintos barriendo internet una vez cada uno. El mismo número de eventos significa cosas opuestas según cuántos lo produjeron, y por eso contar alertas no alcanza para priorizarlas.',
  },
  dictionary: {
    usersTitle: 'Usuarios más probados',
    usersHint: 'Los atacantes no adivinan: prueban los nombres que casi siempre existen.',
    passTitle: 'Contraseñas más probadas',
    passHint: 'Todas salen de diccionarios públicos armados con filtraciones reales.',
    unitUsers: 'intentos de acceso con este usuario',
    unitPass: 'veces que se probó esta contraseña',
    empty: '(vacía)',
    ofTop: 'del top 10',
    timesLess: (n: string, k: string) => `${n}× menos que ${k}`,
  },
  mitre: {
    coverageTitle: 'Cobertura del marco',
    coverageNote:
      'De las catorce tácticas de MITRE ATT&CK Enterprise, estas son las que aparecen en las sesiones capturadas. Las ausentes no son un vacío del panel: son etapas que un señuelo de baja interacción no llega a observar.',
    observed: 'observadas',
    notObserved: 'no observadas en este señuelo',
    sessions: 'sesiones observadas',
    session: 'sesión observada',
    techniques: 'técnicas',
    stagesTitle: 'Etapas sobre el total capturado',
    stagesNote:
      'La enorme mayoría del tráfico es reconocimiento y fuerza bruta automatizada. Solo una fracción mínima llega a ejecutar comandos: por eso el triaje importa.',
    stageEvents: 'eventos en esta etapa',
    ofEverything: 'de todo lo capturado',
    techTitle: 'Técnicas observadas',
    techNote: 'Cada técnica es un identificador del catálogo de MITRE ATT&CK. Hacé clic para ver la ficha oficial.',
    steps: 'pasos',
    whyNotSeen: 'Por qué no aparece',
  },
  tactics: {
    Descubrimiento: {
      name: 'Descubrimiento',
      meaning:
        'El atacante averigua dónde entró: qué sistema es, qué permisos tiene, qué hay instalado.',
    },
    Ejecución: {
      name: 'Ejecución',
      meaning: 'Corre código propio en el equipo, normalmente después de descargarlo.',
    },
    Persistencia: {
      name: 'Persistencia',
      meaning: 'Se asegura de seguir dentro aunque se reinicie el equipo o se cambie la clave.',
    },
    'Evasión de defensas': {
      name: 'Evasión de defensas',
      meaning: 'Borra rastros y evita las herramientas que podrían detectarlo.',
    },
    'Acceso a credenciales': {
      name: 'Acceso a credenciales',
      meaning: 'Roba usuarios y contraseñas para moverse a otros sistemas.',
    },
    'Movimiento lateral': {
      name: 'Movimiento lateral',
      meaning: 'Salta desde el equipo comprometido hacia otros de la misma red.',
    },
    Impacto: {
      name: 'Impacto',
      meaning: 'Destruye, cifra o interrumpe. Es el objetivo final de un ataque destructivo.',
    },
  },
  notObservedWhy: {
    'Acceso a credenciales':
      'El señuelo no guarda credenciales reales que robar: no hay archivos de contraseñas ni sesiones de otros usuarios.',
    'Movimiento lateral':
      'El sensor está aislado en su propia red, sin equipos vecinos a los que saltar. El bloqueo de tráfico saliente lo impide además a nivel de red.',
    Impacto:
      'Requiere una permanencia que la emulación no sostiene: el atacante abandona antes de llegar a esta etapa.',
  },
  passcheck: {
    title: '¿Tu contraseña está acá?',
    intro:
      'Comparala contra las 53.580 contraseñas distintas que los atacantes probaron realmente contra este señuelo. No se envía a ningún lado.',
    placeholder: 'Escribí una contraseña',
    button: 'Comparar',
    failed: 'No se pudo consultar el índice. Generalo con make passwords.',
    foundTitle: 'Está en la lista.',
    foundBody: (c: string) =>
      `Se probó ${c} veces contra este equipo. Si la usás en algún lado, cambiala: no hace falta que nadie te apunte, los bots la prueban por defecto.`,
    safeTitle: 'No aparece en las capturas.',
    safeBody:
      'Que no esté acá no la vuelve segura: este es un señuelo, no un catálogo completo. Significa que no está entre las que se probaron en estos setenta y seis días.',
    privacy:
      'Cómo funciona: el navegador calcula el hash SHA-256 de lo que escribís y envía solo los primeros cinco caracteres. El servicio responde con todos los hashes capturados que empiezan igual, y la comparación termina acá. La contraseña nunca sale de tu equipo, y el servicio no puede saber cuál preguntaste.',
  },
  fingerprints: {
    sessionsLabel: 'Sesiones con comandos',
    withCommands: 'donde el atacante llegó a ejecutar algo',
    familiesLabel: 'Familias distintas',
    identical: 'con secuencia de comandos idéntica',
    coverageLabel: 'Agrupadas',
    grouped: (c: string) => `${c} sesiones dentro de una familia`,
    sessions: 'sesiones',
    sources: 'direcciones',
    perSource: (r: string) => `${r} sesiones por dirección: la misma máquina repitiendo el guion`,
    script: 'El guion exacto',
    truncated: (n: number) => `… y ${n - 12} comandos más`,
    lesson:
      'Casi todas las sesiones capturadas no son ataques distintos: son el mismo guion ejecutado por muchas máquinas. Agrupar por secuencia exacta de comandos lo hace evidente, y de paso muestra por qué contar alertas no sirve para medir amenazas. Una familia con miles de sesiones desde un puñado de direcciones no son miles de atacantes: es un programa, repetido.',
  },
  capture: {
    on: 'Modo captura',
    off: 'Modo captura',
    hint: 'Congela las animaciones para que las capturas de pantalla salgan reproducibles.',
  },
  sensors: {
    cowrie: 'acceso remoto',
    dionaea: 'servicios de red',
  },
};

const en: typeof es = {
  brand: {
    name: 'HoneyML',
    subtitle: 'Educational panel',
  },
  footer: {
    live: 'Real captured data',
    frozen: 'Frozen snapshot',
    frozenTitle: 'Snapshot taken on',
  },
  loading: 'Loading…',
  error: {
    title: 'Could not load telemetry',
    hint: 'Check that the API is running:',
  },
  nav: {
    pulso: 'The pulse',
    anatomia: 'Anatomy of an attack',
    protocolos: 'Beyond SSH',
    diccionario: "The attacker's dictionary",
    huellas: 'Botnet fingerprints',
    mitre: 'MITRE tactics',
  },
  lead: {
    pulso: 'A machine nobody advertised anywhere, exposed to the internet. This is what it gets.',
    anatomia: 'A real captured intrusion, replayed step by step. Every command, explained.',
    protocolos:
      'SSH is the door everyone remembers to lock. These are the others, and what reached each one.',
    diccionario:
      'Which credentials they try, and why. The evidence behind every security recommendation.',
    huellas:
      'Thousands of sessions, a handful of scripts. What is left when you group them by what they run.',
    mitre: 'The framework used to classify each action, lit up with our own captures.',
  },
  pulse: {
    events: 'Captured events',
    addresses: 'Attacking addresses',
    logins: 'Access attempts',
    commands: 'Commands executed',
    perDay: (n: string) => `${n} per day on average`,
    inDays: (n: number) => `across ${n} days of capture`,
    gotIn: (n: string) => `${n} got in`,
    insideDecoy: 'inside the decoy',
    peak: (n: string, d: string) => `Peak of ${n} events on ${d}.`,
    oneEvery: (n: number) => `A distinct address every ${n} minutes.`,
    hitRate: (p: string) => `${p}% of attempts hit a decoy credential.`,
    perSession: (n: string) => `${n} commands per session that got in.`,
    chartTitle: 'Daily activity by sensor',
    chartNote:
      'Dashed lines are documented capture outages, not an absence of attacks. Hover over any day for the detail.',
    noCapture: 'No capture. Documented outage, not an absence of attacks.',
    ofTotal: (p: string) => `${p}% of everything captured`,
    busiest: 'When they attack',
    busiestNote:
      'Hour of day when attacks arrive, in universal time. The distribution is flat: there are no office hours on the other side, these are automated processes running non-stop.',
    hour: 'hour',
    ratio: (r: string) => `${r}× between peak and trough`,
    loginsAtThisHour: 'access attempts in that hour',
    events_short: 'events',
    outages: 'Capture outages',
    outagesNote:
      'Declared and documented. The gaps in the chart correspond to these periods, not to an absence of attacks.',
    days: (n: number) => (n === 1 ? '1 day' : `${n} days`),
  },
  replay: {
    speed: 'Speed',
    pause: 'Pause',
    play: 'Play',
    restart: 'Restart',
    accessGranted: (u: string, p: string) => `Access granted with ${u}:${p}`,
    sessionEnded: 'session ended',
    step: (i: number, n: number) => `Step ${i} of ${n}`,
    keys: 'space pauses · ← → step by step',
    goToStep: 'Jump to this step',
    why: 'Why they do it',
    others: 'Other captured sessions',
    attackers: (n: number) => `${n} attackers`,
    cmd: 'cmd',
    empty: 'No sessions with commands to replay.',
    emptyHint: 'Generate them with make replays after pulling fresh logs.',
    seeInMitre: 'View this technique on MITRE ATT&CK',
    search: 'Search attacker, credential or tactic',
    noMatch: 'No session matches.',
  },
  protocols: {
    intro1: 'The decoy does not only expose SSH. These are the other services it left open, and what reached each one.',
    introStrong: 'Nobody published this address:',
    intro2: 'everything you see was found by a scanner sweeping the internet.',
    volume: 'volume',
    reach: 'reach',
    events: 'events',
    sources: 'addresses',
    port: 'port',
    tipEvents: 'captured events',
    tipSources: 'distinct addresses',
    tipPerSource: 'events per address',
    tipShare: 'of multiprotocol traffic',
    lessonTitle: 'What the comparison teaches',
    lesson:
      'Look at the two bars for SMB and those for HTTP. SMB piles up the bulk of the volume from very few addresses: a handful of worms retrying endlessly against the same port. HTTP is the reverse, far less traffic spread across many more addresses: distinct scanners sweeping the internet once each. The same event count means opposite things depending on how many sources produced it, and that is why counting alerts is not enough to prioritise them.',
  },
  dictionary: {
    usersTitle: 'Most attempted usernames',
    usersHint: 'Attackers do not guess: they try the names that almost always exist.',
    passTitle: 'Most attempted passwords',
    passHint: 'They all come from public dictionaries built from real breaches.',
    unitUsers: 'access attempts with this username',
    unitPass: 'times this password was tried',
    empty: '(empty)',
    ofTop: 'of the top 10',
    timesLess: (n: string, k: string) => `${n}× fewer than ${k}`,
  },
  mitre: {
    coverageTitle: 'Framework coverage',
    coverageNote:
      'Of the fourteen MITRE ATT&CK Enterprise tactics, these are the ones that appear in the captured sessions. The missing ones are not a gap in the panel: they are stages a low-interaction decoy never gets to observe.',
    observed: 'observed',
    notObserved: 'not observed in this decoy',
    sessions: 'sessions observed',
    session: 'session observed',
    techniques: 'techniques',
    stagesTitle: 'Stages over everything captured',
    stagesNote:
      'The vast majority of traffic is reconnaissance and automated brute force. Only a tiny fraction gets as far as executing commands: that is why triage matters.',
    stageEvents: 'events at this stage',
    ofEverything: 'of everything captured',
    techTitle: 'Observed techniques',
    techNote: 'Each technique is an identifier from the MITRE ATT&CK catalogue. Click to open the official entry.',
    steps: 'steps',
    whyNotSeen: 'Why it does not appear',
  },
  tactics: {
    Descubrimiento: {
      name: 'Discovery',
      meaning:
        'The attacker works out where they landed: what system it is, what permissions they have, what is installed.',
    },
    Ejecución: {
      name: 'Execution',
      meaning: 'Runs their own code on the machine, usually after downloading it.',
    },
    Persistencia: {
      name: 'Persistence',
      meaning: 'Makes sure they stay in even if the machine reboots or the password changes.',
    },
    'Evasión de defensas': {
      name: 'Defense Evasion',
      meaning: 'Wipes traces and avoids the tools that might detect them.',
    },
    'Acceso a credenciales': {
      name: 'Credential Access',
      meaning: 'Steals usernames and passwords to move on to other systems.',
    },
    'Movimiento lateral': {
      name: 'Lateral Movement',
      meaning: 'Jumps from the compromised machine to others on the same network.',
    },
    Impacto: {
      name: 'Impact',
      meaning: 'Destroys, encrypts or disrupts. The end goal of a destructive attack.',
    },
  },
  notObservedWhy: {
    'Acceso a credenciales':
      'The decoy holds no real credentials to steal: there are no password files and no other users’ sessions.',
    'Movimiento lateral':
      'The sensor is isolated on its own network, with no neighbouring machines to jump to. Outbound traffic blocking prevents it at the network layer as well.',
    Impacto:
      'It requires a persistence the emulation does not sustain: the attacker leaves before reaching this stage.',
  },
  passcheck: {
    title: 'Is your password in here?',
    intro:
      'Compare it against the 53,580 distinct passwords attackers actually tried against this decoy. It is never sent anywhere.',
    placeholder: 'Type a password',
    button: 'Compare',
    failed: 'Could not query the index. Generate it with make passwords.',
    foundTitle: 'It is on the list.',
    foundBody: (c: string) =>
      `It was tried ${c} times against this machine. If you use it anywhere, change it: nobody has to target you, the bots try it by default.`,
    safeTitle: 'It does not appear in the captures.',
    safeBody:
      'Not being here does not make it safe: this is one decoy, not a complete catalogue. It means it is not among those tried during these seventy-six days.',
    privacy:
      'How it works: the browser computes the SHA-256 hash of what you type and sends only the first five characters. The service replies with every captured hash starting the same way, and the comparison finishes here. The password never leaves your machine, and the service cannot tell which one you asked about.',
  },
  fingerprints: {
    sessionsLabel: 'Sessions with commands',
    withCommands: 'where the attacker got to run something',
    familiesLabel: 'Distinct families',
    identical: 'with an identical command sequence',
    coverageLabel: 'Grouped',
    grouped: (c: string) => `${c} sessions inside a family`,
    sessions: 'sessions',
    sources: 'addresses',
    perSource: (r: string) => `${r} sessions per address: the same machine repeating the script`,
    script: 'The exact script',
    truncated: (n: number) => `… and ${n - 12} more commands`,
    lesson:
      'Almost every captured session is not a distinct attack: it is the same script run by many machines. Grouping by exact command sequence makes that obvious, and shows why counting alerts does not measure threat. A family with thousands of sessions from a handful of addresses is not thousands of attackers: it is one program, repeated.',
  },
  capture: {
    on: 'Capture mode',
    off: 'Capture mode',
    hint: 'Freezes animations so screenshots come out reproducible.',
  },
  sensors: {
    cowrie: 'remote access',
    dionaea: 'network services',
  },
};

export type Lang = 'es' | 'en';
export type Dict = typeof es;

export const TRANSLATIONS: Record<Lang, Dict> = { es, en };
