# CompElectrix — contexto para Claude

Aplicación personal para comparar tarifas eléctricas (España, baja tensión, peaje 2.0TD).
Uso privado en una Raspberry Pi 4 (4 GB) con Docker, accesible por VPN. Licencia GPL-3.0-or-later.
Todo el texto de la interfaz, el código y la documentación va en español.

## Cómo trabajar con la persona usuaria

- Antes de escribir algo que firmará, preguntar qué quiere decir y qué sabe ya.
- Al revisar algo suyo, señalar los fallos sin reescribirlos. Al pulir, no cambiar tesis, ejemplos ni añadir datos.
- Si pregunta algo que le conviene aprender, hacer preguntas antes de dar la respuesta.
- Sabe informática básica: explicar pasos de despliegue con detalle y sin jerga.

## Decisiones tomadas

- **Arquitectura**: FastAPI + SQLite (`backend/`), React + Vite + Tailwind 4 + Recharts (`frontend/`), un solo contenedor.
- **Recursos**: sin tareas periódicas. El PVPC se completa **al abrir la interfaz** (`POST /api/pvpc/al-entrar`):
  solo descarga los huecos desde el último uso, pide los precios de mañana a partir de las 20:45 y espera 10 minutos entre comprobaciones.
- **Credenciales (Datadis, Octopus)**: **nunca se guardan**. Se piden en cada importación con un formulario
  `autocomplete=username/current-password` para que las rellene el gestor de contraseñas (usa 1Password).
- **Parámetros regulados** (IEE, IVA, alquiler de contador, bono social) con fechas de vigencia, prorrateados por días.
  La rebaja temporal del RDL 7/2026 (IVA 10 %, IEE 0,5 % con mínimo de 1 €/MWh) va del 22/03/2026 (AEAT) al
  31/05/2026 (comprobado con facturas de Octopus). Matiz: Octopus aplica el tipo según la fecha de la factura, no por días,
  así que una factura que cruce el 31/05 puede diferir un poco del cálculo prorrateado.
- **Subruta**: la app funciona tras un proxy con `X-Forwarded-Prefix` (inyecta `<base href>`), aunque se ha optado por
  un **puerto por servicio**.
- **Cálculo validado con facturas reales de Octopus** (`backend/tests/test_factura_real.py`, 67,48 €): la base del IEE
  es potencia + energía (sin bono social). Octopus no cuenta los días igual en todas sus facturas (a veces incluye el
  último día y a veces no), por eso existe el campo opcional `dias` en la factura.
- **Historial de potencias** por domicilio (tabla `potenciacontratada`). Las facturas con origen «horario» usan la
  media ponderada por días de la potencia vigente (es exacta, porque la potencia se paga por kW·día) y se recalculan
  al editar el historial. Las facturas manuales conservan su potencia. Se rellena al importar: Datadis
  (`get-contract-detail`, P1 y P2) y Octopus (`agreements.details.contractualMaxPower`, que en la práctica llega como **lista por periodo**, aunque
  el esquema diga número: fue la causa del error 500 en la 1.03). Datadis, sin probar con una cuenta real en esta parte. Caso real de la persona usuaria: 3,5 kW hasta el 11/02/2026 y
  4,5 kW desde el 12/02/2026.
- **Facturas de Octopus** (1.05): se traen de `account.bills` (periodo, emisión, total en céntimos y kWh de las líneas).
  Los kWh por periodo salen del consumo horario; el último día se decide comparando con los kWh facturados (Octopus
  no siempre lo incluye). Sustituyen a las mensuales «horario» que se solapen; origen «octopus», `numero` = id de
  Octopus (repetir actualiza, no duplica). **Sin probar con la cuenta real** al fusionar la 1.05.
- **Comparativa en dos modos** (1.05): «hoy» (tarifa actual con sus precios de hoy; para decidir) y «pagado» (solo
  facturas con importe real; fila «Lo que pagaste» como referencia; pasado contra pasado). Si gana el PVPC, aviso
  de que depende del mercado, con las facturas en que habría salido más caro.
- **Los precios de las tarifas cambian con el tiempo** (Octopus: peajes en enero, margen de P2 de 0,025 a 0,027).
  La comparativa usa los precios actuales de cada tarifa. Pendiente, quizá: un historial de precios por tarifa.
- **Disco**: base de datos < 1 MB por año de datos horarios. Panel en Ajustes → Almacenamiento, con un botón para compactar.

## Estado

- Última versión fusionada: **1.06** (18/11/2026). Pendiente de que la persona usuaria pruebe con su cuenta: la
  importación de **facturas de Octopus** (1.05) y la comparativa «con lo que pagué».
- Fase 1 ✅ domicilios, facturas, tarifas, motor 2.0TD, comparativa, tema claro/oscuro.
- Fase 2 ✅ PVPC de REE (REData, con reintentos ante su antibots), consumo horario desde CSV, Datadis y Octopus.
  **Octopus probado con la cuenta real de la persona usuaria** (18/11/2026: ~13.500 horas importadas, de mayo de 2025
  a noviembre de 2026). Datadis sigue **sin probar con una cuenta real**.
- Pendiente:
  - **Fase 3**: leer facturas en PDF, foto o texto, con IA opcional. Necesita facturas reales de Octopus anonimizadas.
    La API de Octopus también expone las facturas en PDF (`account.bills` → `attachments.temporaryUrl`).
  - **Portal Wall-O** (repositorio iTiton/Wall-O): CompElectrix se integra con `docker-compose.wallo.yml`
    (activado con `COMPOSE_FILE` en `.env`). Se entra por el puerto 8101 y se duerme tras 15 minutos sin uso.
  - **HTTPS y acceso**: la VPN y el certificado están en un NAS Synology (dominio `*.synology.me`, no ponerlo en el
    repositorio). Proxy inverso de DSM, una regla por puerto, hacia la Raspberry. Hace falta el paquete DNS Server de DSM
    para que el nombre apunte al NAS dentro de la VPN. Sin confirmar: qué puertos redirige su router y qué protocolo usa la VPN.
  - Fase 4: ofertas del comparador de la CNMC. Fase 5: informes PDF. Fase 6: guía de despliegue. Fase 7: gas (TUR).

## Versiones y ramas

- `main` es la versión estable (la que se instala). La 1.00 se fusionó el 15/11/2026.
- La siguiente versión (1.01, 1.02…) se trabaja en una rama aparte. Cuando está madura, se crea una pull request
  hacia `main` y la fusiona Claude cuando la persona usuaria lo pide. Después, la siguiente versión empieza en otra rama.
- No subir nada directamente a `main`.
- **Número de versión**: `backend/app/version.py`. Se pone el de la versión en curso al empezarla (p. ej. 1.04) y se
  comprueba antes de fusionar. Se ve en el menú lateral, en Ajustes y en la portada de Wall-O (vía `/api/salud`).

## Comprobaciones antes de entregar

```bash
cd backend && .venv/bin/python -m pytest -q        # pruebas
cd frontend && npm run build                         # tipos y compilación
```

Después, probar en el navegador con Playwright (tema claro y oscuro, ancho de móvil) y con datos de `python -m scripts.demo`.
