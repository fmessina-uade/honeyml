// Todos los textos ES/EN del panel educativo. Los dos objetos tienen exactamente la misma forma:
// `Dict` se deriva del español, que es la fuente de verdad, así que una clave que falte en inglés
// es un error de tipos.
//
// Lo que no está acá: las explicaciones por comando del replay. Esas vienen de la API, que sirve
// los dos idiomas (ver honeyml/education/annotations.py).

const es = {
  brand: {
    name: 'HoneyML',
    subtitle: 'Panel educativo',
  },
  footer: {
    live: 'Datos reales capturados',
    frozen: 'Snapshot congelado',
    frozenTitle: 'Snapshot tomado el',
    range: (desde: string, hasta: string) => `${desde} al ${hasta}`,
  },
  loading: 'Cargando...',
  error: {
    title: 'No se pudo cargar la telemetría',
    hint: 'Verificá que la API esté corriendo:',
  },
  navGroups: {
    operacion: 'Operación',
    aprender: 'Aprender',
  },
  menu: {
    open: 'Abrir el menú',
    close: 'Cerrar el menú',
  },
  theme: {
    title: 'Tema',
    sistema: 'Como el sistema',
    claro: 'Claro',
    oscuro: 'Oscuro',
  },
  nav: {
    inicio: 'Resumen',
    pulso: 'El pulso',
    anatomia: 'Anatomía de un ataque',
    protocolos: 'Más allá de SSH',
    diccionario: 'Diccionario del atacante',
    huellas: 'Huella de las botnets',
    arquetipos: 'Tipos de atacante',
    origen: 'De dónde vienen',
    mitre: 'Tácticas MITRE',
    triaje: 'Triaje del motor',
  },
  lead: {
    inicio:
      'Todo HoneyML en una pantalla: lo que llega al señuelo, lo que decide el motor y por dónde seguir.',
    pulso:
      'Un equipo que nadie publicó en ningún lado, expuesto a internet. Esto es lo que recibe.',
    anatomia: 'Una intrusión real capturada, reproducida paso a paso. Cada comando, explicado.',
    protocolos:
      'SSH es la puerta que todos se acuerdan de cerrar. Estas son las otras, y lo que llegó a cada una.',
    diccionario:
      'Qué credenciales prueban y por qué. La evidencia detrás de cada consejo de seguridad.',
    huellas:
      'Miles de sesiones, un puñado de guiones. Lo que queda cuando se agrupan por lo que ejecutan.',
    arquetipos:
      'Casi ninguno de los que golpean la puerta llega a entrar. Estos son los que sí, y en qué se distinguen.',
    origen: 'El país dice poco por sí solo. La red que opera la dirección dice bastante más.',
    mitre: 'El marco con el que se clasifica cada acción, iluminado con las capturas propias.',
    triaje:
      'Lo que el motor decidió sobre cada evento, con qué evidencia y a qué costo. Lo que no pudo cerrar solo lo termina de decidir quien opera el panel.',
  },
  home: {
    engineTitle: 'Motor de triaje',
    lastHour: 'decisiones en la última hora',
    toDecision: 'del evento a la decisión',
    pending: 'esperan al analista',
    engineLine: (total: string, copiadas: string, costo: string) =>
      `${total} decisiones sobre tráfico real. El ${copiadas}% se resolvió copiando una decisión anterior sobre la misma conducta, sin consultar al modelo. Costo total: USD ${costo}.`,
    openEngine: 'Ver el motor trabajando',
    distinctOrigins: 'orígenes distintos, ninguno invitado',
    learnTitle: 'Para entender qué pasa',
    learnHint: 'Cada tarjeta lleva a su sección.',
    cards: {
      pulso: (dias: number) => `eventos en ${dias} días de captura`,
      anatomia: 'intrusiones reales, reproducidas comando por comando',
      protocolos: (servicio: string) =>
        `eventos por dirección en ${servicio}: pocas máquinas insistiendo`,
      diccionario: (usuario: string) => `intentos con el usuario ${usuario}`,
      huellas: 'de las sesiones con comandos es un solo guion',
      arquetipos: 'de las direcciones llega a una intrusión efectiva',
      origen: (pais: string) => `eventos por dirección desde ${pais}`,
      mitre: 'tácticas del marco que el señuelo puede observar',
    },
  },
  pulse: {
    notePeak: (eventos: string, fecha: string) => `el pico: ${eventos} eventos el ${fecha}`,
    noteFlat: (veces: string) =>
      `casi plana: el pico es ${veces} veces el valle. Del otro lado no duerme nadie.`,
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
    ratio: (r: string) => `${r} veces entre pico y valle`,
    loginsAtThisHour: 'intentos de acceso en esa hora',
    events_short: 'eventos',
    outages: 'Interrupciones de captura',
    noOutages: 'Sin interrupciones de captura en el período seleccionado',
    noOutagesNote:
      'Los sensores registraron actividad todos los días del rango elegido. Las interrupciones, cuando ocurren, se detectan como días sin ningún evento y casi siempre corresponden a un cuelgue del sensor y no a una pausa de los atacantes.',
    outagesNote:
      'Declaradas y documentadas. Los huecos del gráfico corresponden a estos períodos, no a ausencia de ataques.',
    days: (n: number) => (n === 1 ? '1 día' : `${n} días`),
    filtered: 'filtrado',
    filterFailed: 'No se pudo aplicar el filtro. El gráfico muestra el período completo.',
  },
  replay: {
    speed: 'Velocidad',
    pause: 'Pausar',
    play: 'Reproducir',
    restart: 'Reiniciar',
    accessGranted: (u: string, p: string) => `Acceso concedido con ${u}:${p}`,
    sessionEnded: 'sesión finalizada',
    step: (i: number, n: number) => `Paso ${i} de ${n}`,
    keys: 'espacio pausa, las flechas avanzan o retroceden de a un paso',
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
    phase: 'Fase del ataque',
    turn: (paso: number, que: string) => `paso ${paso}: ${que}`,
    turnWhat: {
      Persistencia: 'acá se asegura de poder volver',
      'Evasión de defensas': 'acá borra sus rastros',
      Ejecución: 'acá corre su propio código',
      Descubrimiento: 'acá mira dónde cayó',
    } as Record<string, string>,
  },
  protocols: {
    contrastTitle: 'Mismo sensor, lecturas opuestas',
    perSourceLabel: 'eventos por dirección',
    sourcesShort: 'direcciones',
    gap: 'de diferencia',
    contrastNote:
      'Contar eventos alcanza para saber cuánto ruido hay, no de qué tipo. Un servicio golpeado muchísimas veces desde pocas direcciones es un gusano insistiendo contra el mismo puerto; uno golpeado menos pero desde muchas más direcciones es rastreo masivo buscando qué hay expuesto. Son dos amenazas distintas y la única forma de distinguirlas es mirar las dos cifras juntas.',
    intro1:
      'El señuelo no expone solo SSH. Estos son los otros servicios que dejó abiertos, y lo que llegó a cada uno.',
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
    unknown: 'Servicio expuesto por el sensor multiprotocolo.',
    fromSources: (d: string) => `desde ${d} direcciones`,
    times: (v: string) => `${v} veces`,
    axisX: 'direcciones distintas',
    axisY: 'eventos por dirección',
    isoLabel: (v: string) => `${v} eventos`,
    isoNote: 'Sobre cada diagonal punteada el volumen total es el mismo.',
    noteWorm: 'un gusano: pocas máquinas que no paran de insistir',
    noteScan: 'un barrido: muchas direcciones, pocas veces cada una',
    lessonTitle: 'Lo que enseña la comparación',
    lesson:
      'Mirá las dos barras de SMB y las de HTTP. SMB acumula el grueso del volumen desde muy pocas direcciones: es un puñado de gusanos reintentando sin parar contra el mismo puerto. HTTP es al revés, mucho menos tráfico repartido entre muchísimas más direcciones: son escáneres distintos barriendo internet una vez cada uno. El mismo número de eventos significa cosas opuestas según cuántos lo produjeron, y por eso contar alertas no alcanza para priorizarlas.',
  },
  dictionary: {
    usersTitle: 'Usuarios más probados',
    usersHint: 'Los atacantes prueban los nombres que casi siempre existen. No hay adivinanza.',
    passTitle: 'Contraseñas más probadas',
    passHint: 'Todas salen de diccionarios públicos armados con filtraciones reales.',
    unitUsers: 'intentos de acceso con este usuario',
    unitPass: 'veces que se probó esta contraseña',
    empty: '(vacía)',
    ofTop: 'del top 10',
    timesLess: (n: string, k: string) => `${n} veces menos que ${k}`,
    noteTop: (k: string, p: string) => `${k} solo se lleva el ${p}% del ranking`,
  },
  mitre: {
    coverageTitle: 'Cobertura del marco',
    coverageNote:
      'De las catorce tácticas de MITRE ATT&CK Enterprise, estas son las que el señuelo observa. Las dos de acceso salen de los intentos de ingreso y las demás, de los comandos de las sesiones capturadas. Las ausentes corresponden a etapas que un señuelo de baja interacción no llega a observar, así que no representan un vacío del panel.',
    observedOf: (a: number, b: number) => `${a} de ${b} observadas`,
    unseen: 'fuera de su alcance',
    noteUnseen: 'esto el señuelo no lo puede ver',
    ofReplayed: 'de los pasos repetidos',
    sessions: 'sesiones observadas',
    session: 'sesión observada',
    techniques: 'técnicas',
    stagesTitle: 'Etapas sobre el total capturado',
    stagesNote:
      'La enorme mayoría del tráfico es reconocimiento y fuerza bruta automatizada. Solo una fracción mínima llega a ejecutar comandos: por eso el triaje importa.',
    stageEvents: 'eventos en esta etapa',
    ofEverything: 'de todo lo capturado',
    techTitle: 'Técnicas observadas',
    techNote:
      'Cada técnica es un identificador del catálogo de MITRE ATT&CK. Hacé clic para ver la ficha oficial.',
    steps: 'pasos',
    whyNotSeen: 'Por qué no aparece',
    attempts: 'intentos de acceso',
    successes: 'accesos exitosos',
    ofAttempts: 'de los intentos',
    events: 'eventos',
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
      meaning:
        'Prueba usuarios y contraseñas hasta dar con uno que funcione. Acá es fuerza bruta automatizada.',
    },
    'Acceso inicial': {
      name: 'Acceso inicial',
      meaning:
        'Entra al equipo con una credencial que funciona, casi siempre una clave por defecto.',
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
    'Movimiento lateral':
      'El sensor está aislado en su propia red, sin equipos vecinos a los que saltar. El bloqueo de tráfico saliente lo impide además a nivel de red.',
    Impacto:
      'Requiere una permanencia que la emulación no sostiene: el atacante abandona antes de llegar a esta etapa.',
  },
  passcheck: {
    title: '¿Tu contraseña está acá?',
    intro: (distintas: string | null) =>
      `Comparala contra ${distintas ? `las ${distintas} contraseñas distintas` : 'las contraseñas'} que los atacantes probaron realmente contra este señuelo. No se envía a ningún lado.`,
    placeholder: 'Escribí una contraseña',
    button: 'Comparar',
    failed: 'No se pudo consultar el índice. Generalo con make passwords.',
    foundTitle: 'Está en la lista.',
    foundBody: (c: string) =>
      `Se probó ${c} veces contra este equipo. Si la usás en algún lado, cambiala: no hace falta que nadie te apunte, los bots la prueban por defecto.`,
    safeTitle: 'No aparece en las capturas.',
    safeBody:
      'Que no esté acá no la vuelve segura: este es un señuelo, no un catálogo completo. Significa que no está entre las que se probaron contra este equipo durante la captura.',
    hashTitle: 'El resumen SHA-256 de lo que escribiste, tal como sale del navegador.',
    noteSent: 'solo esto viaja',
    restStays: (c: number) => `${c} caracteres que se quedan en tu equipo`,
    privacy:
      'Cómo funciona: el navegador calcula el hash SHA-256 de lo que escribís y envía solo los primeros cinco caracteres. El servicio responde con todos los hashes capturados que empiezan igual, y la comparación termina acá. La contraseña nunca sale de tu equipo, y el servicio no puede saber cuál preguntaste.',
  },
  fingerprints: {
    concentrationTitle: 'Cuánto de todo esto es un solo programa',
    otherFamilies: 'el resto de las familias',
    ungrouped: 'sesiones sin familia',
    notePanal: (c: number) => `un solo guion: ${c} de cada 100 sesiones`,
    topOne: 'la familia más grande',
    topThree: 'las tres primeras',
    machinesBehind: 'máquinas que lo corren',
    concentrationNote: (p: string, m: string) =>
      `Una sola familia explica el ${p}% de todas las sesiones que llegaron a una consola, ejecutada desde ${m} direcciones distintas. Esa proporción es el punto entero: no son ${m} atacantes decidiendo qué escribir, es un guion desplegado en ${m} máquinas comprometidas. Contar alertas reportaría miles de incidentes donde hay uno.`,
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
    truncated: (n: number) => `y ${n - 12} comandos más`,
    lesson:
      'Casi todas las sesiones capturadas son el mismo guion ejecutado por muchas máquinas, y no ataques distintos. Agrupar por secuencia exacta de comandos lo hace evidente, y de paso muestra por qué contar alertas no sirve para medir amenazas. Una familia con miles de sesiones desde un puñado de direcciones no son miles de atacantes: es un programa, repetido.',
  },
  archetypes: {
    addresses: 'direcciones',
    // Los rasgos se traducen acá y no en la API: el backend manda el nombre de columna, que es
    // neutral al idioma, y así no hay que enviar dos versiones de cada texto.
    usedCmd: (c: string) => `usó "${c}"`,
    traits: {
      log1p_n_eventos: 'volumen de eventos',
      log1p_n_sesiones: 'cantidad de sesiones',
      log1p_eventos_por_sesion: 'eventos por sesión',
      log1p_login_intentos: 'intentos de acceso',
      log1p_login_exitosos: 'accesos logrados',
      log1p_usuarios_distintos: 'usuarios distintos probados',
      log1p_pass_distintas: 'contraseñas distintas probadas',
      log1p_n_comandos: 'comandos ejecutados',
      ejecuto_comandos: 'llegó a ejecutar comandos',
      descargo_archivo: 'descargó un archivo',
      ratio_ssh: 'proporción de SSH',
      log1p_span_horas: 'horas entre el primer y último evento',
      horas_activas: 'horas distintas con actividad',
      ratio_nocturno: 'proporción de actividad nocturna',
      log1p_dur_sesion_media_s: 'duración media de sesión',
      tuvo_logins: 'intentó autenticarse',
      ratio_fallo_login: 'proporción de accesos fallidos',
      log1p_interarribo_medio_s: 'tiempo medio entre eventos',
      log1p_eventos_por_hora: 'ritmo por hora',
    } as Record<string, string>,
    traitsTitle: 'En qué se distingue, en desvíos del promedio',
    sd: (v: string) => `${v} desv.`,
    ranCommands: 'Ejecutó comandos',
    downloaded: 'Descargó archivo',
    gotIn: 'Logró acceso',
    lesson:
      'Las huellas agrupan ataques por la secuencia exacta de comandos, y por eso no ven a quien nunca llegó a una consola. Esta vista trabaja al revés. Toma el comportamiento de cada dirección observada (cuánto insistió, a qué hora, si probó credenciales, si descargó algo) y deja que los datos decidan dónde caen los límites. La enorme mayoría solo golpea la puerta. Un grupo muy chico es el que entra y actúa.',
    method: (dirs: string, feats: number, groups: number) =>
      `Agrupamiento no supervisado sobre ${dirs} direcciones y ${feats} características de comportamiento. La cantidad de grupos (${groups}) se eligió por el criterio de silueta, no a mano. Los grupos son descriptivos: no existe una clave externa que diga cuántos tipos de atacante hay, y los nombres son una interpretación de cada perfil.`,
    groups: {
      'Intrusión efectiva': {
        name: 'Intrusión efectiva',
        blurb:
          'Entraron, ejecutaron comandos y trajeron algo desde afuera. Es el único grupo donde hubo un compromiso real y no un intento.',
      },
      'Fuerza bruta': {
        name: 'Fuerza bruta',
        blurb:
          'Prueban credenciales de forma sostenida. Algunos entran, pero casi ninguno hace algo después: el objetivo parece ser la credencial en sí, para venderla o sumarla a una lista.',
      },
      Sondeo: {
        name: 'Sondeo',
        blurb:
          'Se conectan, miran y se van. Sin insistencia ni comandos: es reconocimiento indiscriminado, el ruido de fondo permanente de internet.',
      },
    },
  },
  funnel: {
    title: 'De golpear la puerta a llevarse algo',
    knocked: 'Golpearon la puerta',
    knockedHint: 'Direcciones distintas que tocaron el sensor al menos una vez',
    tried: 'Insistieron con credenciales',
    triedHint: 'Dejaron de ser un sondeo y probaron entrar',
    gotIn: 'Lograron entrar',
    gotInHint: 'Alguna combinación de usuario y contraseña funcionó',
    ran: 'Ejecutaron comandos',
    ranHint: 'Llegaron a una consola e hicieron algo con ella',
    took: 'Trajeron algo de afuera',
    tookHint: 'Descargaron un archivo: es la señal de un compromiso real',
    ofTotal: (p: string) => `${p}% del total`,
    ofPrevious: (p: string) => `${p}% del anterior`,
    noteDrop: (p: string) => `acá se pierde el ${p}%`,
    lesson: (total: string, fin: string, porc: string) =>
      `De ${total} direcciones que golpearon la puerta, ${fin} llegaron a descargar algo: el ${porc}%. En esa caída se apoya el triaje automático. Tratar cada evento como una alerta obliga a revisar catorce mil cosas para encontrar doscientas, así que la tarea del motor pasa más por descartar bien que por detectar más.`,
  },
  geography: {
    byCountry: 'Por país',
    byAs: 'Por red que opera la dirección',
    addresses: 'direcciones',
    perAddress: (r: string) => `${r} eventos por dirección`,
    fromAddresses: (d: string) => `desde ${d} direcciones`,
    noteLoud: 'pocas máquinas, mucho ruido',
    eventsShort: 'eventos',
    perAddressShort: 'por dirección',
    // "De localizados" y no "del total": el porcentaje se calcula sobre los eventos cuyo país se
    // pudo resolver, que no son todos. Decir "del total" sería un número distinto del que se muestra.
    ofLocated: 'de localizados',
    dragHint: 'Arrastrá el globo con el mouse para girarlo a mano.',
    pickHint:
      'Cada punto es un país de origen, ubicado en el centroide de las direcciones que se observaron ahí. El tamaño sigue el volumen de eventos. Tocá un punto o una fila para que el globo gire hasta ese país.',
    selected: (p: string) =>
      `${p} seleccionado. El marcador queda al frente y resaltado en la tabla. Tocalo de nuevo para soltar la selección y que el globo retome el giro.`,
    lesson:
      'Un ataque lanzado desde un servidor alquilado y otro desde una conexión hogareña pueden compartir bandera y ser cosas distintas. Por eso al país lo acompaña el sistema autónomo, que nombra a la red que realmente opera la dirección: cuando aparece un proveedor de nube o de alojamiento, no hay una persona en ese país, hay una máquina rentada. Y conviene mirar los eventos por dirección: un país puede liderar en volumen y ser apenas un puñado de máquinas insistiendo.',
    coverage: (geo: string, asn: string) =>
      `Se resolvió el país del ${geo}% de los eventos y la red operadora del ${asn}%. Las bases son las GeoLite2 gratuitas de MaxMind, de 2019: no conocen todas las direcciones, y una dirección que cambió de manos desde entonces aparece con su dueño de aquel momento. Además, quien usa una VPN o una cadena de equipos comprometidos aparece donde está el último salto: el dato sirve para agrupar y comparar, no para atribuir. Incluye datos GeoLite2 creados por MaxMind (maxmind.com), bajo licencia CC BY-SA 4.0.`,
  },
  week: {
    title: 'La semana completa, hora por hora',
    utc: 'horario UTC',
    days: ['LUN', 'MAR', 'MIÉ', 'JUE', 'VIE', 'SÁB', 'DOM'],
    daysLong: ['Lunes', 'Martes', 'Miércoles', 'Jueves', 'Viernes', 'Sábado', 'Domingo'],
    perHour: 'eventos por hora, en promedio',
    observed: (n: number) => `medido sobre ${n} ${n === 1 ? 'semana' : 'semanas'}`,
    office: 'Oficina L-V 9-18',
    night: 'Madrugada 0-6',
    weekend: 'Fin de semana',
    vsOffice: (r: string) => `${r} veces la actividad de oficina`,
    verdictAutomated:
      'Acá está la prueba de que no hay nadie del otro lado. Un sistema operado por personas se enciende de lunes a viernes en horario de oficina y se apaga de noche y los fines de semana. Acá pasa lo contrario: la madrugada y el fin de semana superan al horario laboral. Los atacantes no trabajan de noche. Simplemente no duermen, porque son programas corriendo sin supervisión.',
    verdictMixed:
      'La distribución no reproduce un horario humano, pero tampoco es del todo pareja. Conviene mirar las celdas más intensas: suelen corresponder a una campaña puntual y no a un patrón sostenido.',
  },
  controls: {
    interval: { hour: 'Por hora', day: 'Por día', week: 'Por semana' },
    allSensors: 'Ambos',
    loading: 'actualizando...',
    from: 'Desde',
    to: 'Hasta',
    reset: 'Ver todo',
    shortcut: {
      hoy: 'Último día',
      ayer: 'Día anterior',
      semana: 'Última semana',
      mes: 'Último mes',
      todo: 'Todo',
    },
  },
  triage: {
    decisions: 'Decisiones del motor',
    reasoned: 'razonadas por el modelo',
    copied: 'copiadas del repertorio',
    cost: 'Costo de inferencia',
    correctedByEngine: 'corregidas tras un rechazo de la validación',
    conclusion: 'Tiempo de conclusión',
    conclusionNote: (d: number) => `del evento a la decisión guardada, últimos ${d} días`,
    conclusionP90: (p90: string, d: number, media: string | null) =>
      `${media ? `media de ${media}; ` : ''}nueve de cada diez, en menos de ${p90}. Últimos ${d} días`,
    pendingNone: (r: string) => `el motor cerró todo solo; ${r} con veredicto`,
    inbox: 'Decisiones',
    live: 'en vivo',
    newOnes: (c: number) => (c === 1 ? '1 nueva' : `${c} nuevas`),
    allTactics: 'Todas las tácticas',
    allSensors: 'Los dos sensores',
    emptyPendingTitle: 'Nada pendiente de revisión',
    emptyPendingText:
      'El motor cerró todas sus decisiones sin consultas fallidas. Igual podés revisar cualquiera desde "Todas": tu veredicto queda al lado de la decisión.',
    guide: {
      title: 'Cómo se usa esta sección',
      ok: 'Entendido',
      show: 'Cómo se usa',
      steps: [
        {
          title: 'El motor decide solo',
          text: 'Cada evento recorre el grafo de arriba. Si la conducta ya se decidió, se copia; si no, razona el modelo.',
        },
        {
          title: 'Elegí una decisión',
          text: 'En la lista de abajo, o tocando el evento que está procesando el motor. Se abre con su porqué.',
        },
        {
          title: 'Confirmala o corregila',
          text: 'Tu veredicto se guarda al lado. La decisión del motor no se modifica, así después se mide en qué se equivocó.',
        },
      ],
    },
    modal: {
      title: 'Revisar la decisión del motor',
      engineSays: 'Lo que decidió el motor',
      alreadyReviewed: (que: string, cuando: string) =>
        `Ya tiene un veredicto: ${que} el ${cuando}. Guardar uno nuevo lo reemplaza.`,
      confirmedShort: 'la confirmaste',
      correctedShort: 'la corregiste',
      question: '¿La clasificación del motor es correcta?',
      yes: 'Sí, es correcta',
      yesHint: 'Queda confirmada tal como está.',
      no: 'No, hay que corregirla',
      noHint: 'Elegís la severidad y la táctica que corresponden.',
      severityQ: '¿Qué severidad corresponde?',
      rangeHint: (piso: string, techo: string) =>
        piso === techo
          ? `Con la evidencia sola, el motor solo podía decir ${piso}. Vos podés elegir otra.`
          : `Con la evidencia sola, el motor podía ir de ${piso} a ${techo}. Vos podés salir de ese rango.`,
      outOfRange: 'Fuera de lo que la evidencia sola sostiene',
      engineTag: 'motor',
      tacticQ: '¿Qué táctica corresponde?',
      none: 'Ninguna',
      noneHint: 'El evento no se corresponde con ninguna de las tácticas que el señuelo observa.',
      noteLabel: 'Nota (opcional)',
      notePlaceholder:
        'Por qué, en una línea: sirve para medir después en qué se equivoca el motor.',
      save: 'Guardar veredicto',
      saved: 'Veredicto guardado',
      savedHint:
        'La decisión del motor queda intacta y tu veredicto se guarda al lado, con una copia de lo que decía el motor.',
      close: 'Cerrar',
      sameAsEngine: 'Es igual a lo que dijo el motor: en ese caso, confirmala.',
      untouched: 'La decisión del motor no se modifica.',
    },
    median: 'mediana',
    p90: 'p90',
    noData: 'sin datos',
    pending: 'Pendientes de revisión',
    pendingNote: (r: string) => `de ${r} que el motor no pudo cerrar solo`,
    bySeverity: 'Por severidad',
    byTactic: 'Por táctica',
    noTactic: 'sin táctica',
    filterHint: 'Tocá una barra para filtrar el listado.',
    state: { todas: 'Todas', pendientes: 'Pendientes', revisadas: 'Revisadas' },
    severity: 'Severidad',
    tactic: 'Táctica',
    sensor: 'Sensor',
    any: 'Cualquiera',
    clear: 'Limpiar filtros',
    when: 'Momento',
    event: 'Evento',
    empty: 'No hay decisiones con estos filtros.',
    page: (a: string, b: string, total: string) => `${a} a ${b} de ${total}`,
    prev: 'Anterior',
    next: 'Siguiente',
    copiedMark: 'Copiada del repertorio',
    reasonedMark: 'Razonada por el modelo',
    needsReview: 'Requiere revisión',
    reviewed: 'Revisada',
    notConcluded: 'sin concluir',
    liveOnly: 'Las decisiones del motor se leen solo en vivo, y la API no alcanza a Elasticsearch.',
    engine: {
      active: 'Agente activo',
      idle: 'Agente en espera',
      lastAgo: (hace: string) => `última decisión hace ${hace}`,
      lastHour: 'decisiones en la última hora',
      byMemory: 'resueltas por memoria',
      toConclusion: 'del evento a la decisión',
      replay: 'Repetir las últimas',
      replaying: 'repetición de decisiones ya tomadas',
      thinking: 'Qué está haciendo el agente',
      reading:
        'Armando el contexto: qué hizo antes esta dirección, qué más pasó en la sesión y qué decidió el motor sobre ella.',
      reasoning: 'Razonando sobre el contexto con el modelo de lenguaje.',
      copied:
        'Esta conducta ya se decidió antes: se copia la decisión razonada, sin llamar al modelo.',
      noContext:
        'El evento no trae dirección de origen y no hay nada que correlacionar: se guarda como no concluyente.',
      waiting: 'Esperando la próxima decisión del motor.',
      open: 'ver la decisión',
      pulseTitle: 'Decisiones por minuto, última hora',
      pulseCopied: 'por memoria',
      pulseReasoned: 'razonadas',
      pulseTotals: (total: string, razonadas: string) =>
        `${total} en la hora, ${razonadas} razonadas`,
      pulseMinute: (c: number, copiadas: number) =>
        c === 0
          ? 'sin decisiones'
          : `${c} ${c === 1 ? 'decisión' : 'decisiones'}, ${copiadas} por memoria`,
      pulseNow: 'ahora',
      pulseMissing:
        'El gráfico por minuto necesita la versión nueva de la interfaz de programación.',
      feed: 'Decisiones a medida que llegan',
      ring: (a: number, b: number) => `${a} de las últimas ${b} decisiones pasaron por este nodo`,
      retries: (n: number) => (n === 1 ? 'con 1 reproche' : `con ${n} reproches`),
      paths: {
        memory: 'atajo de memoria',
        retry: 'vuelta por reproche',
        noContext: 'sin contexto',
        full: 'ciclo completo',
      },
      nodes: {
        memoria: { name: 'memoria', what: '¿ya vi esta conducta?' },
        contexto: { name: 'contexto', what: 'qué es este evento' },
        historial: { name: 'historial', what: 'qué hizo antes' },
        inferencia: { name: 'inferencia', what: 'el modelo razona' },
        validacion: { name: 'validación', what: 'esquema y piso' },
        persistencia: { name: 'persistencia', what: 'queda guardada' },
      },
    },
    detail: {
      title: 'Decisión del motor',
      review: 'Revisar esta decisión',
      stateReviewed: 'Revisada por el analista',
      statePending: 'Pendiente de revisión',
      stateEngine: 'Resuelta por el motor, sin revisar',
      eventAt: (x: string) => `evento ${x}`,
      decidedAt: (x: string) => `decidida ${x}`,
      took: (x: string) => `${x} después`,
      why: 'Por qué lo decidió',
      seeOriginal: 'ver la original',
      pathMemory:
        'Salió por el atajo de memoria: la misma conducta ya tenía una decisión, y se copió sin consultar al modelo.',
      pathNoContext:
        'El evento no traía dirección de origen: sin nada que correlacionar, se guardó sin pasar por el modelo.',
      pathRetry: (r: number) =>
        `Hizo el ciclo completo, y la validación le devolvió la respuesta al modelo ${r === 1 ? 'una vez' : `${r} veces`} antes de aceptarla.`,
      pathFull:
        'Hizo el ciclo completo: armó el contexto, razonó con el modelo y la validación aceptó la respuesta.',
      cost: 'Costo',
      seconds: 'Duración de la llamada',
      signature: 'Firma de conducta',
      close: 'Cerrar',
      path: 'Cómo la resolvió el agente',
      attributes: 'Atributos normalizados del evento',
      noEvent:
        'El evento ya no está en los índices de telemetría. La decisión conserva sus datos principales.',
      classification: 'Clasificación del motor',
      notConcluded: 'El motor no llegó a una clasificación.',
      confidence: 'confianza',
      bounds: (piso: string, techo: string) =>
        piso === techo
          ? `Para este evento la escala solo admite ${piso}.`
          : `La escala admite de ${piso} a ${techo} para este evento.`,
      justification: 'Justificación',
      evidence: 'Evidencia',
      cycle: 'Cómo se decidió',
      copiedFrom: 'Copiada de la decisión de otro evento con la misma conducta:',
      open: 'abrir',
      attempts: 'intentos',
      rejections: 'rechazos',
      reproaches: 'Reproches de la validación',
      failed: 'Consultas que fallaron',
      failedNote: 'La decisión se tomó sin esta parte del contexto, por eso va a revisión.',
      cutReason: 'Motivo del corte',
      model: 'Modelo',
    },
    verdict: {
      title: 'Veredicto del analista',
      explain:
        'La decisión del motor no se modifica: el veredicto queda al lado, para medir después en qué se equivocó.',
      none: 'Todavía sin veredicto.',
      confirm: 'Confirmar la del motor',
      correct: 'Corregir',
      save: 'Guardar corrección',
      cancel: 'Cancelar',
      note: 'Nota (opcional)',
      saving: 'Guardando...',
      confirmed: 'Confirmó la clasificación del motor',
      corrected: 'Corrigió la clasificación',
      cannotConfirm: 'No hay clasificación del motor que confirmar: corresponde corregir.',
      change: 'Cambiar veredicto',
      blindTag: 'a ciegas',
      blindLocked:
        'Revisada a ciegas: es la referencia con la que se mide al motor y no se cambia.',
    },
    blind: {
      open: 'Revisión a ciegas',
      title: 'Revisión a ciegas',
      progress: (hechas: number, total: number) => `${hechas} de ${total} revisadas`,
      intro:
        'Elegí la severidad y la táctica que te parecen correctas sin ver lo que dijo el motor. Al guardar aparece su clasificación y la comparación queda registrada.',
      event: 'El evento',
      attributes: 'Atributos del evento',
      noEvent: 'El evento ya no está en el índice de telemetría; queda el resumen.',
      range: (piso: string, techo: string) =>
        piso === techo
          ? `La evidencia sola establece ${piso}.`
          : `La evidencia sola establece ${piso}, y la escala admite hasta ${techo}.`,
      save: 'Guardar y ver lo del motor',
      saving: 'Guardando...',
      missing: 'Falta elegir la severidad y la táctica.',
      yours: 'Tu clasificación',
      engine: 'La del motor',
      matches: 'Coinciden',
      differs: 'No coinciden',
      severity: 'Severidad',
      tactic: 'Táctica',
      recorded: (confirma: boolean): string =>
        confirma
          ? 'Quedó registrada como confirmación del motor.'
          : 'Quedó registrada como corrección del motor.',
      next: 'Siguiente',
      pause: 'Seguir más tarde',
      done: (total: number) =>
        `Terminaste la muestra: las ${total} conductas tienen su revisión a ciegas.`,
      loading: 'Buscando la próxima conducta...',
    },
  },
  severities: {
    informativo: 'informativo',
    bajo: 'bajo',
    medio: 'medio',
    alto: 'alto',
    critico: 'crítico',
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
    range: (desde: string, hasta: string) => `${desde} to ${hasta}`,
  },
  loading: 'Loading...',
  error: {
    title: 'Could not load telemetry',
    hint: 'Check that the API is running:',
  },
  navGroups: {
    operacion: 'Operations',
    aprender: 'Learn',
  },
  menu: {
    open: 'Open the menu',
    close: 'Close the menu',
  },
  theme: {
    title: 'Theme',
    sistema: 'Match the system',
    claro: 'Light',
    oscuro: 'Dark',
  },
  nav: {
    inicio: 'Overview',
    pulso: 'The pulse',
    anatomia: 'Anatomy of an attack',
    protocolos: 'Beyond SSH',
    diccionario: "The attacker's dictionary",
    huellas: 'Botnet fingerprints',
    arquetipos: 'Kinds of attacker',
    origen: 'Where they come from',
    mitre: 'MITRE tactics',
    triaje: 'Engine triage',
  },
  lead: {
    inicio:
      'All of HoneyML on one screen: what reaches the decoy, what the engine decides and where to go next.',
    pulso: 'A machine nobody advertised anywhere, exposed to the internet. This is what it gets.',
    anatomia: 'A real captured intrusion, replayed step by step. Every command, explained.',
    protocolos:
      'SSH is the door everyone remembers to lock. These are the others, and what reached each one.',
    diccionario:
      'Which credentials they try, and why. The evidence behind every security recommendation.',
    huellas:
      'Thousands of sessions, a handful of scripts. What is left when you group them by what they run.',
    arquetipos:
      'Almost none of those knocking ever get in. These are the ones who do, and what sets them apart.',
    origen: 'The country says little on its own. The network operating the address says far more.',
    mitre: 'The framework used to classify each action, lit up with our own captures.',
    triaje:
      'What the engine decided about each event, on what evidence and at what cost. Whatever it could not settle on its own is decided by whoever operates the panel.',
  },
  home: {
    engineTitle: 'Triage engine',
    lastHour: 'decisions in the last hour',
    toDecision: 'from event to decision',
    pending: 'waiting for the analyst',
    engineLine: (total: string, copiadas: string, costo: string) =>
      `${total} decisions on real traffic. ${copiadas}% were settled by copying an earlier decision on the same behavior, without asking the model. Total cost: USD ${costo}.`,
    openEngine: 'See the engine at work',
    distinctOrigins: 'distinct origins, none of them invited',
    learnTitle: 'To understand what is going on',
    learnHint: 'Each card opens its section.',
    cards: {
      pulso: (dias: number) => `events over ${dias} days of capture`,
      anatomia: 'real intrusions, replayed command by command',
      protocolos: (servicio: string) =>
        `events per address on ${servicio}: a few machines pushing hard`,
      diccionario: (usuario: string) => `attempts with the username ${usuario}`,
      huellas: 'of sessions with commands are a single script',
      arquetipos: 'of addresses reach an effective intrusion',
      origen: (pais: string) => `events per address from ${pais}`,
      mitre: 'framework tactics the decoy can observe',
    },
  },
  pulse: {
    notePeak: (eventos: string, fecha: string) => `the peak: ${eventos} events on ${fecha}`,
    noteFlat: (veces: string) =>
      `almost flat: the peak is ${veces} times the trough. Nobody sleeps on the other side.`,
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
    ratio: (r: string) => `${r} times between peak and trough`,
    loginsAtThisHour: 'access attempts in that hour',
    events_short: 'events',
    outages: 'Capture outages',
    noOutages: 'No capture outages in the selected period',
    noOutagesNote:
      'The sensors recorded activity on every day of the chosen range. Outages, when they happen, show up as days with no events at all and almost always mean the sensor hung rather than the attackers pausing.',
    outagesNote:
      'Declared and documented. The gaps in the chart correspond to these periods, not to an absence of attacks.',
    days: (n: number) => (n === 1 ? '1 day' : `${n} days`),
    filtered: 'filtered',
    filterFailed: 'The filter could not be applied. The chart shows the full period.',
  },
  replay: {
    speed: 'Speed',
    pause: 'Pause',
    play: 'Play',
    restart: 'Restart',
    accessGranted: (u: string, p: string) => `Access granted with ${u}:${p}`,
    sessionEnded: 'session ended',
    step: (i: number, n: number) => `Step ${i} of ${n}`,
    keys: 'space pauses, the arrow keys step forward or back',
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
    phase: 'Attack phase',
    turn: (paso: number, que: string) => `step ${paso}: ${que}`,
    turnWhat: {
      Persistencia: 'here it makes sure it can come back',
      'Evasión de defensas': 'here it wipes its tracks',
      Ejecución: 'here it runs its own code',
      Descubrimiento: 'here it looks around',
    } as Record<string, string>,
  },
  protocols: {
    contrastTitle: 'Same sensor, opposite readings',
    perSourceLabel: 'events per address',
    sourcesShort: 'addresses',
    gap: 'apart',
    contrastNote:
      'Counting events tells you how much noise there is, not what kind. A service hit an enormous number of times from few addresses is a worm hammering the same port; one hit less often but from many more addresses is mass scanning looking for what is exposed. Those are two different threats, and the only way to tell them apart is to read both figures together.',
    intro1:
      'The decoy does not only expose SSH. These are the other services it left open, and what reached each one.',
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
    unknown: 'A service exposed by the multiprotocol sensor.',
    fromSources: (d: string) => `from ${d} addresses`,
    times: (v: string) => `${v} times`,
    axisX: 'distinct addresses',
    axisY: 'events per address',
    isoLabel: (v: string) => `${v} events`,
    isoNote: 'Along each dotted diagonal the total volume is the same.',
    noteWorm: 'a worm: a few machines that never stop pushing',
    noteScan: 'a sweep: many addresses, a few hits each',
    lessonTitle: 'What the comparison teaches',
    lesson:
      'Look at the two bars for SMB and those for HTTP. SMB piles up the bulk of the volume from very few addresses: a handful of worms retrying endlessly against the same port. HTTP is the reverse, far less traffic spread across many more addresses: distinct scanners sweeping the internet once each. The same event count means opposite things depending on how many sources produced it, and that is why counting alerts is not enough to prioritize them.',
  },
  dictionary: {
    usersTitle: 'Most attempted usernames',
    usersHint: 'Attackers try the names that almost always exist. There is no guesswork.',
    passTitle: 'Most attempted passwords',
    passHint: 'They all come from public dictionaries built from real breaches.',
    unitUsers: 'access attempts with this username',
    unitPass: 'times this password was tried',
    empty: '(empty)',
    ofTop: 'of the top 10',
    timesLess: (n: string, k: string) => `${n} times fewer than ${k}`,
    noteTop: (k: string, p: string) => `${k} alone takes ${p}% of the ranking`,
  },
  mitre: {
    coverageTitle: 'Framework coverage',
    coverageNote:
      'Of the fourteen MITRE ATT&CK Enterprise tactics, these are the ones the decoy observes. The two access tactics come from login attempts and the rest from the commands in the captured sessions. The missing ones correspond to stages a low-interaction decoy never gets to observe, so they do not represent a gap in the panel.',
    observedOf: (a: number, b: number) => `${a} of ${b} observed`,
    unseen: 'out of its reach',
    noteUnseen: 'the decoy cannot see this',
    ofReplayed: 'of the replayed steps',
    sessions: 'sessions observed',
    session: 'session observed',
    techniques: 'techniques',
    stagesTitle: 'Stages over everything captured',
    stagesNote:
      'The vast majority of traffic is reconnaissance and automated brute force. Only a tiny fraction gets as far as executing commands: that is why triage matters.',
    stageEvents: 'events at this stage',
    ofEverything: 'of everything captured',
    techTitle: 'Observed techniques',
    techNote:
      'Each technique is an identifier from the MITRE ATT&CK catalog. Click to open the official entry.',
    steps: 'steps',
    whyNotSeen: 'Why it does not appear',
    attempts: 'login attempts',
    successes: 'successful logins',
    ofAttempts: 'of all attempts',
    events: 'events',
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
      meaning: 'Tries usernames and passwords until one works. Here it is automated brute force.',
    },
    'Acceso inicial': {
      name: 'Initial Access',
      meaning:
        'Gets into the machine with a credential that works, almost always a default password.',
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
    'Movimiento lateral':
      'The sensor is isolated on its own network, with no neighboring machines to jump to. Outbound traffic blocking prevents it at the network layer as well.',
    Impacto:
      'It requires a persistence the emulation does not sustain: the attacker leaves before reaching this stage.',
  },
  passcheck: {
    title: 'Is your password in here?',
    intro: (distinct: string | null) =>
      `Compare it against ${distinct ? `the ${distinct} distinct passwords` : 'the passwords'} attackers actually tried against this decoy. It is never sent anywhere.`,
    placeholder: 'Type a password',
    button: 'Compare',
    failed: 'Could not query the index. Generate it with make passwords.',
    foundTitle: 'It is on the list.',
    foundBody: (c: string) =>
      `It was tried ${c} times against this machine. If you use it anywhere, change it: nobody has to target you, the bots try it by default.`,
    safeTitle: 'It does not appear in the captures.',
    safeBody:
      'Not being here does not make it safe: this is one decoy, not a complete catalog. It means it is not among those tried against this machine during the capture.',
    hashTitle: 'The SHA-256 digest of what you typed, as it leaves the browser.',
    noteSent: 'only this travels',
    restStays: (c: number) => `${c} characters that stay on your machine`,
    privacy:
      'How it works: the browser computes the SHA-256 hash of what you type and sends only the first five characters. The service replies with every captured hash starting the same way, and the comparison finishes here. The password never leaves your machine, and the service cannot tell which one you asked about.',
  },
  fingerprints: {
    concentrationTitle: 'How much of it is one program',
    otherFamilies: 'the other families',
    ungrouped: 'sessions without a family',
    notePanal: (c: number) => `a single script: ${c} out of every 100 sessions`,
    topOne: 'the largest family',
    topThree: 'the top three',
    machinesBehind: 'machines running it',
    concentrationNote: (p: string, m: string) =>
      `A single family accounts for ${p}% of every session that reached a shell, run from ${m} distinct addresses. That ratio is the whole point: those are not ${m} attackers deciding what to type, it is one script deployed across ${m} compromised machines. Counting alerts would report thousands of incidents where there is one.`,
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
    truncated: (n: number) => `and ${n - 12} more commands`,
    lesson:
      'Almost every captured session is the same script run by many machines rather than a distinct attack. Grouping by exact command sequence makes that obvious, and shows why counting alerts does not measure threat. A family with thousands of sessions from a handful of addresses is not thousands of attackers: it is one program, repeated.',
  },
  archetypes: {
    addresses: 'addresses',
    usedCmd: (c: string) => `ran "${c}"`,
    traits: {
      log1p_n_eventos: 'event volume',
      log1p_n_sesiones: 'number of sessions',
      log1p_eventos_por_sesion: 'events per session',
      log1p_login_intentos: 'login attempts',
      log1p_login_exitosos: 'successful logins',
      log1p_usuarios_distintos: 'distinct usernames tried',
      log1p_pass_distintas: 'distinct passwords tried',
      log1p_n_comandos: 'commands run',
      ejecuto_comandos: 'reached a shell',
      descargo_archivo: 'downloaded a file',
      ratio_ssh: 'share of SSH',
      log1p_span_horas: 'hours between first and last event',
      horas_activas: 'distinct active hours',
      ratio_nocturno: 'share of night-time activity',
      log1p_dur_sesion_media_s: 'mean session duration',
      tuvo_logins: 'attempted authentication',
      ratio_fallo_login: 'share of failed logins',
      log1p_interarribo_medio_s: 'mean time between events',
      log1p_eventos_por_hora: 'pace per hour',
    } as Record<string, string>,
    traitsTitle: 'What sets it apart, in standard deviations',
    sd: (v: string) => `${v} SD`,
    ranCommands: 'Ran commands',
    downloaded: 'Downloaded a file',
    gotIn: 'Got access',
    lesson:
      'Fingerprints group attacks by their exact command sequence, and so they cannot see anyone who never reached a shell. This view works the other way round. It takes how each observed address behaved (how hard it pushed, at what hour, whether it tried credentials, whether it downloaded anything) and lets the data draw the boundaries. The overwhelming majority only knock. A very small group is the one that gets in and acts.',
    method: (dirs: string, feats: number, groups: number) =>
      `Unsupervised grouping over ${dirs} addresses and ${feats} behavioral features. The number of groups (${groups}) was chosen by the silhouette criterion, not by hand. The groups are descriptive: there is no external key saying how many kinds of attacker exist, and the names are an interpretation of each profile.`,
    groups: {
      'Intrusión efectiva': {
        name: 'Effective intrusion',
        blurb:
          'They got in, ran commands and pulled something from outside. It is the only group where a real compromise happened rather than an attempt.',
      },
      'Fuerza bruta': {
        name: 'Brute force',
        blurb:
          'They try credentials relentlessly. Some get in, but almost none do anything afterwards: the credential itself seems to be the goal, to sell or to add to a list.',
      },
      Sondeo: {
        name: 'Probing',
        blurb:
          'They connect, look and leave. No persistence, no commands: indiscriminate reconnaissance, the permanent background noise of the internet.',
      },
    },
  },
  funnel: {
    title: 'From knocking to taking something',
    knocked: 'Knocked on the door',
    knockedHint: 'Distinct addresses that touched the sensor at least once',
    tried: 'Pushed on credentials',
    triedHint: 'Stopped being a probe and tried to get in',
    gotIn: 'Got in',
    gotInHint: 'Some username and password combination worked',
    ran: 'Ran commands',
    ranHint: 'Reached a shell and did something with it',
    took: 'Pulled something in',
    tookHint: 'Downloaded a file: the mark of a real compromise',
    ofTotal: (p: string) => `${p}% of total`,
    ofPrevious: (p: string) => `${p}% of previous`,
    noteDrop: (p: string) => `${p}% drop out here`,
    lesson: (total: string, fin: string, porc: string) =>
      `Out of ${total} addresses that knocked, ${fin} got as far as downloading something: ${porc}%. That drop-off is what automated triage rests on. Treating every event as an alert means reviewing fourteen thousand things to find two hundred, so the engine's job has more to do with discarding well than with detecting more.`,
  },
  geography: {
    byCountry: 'By country',
    byAs: 'By network operating the address',
    addresses: 'addresses',
    perAddress: (r: string) => `${r} events per address`,
    fromAddresses: (d: string) => `from ${d} addresses`,
    noteLoud: 'few machines, a lot of noise',
    eventsShort: 'events',
    perAddressShort: 'per address',
    ofLocated: 'of located',
    dragHint: 'Drag the globe with the mouse to turn it by hand.',
    pickHint:
      'Each dot is a country of origin, placed at the centroid of the addresses observed there. Size follows event volume. Tap a dot or a row and the globe turns to that country.',
    selected: (p: string) =>
      `${p} selected. The marker faces front and the row is highlighted. Tap again to release it and let the globe resume turning.`,
    lesson:
      'An attack launched from a rented server and one from a home connection can share a flag and be entirely different things. That is why the country comes paired with the autonomous system, which names the network actually operating the address: when a cloud or hosting provider shows up, there is no person in that country, there is a rented machine. It is also worth reading events per address: a country can lead on volume and be just a handful of machines pushing hard.',
    coverage: (geo: string, asn: string) =>
      `The country resolved for ${geo}% of events and the operating network for ${asn}%. The databases are MaxMind's free GeoLite2 ones, from 2019: they do not know every address, and an address that changed hands since then shows up with its owner at the time. On top of that, anyone behind a VPN or a chain of compromised machines shows up wherever the last hop is: the data is for grouping and comparing, not for attribution. Includes GeoLite2 data created by MaxMind (maxmind.com), under the CC BY-SA 4.0 license.`,
  },
  week: {
    title: 'The full week, hour by hour',
    utc: 'UTC time',
    days: ['MON', 'TUE', 'WED', 'THU', 'FRI', 'SAT', 'SUN'],
    daysLong: ['Monday', 'Tuesday', 'Wednesday', 'Thursday', 'Friday', 'Saturday', 'Sunday'],
    perHour: 'events per hour, on average',
    observed: (n: number) => `measured over ${n} ${n === 1 ? 'week' : 'weeks'}`,
    office: 'Office Mon-Fri 9-18',
    night: 'Late night 0-6',
    weekend: 'Weekend',
    vsOffice: (r: string) => `${r} times office-hours activity`,
    verdictAutomated:
      'There is the proof that nobody is on the other side. A system run by people lights up on weekdays during office hours and goes quiet at night and on weekends. Here the opposite happens: the small hours and the weekend beat the working day. Attackers do not work nights. They simply do not sleep, because they are programs running unattended.',
    verdictMixed:
      'The distribution does not reproduce a human schedule, but it is not perfectly even either. The most intense cells are worth a look: they usually mark a one-off campaign rather than a sustained pattern.',
  },
  controls: {
    interval: { hour: 'Hourly', day: 'Daily', week: 'Weekly' },
    allSensors: 'Both',
    loading: 'updating...',
    from: 'From',
    to: 'To',
    reset: 'Show all',
    shortcut: {
      hoy: 'Last day',
      ayer: 'Previous day',
      semana: 'Last week',
      mes: 'Last month',
      todo: 'All',
    },
  },
  triage: {
    decisions: 'Engine decisions',
    reasoned: 'reasoned by the model',
    copied: 'copied from the repertoire',
    cost: 'Inference cost',
    correctedByEngine: 'corrected after a validation rejection',
    conclusion: 'Time to conclusion',
    conclusionNote: (d: number) => `from the event to the stored decision, last ${d} days`,
    conclusionP90: (p90: string, d: number, media: string | null) =>
      `${media ? `mean of ${media}; ` : ''}nine out of ten in under ${p90}. Last ${d} days`,
    pendingNone: (r: string) => `the engine settled everything on its own; ${r} with a verdict`,
    inbox: 'Decisions',
    live: 'live',
    newOnes: (c: number) => (c === 1 ? '1 new' : `${c} new`),
    allTactics: 'All tactics',
    allSensors: 'Both sensors',
    emptyPendingTitle: 'Nothing waiting for review',
    emptyPendingText:
      'The engine closed every decision without failed queries. You can still review any of them from "All": your verdict is stored next to the decision.',
    guide: {
      title: 'How this section works',
      ok: 'Got it',
      show: 'How it works',
      steps: [
        {
          title: 'The engine decides on its own',
          text: 'Every event travels the graph above. If the behavior was already decided, it is copied; otherwise the model reasons.',
        },
        {
          title: 'Pick a decision',
          text: 'From the list below, or by clicking the event the engine is processing. It opens with its reasoning.',
        },
        {
          title: 'Confirm or correct it',
          text: "Your verdict is stored next to it. The engine's decision is left untouched, so its mistakes can be measured later.",
        },
      ],
    },
    modal: {
      title: "Review the engine's decision",
      engineSays: 'What the engine decided',
      alreadyReviewed: (que: string, cuando: string) =>
        `It already has a verdict: ${que} on ${cuando}. Saving a new one replaces it.`,
      confirmedShort: 'you confirmed it',
      correctedShort: 'you corrected it',
      question: "Is the engine's classification right?",
      yes: 'Yes, it is right',
      yesHint: 'It is confirmed as it stands.',
      no: 'No, it needs a correction',
      noHint: 'You choose the severity and the tactic that apply.',
      severityQ: 'Which severity applies?',
      rangeHint: (piso: string, techo: string) =>
        piso === techo
          ? `With the evidence alone, the engine could only say ${piso}. You can choose another.`
          : `With the evidence alone, the engine could go from ${piso} to ${techo}. You can go outside that range.`,
      outOfRange: 'Beyond what the evidence alone supports',
      engineTag: 'engine',
      tacticQ: 'Which tactic applies?',
      none: 'None',
      noneHint: 'The event does not match any of the tactics the decoy observes.',
      noteLabel: 'Note (optional)',
      notePlaceholder: 'Why, in one line: it helps measure later where the engine goes wrong.',
      save: 'Save verdict',
      saved: 'Verdict saved',
      savedHint:
        "The engine's decision is left untouched and your verdict is stored next to it, with a copy of what the engine said.",
      close: 'Close',
      sameAsEngine: 'This matches what the engine said: confirm it instead.',
      untouched: "The engine's decision is not modified.",
    },
    median: 'median',
    p90: 'p90',
    noData: 'no data',
    pending: 'Pending review',
    pendingNote: (r: string) => `out of ${r} the engine could not settle on its own`,
    bySeverity: 'By severity',
    byTactic: 'By tactic',
    noTactic: 'no tactic',
    filterHint: 'Click a bar to filter the list.',
    state: { todas: 'All', pendientes: 'Pending', revisadas: 'Reviewed' },
    severity: 'Severity',
    tactic: 'Tactic',
    sensor: 'Sensor',
    any: 'Any',
    clear: 'Clear filters',
    when: 'When',
    event: 'Event',
    empty: 'No decisions match these filters.',
    page: (a: string, b: string, total: string) => `${a} to ${b} of ${total}`,
    prev: 'Previous',
    next: 'Next',
    copiedMark: 'Copied from the repertoire',
    reasonedMark: 'Reasoned by the model',
    needsReview: 'Needs review',
    reviewed: 'Reviewed',
    notConcluded: 'not concluded',
    liveOnly: 'Engine decisions are only read live, and the API cannot reach Elasticsearch.',
    engine: {
      active: 'Agent active',
      idle: 'Agent idle',
      lastAgo: (hace: string) => `last decision ${hace} ago`,
      lastHour: 'decisions in the last hour',
      byMemory: 'settled from memory',
      toConclusion: 'from event to decision',
      replay: 'Replay the latest',
      replaying: 'replaying decisions already made',
      thinking: 'What the agent is doing',
      reading:
        'Building the context: what this address did before, what else happened in the session and what the engine decided about it.',
      reasoning: 'Reasoning over the context with the language model.',
      copied:
        'This behavior was already decided: the reasoned decision is copied without calling the model.',
      noContext:
        'The event has no source address and nothing to correlate: it is stored as inconclusive.',
      waiting: 'Waiting for the next engine decision.',
      open: 'open the decision',
      pulseTitle: 'Decisions per minute, last hour',
      pulseCopied: 'from memory',
      pulseReasoned: 'reasoned',
      pulseTotals: (total: string, razonadas: string) =>
        `${total} this hour, ${razonadas} reasoned`,
      pulseMinute: (c: number, copiadas: number) =>
        c === 0
          ? 'no decisions'
          : `${c} ${c === 1 ? 'decision' : 'decisions'}, ${copiadas} from memory`,
      pulseNow: 'now',
      pulseMissing: 'The per-minute chart needs the new version of the API.',
      feed: 'Decisions as they arrive',
      ring: (a: number, b: number) => `${a} of the last ${b} decisions went through this node`,
      retries: (n: number) => (n === 1 ? 'after 1 rejection' : `after ${n} rejections`),
      paths: {
        memory: 'memory shortcut',
        retry: 'retry after rejection',
        noContext: 'no context',
        full: 'full cycle',
      },
      nodes: {
        memoria: { name: 'memory', what: 'seen this before?' },
        contexto: { name: 'context', what: 'what this event is' },
        historial: { name: 'history', what: 'what it did before' },
        inferencia: { name: 'inference', what: 'the model reasons' },
        validacion: { name: 'validation', what: 'schema and floor' },
        persistencia: { name: 'persistence', what: 'stored for good' },
      },
    },
    detail: {
      title: 'Engine decision',
      review: 'Review this decision',
      stateReviewed: 'Reviewed by the analyst',
      statePending: 'Waiting for review',
      stateEngine: 'Settled by the engine, not reviewed',
      eventAt: (x: string) => `event ${x}`,
      decidedAt: (x: string) => `decided ${x}`,
      took: (x: string) => `${x} later`,
      why: 'Why it decided this',
      seeOriginal: 'open the original',
      pathMemory:
        'It took the memory shortcut: the same behavior already had a decision, which was copied without asking the model.',
      pathNoContext:
        'The event had no source address: with nothing to correlate, it was stored without going through the model.',
      pathRetry: (r: number) =>
        `It ran the full cycle, and validation sent the answer back to the model ${r === 1 ? 'once' : `${r} times`} before accepting it.`,
      pathFull:
        'It ran the full cycle: built the context, reasoned with the model and validation accepted the answer.',
      cost: 'Cost',
      seconds: 'Call duration',
      signature: 'Behavior signature',
      close: 'Close',
      path: 'How the agent settled it',
      attributes: 'Normalized event attributes',
      noEvent:
        'The event is no longer in the telemetry indices. The decision keeps its main fields.',
      classification: 'Engine classification',
      notConcluded: 'The engine did not reach a classification.',
      confidence: 'confidence',
      bounds: (piso: string, techo: string) =>
        piso === techo
          ? `For this event the scale only allows ${piso}.`
          : `The scale allows ${piso} to ${techo} for this event.`,
      justification: 'Justification',
      evidence: 'Evidence',
      cycle: 'How it was decided',
      copiedFrom: 'Copied from the decision on another event with the same behavior:',
      open: 'open',
      attempts: 'attempts',
      rejections: 'rejections',
      reproaches: 'Validation feedback',
      failed: 'Queries that failed',
      failedNote:
        'The decision was made without this part of the context, which is why it goes to review.',
      cutReason: 'Why it stopped',
      model: 'Model',
    },
    verdict: {
      title: "Analyst's verdict",
      explain:
        "The engine's decision is left untouched: the verdict is stored next to it, so its mistakes can be measured later.",
      none: 'No verdict yet.',
      confirm: "Confirm the engine's",
      correct: 'Correct',
      save: 'Save correction',
      cancel: 'Cancel',
      note: 'Note (optional)',
      saving: 'Saving...',
      confirmed: "Confirmed the engine's classification",
      corrected: 'Corrected the classification',
      cannotConfirm: 'There is no engine classification to confirm: it has to be corrected.',
      change: 'Change verdict',
      blindTag: 'blind',
      blindLocked:
        'Reviewed blind: it is the reference the engine is measured against and cannot be changed.',
    },
    blind: {
      open: 'Blind review',
      title: 'Blind review',
      progress: (hechas: number, total: number) => `${hechas} of ${total} reviewed`,
      intro:
        'Choose the severity and the tactic you think are right without seeing what the engine said. When you save, its classification appears and the comparison is recorded.',
      event: 'The event',
      attributes: 'Event attributes',
      noEvent: 'The event is no longer in the telemetry index; the summary remains.',
      range: (piso: string, techo: string) =>
        piso === techo
          ? `The evidence alone establishes ${piso}.`
          : `The evidence alone establishes ${piso}, and the scale allows up to ${techo}.`,
      save: "Save and see the engine's",
      saving: 'Saving...',
      missing: 'Choose the severity and the tactic first.',
      yours: 'Your classification',
      engine: "The engine's",
      matches: 'They match',
      differs: 'They differ',
      severity: 'Severity',
      tactic: 'Tactic',
      recorded: (confirma: boolean): string =>
        confirma
          ? 'Recorded as a confirmation of the engine.'
          : 'Recorded as a correction of the engine.',
      next: 'Next',
      pause: 'Continue later',
      done: (total: number) => `Sample finished: all ${total} behaviors have their blind review.`,
      loading: 'Looking for the next behavior...',
    },
  },
  severities: {
    informativo: 'informational',
    bajo: 'low',
    medio: 'medium',
    alto: 'high',
    critico: 'critical',
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
