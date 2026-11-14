# CompElectrix

Aplicación de comparación de tarifas eléctricas para uso personal, pensada para ejecutarse en casa
(por ejemplo en una Raspberry Pi) y usarse desde el navegador del móvil o del ordenador.

- Varios **domicilios** gestionados de forma independiente.
- Registro de **facturas** con consumo por periodos (P1, P2, P3), potencia e importes.
- **Catálogo de tarifas** de las comercializadoras.
- **Comparativa** que simula tus facturas reales con cada tarifa, con todo el detalle: potencia, energía,
  descuentos, cuotas, financiación del bono social, impuesto eléctrico, alquiler del contador e IVA.
  Muestra el ahorro mensual y anual, un ranking, gráficas y el desglose concepto a concepto.
- **Fiabilidad**: compara lo que calcula la aplicación con lo que pagaste de verdad.
- **Parámetros regulados con fechas** (IVA, impuesto eléctrico, bono social…): si cambian a mitad de una
  factura, se prorratea por días.
- Tema **claro, oscuro o automático**, y adaptada al móvil.

> Los cálculos son orientativos. Compruébalos siempre con las condiciones oficiales de cada oferta.

## Estado

| Fase | Contenido | Estado |
|---|---|---|
| 1 | Domicilios, facturas y tarifas a mano, motor de cálculo 2.0TD, comparativa, temas | ✅ |
| 2 | PVPC automático (REE), importar consumos de Datadis y de la comercializadora | Pendiente |
| 3 | Leer facturas desde PDF, foto o texto (con IA opcional) | Pendiente |
| 4 | Importar ofertas del comparador de la CNMC | Pendiente |
| 5 | Informes guardados y exportación a PDF | Pendiente |
| 6 | Guía de acceso por VPN (Tailscale) y copias de seguridad | Pendiente |
| — | Autoconsumo y excedentes | Más adelante |

## Instalación en una Raspberry Pi (o cualquier equipo con Docker)

Necesitas una Raspberry Pi 4 o superior con Raspberry Pi OS de 64 bits.

**1. Instala Docker** (solo la primera vez). Abre una terminal en la Raspberry y escribe:

```bash
curl -fsSL https://get.docker.com | sh
sudo usermod -aG docker $USER
```

Cierra la sesión y vuelve a entrar para que se aplique.

**2. Descarga CompElectrix y arráncala:**

```bash
git clone https://github.com/iTiton/CompElectrix.git
cd CompElectrix
docker compose up -d --build
```

La primera vez tarda unos minutos porque tiene que prepararlo todo. Después arranca sola cada vez que se enciende la Raspberry.

**3. Ábrela** en el navegador de cualquier dispositivo de tu red: `http://raspberrypi.local:8000`
(o `http://IP-DE-LA-RASPBERRY:8000`).

### ¿Quieres probarla con datos inventados?

```bash
docker exec compelectrix python -m scripts.demo
```

Solo se carga si la aplicación está vacía. Después puedes borrar los domicilios de ejemplo desde la propia aplicación.

### Actualizar

```bash
cd CompElectrix
git pull
docker compose up -d --build
```

### Copia de seguridad

Todos tus datos están en la carpeta `data/`. Para hacer una copia basta con copiar esa carpeta
(mejor con la aplicación parada: `docker compose stop`, copiar y `docker compose start`).

### Consumo de recursos

Un solo contenedor con unos 50 MB de RAM en reposo y la CPU prácticamente a 0 %. Tiene un límite de
256 MB de memoria y un núcleo, así que nunca acapara la Raspberry. Los registros se limitan para no gastar
la tarjeta SD.

### Página de inicio con varias herramientas

El `docker-compose.yml` incluye etiquetas para [Homepage](https://gethomepage.dev). Si lo usas, CompElectrix
aparece sola en tu panel de inicio.

## Configuración

Copia `.env.example` como `.env` si necesitas cambiar el puerto. Las claves opcionales de próximas fases (IA, ESIOS)
también irán ahí. **El archivo `.env` y la carpeta `data/` nunca se suben al repositorio.**

## Cómo introducir los datos

1. **Tarifas**: añade tu tarifa actual y las ofertas que quieras comparar. Los precios van **sin impuestos**,
   como los publican las comercializadoras:
   - Potencia en €/kW·día. Si te lo dan en €/kW·año, divide entre 365.
   - Energía en €/kWh, con un precio único o uno por periodo.
2. **Domicilio**: nombre, potencias contratadas y tarifa actual.
3. **Facturas**: fechas, kWh de cada periodo (P1 punta, P2 llano, P3 valle) y el total pagado.
4. **Comparativa**: elige el domicilio y pulsa *Comparar*.
5. **Ajustes**: revisa los impuestos y cargos. En 2026 hubo cambios temporales (rebaja de IVA e impuesto eléctrico
   entre marzo y mayo). Si tus facturas de esas fechas no cuadran, añade ese periodo con las fechas exactas.

## Desarrollo

```bash
# Servidor (Python 3.12+)
cd backend
python -m venv .venv && .venv/bin/pip install -r requirements.txt pytest httpx
.venv/bin/python -m pytest
.venv/bin/uvicorn app.main:app --reload

# Interfaz (Node 22+), en otra terminal
cd frontend
npm install
npm run dev        # http://localhost:5173, redirige /api al servidor
```

Estructura:

- `backend/app/motor/calculo.py`: motor de cálculo. Son funciones puras, con pruebas en `backend/tests/`.
- `backend/app/servicios.py`: lógica de la comparativa.
- `backend/app/api.py`: API REST bajo `/api` (documentación interactiva en `/docs`).
- `frontend/src/`: interfaz en React, Tailwind y Recharts.

## Licencia

CompElectrix es software libre bajo la [GNU General Public License v3.0 o posterior](LICENSE)
(GPL-3.0-or-later). Puedes usarlo, estudiarlo, modificarlo y redistribuirlo, pero cualquier versión
modificada que distribuyas debe publicarse también con la misma licencia y con su código fuente.

Se ofrece **sin ninguna garantía**: los cálculos son orientativos.
