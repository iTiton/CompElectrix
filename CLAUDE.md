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
  La rebaja temporal de marzo–mayo de 2026 no está cargada (fechas sin confirmar).
- **Subruta**: la app funciona tras un proxy con `X-Forwarded-Prefix` (inyecta `<base href>`), aunque se ha optado por
  un **puerto por servicio**.
- **Disco**: base de datos < 1 MB por año de datos horarios. Panel en Ajustes → Almacenamiento, con un botón para compactar.

## Estado

- Fase 1 ✅ domicilios, facturas, tarifas, motor 2.0TD, comparativa, tema claro/oscuro.
- Fase 2 ✅ PVPC de REE (REData, con reintentos ante su antibots), consumo horario desde CSV, Datadis y Octopus
  (consultas GraphQL validadas contra el esquema real; Datadis y Octopus **sin probar con una cuenta real**).
- Pendiente:
  - **Fase 3**: leer facturas en PDF, foto o texto, con IA opcional. Necesita facturas reales de Octopus anonimizadas.
    La API de Octopus también expone las facturas en PDF (`account.bills` → `attachments.temporaryUrl`).
  - **Portal Wall-O** (repositorio iTiton/Wall-O): CompElectrix se integra con `docker-compose.wallo.yml`
    (activado con `COMPOSE_FILE` en `.env`). Se entra por el puerto 8101 y se duerme tras 15 minutos sin uso.
  - **HTTPS y acceso**: la VPN y el certificado están en un NAS Synology (dominio `*.synology.me`, no ponerlo en el
    repositorio). Proxy inverso de DSM, una regla por puerto, hacia la Raspberry. Hace falta el paquete DNS Server de DSM
    para que el nombre apunte al NAS dentro de la VPN. Sin confirmar: qué puertos redirige su router y qué protocolo usa la VPN.
  - Fase 4: ofertas del comparador de la CNMC. Fase 5: informes PDF. Fase 6: guía de despliegue. Fase 7: gas (TUR).

## Comprobaciones antes de entregar

```bash
cd backend && .venv/bin/python -m pytest -q        # pruebas
cd frontend && npm run build                         # tipos y compilación
```

Después, probar en el navegador con Playwright (tema claro y oscuro, ancho de móvil) y con datos de `python -m scripts.demo`.
