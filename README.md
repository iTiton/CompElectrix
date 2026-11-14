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
- **PVPC automático**: descarga sola el precio horario oficial de Red Eléctrica y lo muestra día a día.
- **Consumo hora a hora** desde un CSV (Datadis, distribuidora, comercializadora), desde Datadis o desde Octopus.
  Con él, el PVPC se calcula exacto y se pueden crear las facturas de los meses que falten.
- **Parámetros regulados con fechas** (IVA, impuesto eléctrico, bono social…): si cambian a mitad de una
  factura, se prorratea por días.
- Tema **claro, oscuro o automático**, y adaptada al móvil.

> Los cálculos son orientativos. Compruébalos siempre con las condiciones oficiales de cada oferta.

## Estado

| Fase | Contenido | Estado |
|---|---|---|
| 1 | Domicilios, facturas y tarifas a mano, motor de cálculo 2.0TD, comparativa, temas | ✅ |
| 2 | PVPC automático (REE), consumo horario desde CSV, Datadis y Octopus | ✅ |
| 3 | Leer facturas desde PDF, foto o texto (con IA opcional) | Pendiente |
| 4 | Importar ofertas del comparador de la CNMC | Pendiente |
| 5 | Informes guardados y exportación a PDF | Pendiente |
| 6 | Guía de acceso por VPN (Tailscale) y copias de seguridad | Pendiente |
| 7 | Suministros de gas: TUR, ofertas y comparativa | Pendiente |
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
docker image prune -f      # borra las versiones anteriores de la imagen (~240 MB cada una)
```

### Copia de seguridad

Todos tus datos están en la carpeta `data/`. Para hacer una copia basta con copiar esa carpeta
(mejor con la aplicación parada: `docker compose stop`, copiar y `docker compose start`).

### Espacio en disco

| Qué | Cuánto |
|---|---|
| Imagen de Docker | ~240 MB (una sola si borras las antiguas al actualizar) |
| Un año de precios del PVPC | < 1 MB |
| Un año de consumo horario de un domicilio | < 1 MB |
| Facturas, tarifas y domicilios | unos KB |
| Registros (logs) | como máximo 2 MB, rotan solos |

En **Ajustes → Almacenamiento** ves cuánto ocupa la base de datos. El botón **Compactar** recupera el espacio
de lo que hayas borrado.

### Consumo de recursos

Un solo contenedor con unos 60 MB de RAM en reposo y la CPU prácticamente a 0 %: no hay tareas periódicas,
solo trabaja cuando la usas. Tiene un límite de
256 MB de memoria y un núcleo, así que nunca acapara la Raspberry. Los registros se limitan para no gastar
la tarjeta SD.

### Publicarla en una subruta (detrás de un portal o proxy)

CompElectrix puede vivir en una subruta, por ejemplo `https://raspberry/compelectrix/`. El proxy debe:

1. Recortar el prefijo antes de reenviar (`/compelectrix/api/salud` → `/api/salud`).
2. Indicarlo en la cabecera `X-Forwarded-Prefix: /compelectrix`.

La interfaz construye entonces todas sus direcciones relativas a esa ruta. Sin la cabecera funciona igual en la raíz.

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

## Datos automáticos

### Precio del PVPC

No hay que hacer nada. **Cada vez que abres la aplicación**, busca los días que faltan desde la última vez
y los descarga de Red Eléctrica mientras sigues usándola (verás un aviso abajo con el progreso). Mientras no la
usas no consulta nada, así que en reposo no gasta ni CPU ni red.

- La primera vez descarga algo más de un año, en un par de minutos.
- Si añades facturas más antiguas que los precios guardados, la siguiente vez completa también esas fechas.
- Los precios de mañana se piden a partir de las 20:45, cuando ya están publicados.
- Si abres la aplicación varias veces seguidas, no vuelve a preguntar hasta pasados 10 minutos.

Para forzar una descarga o bajar un periodo concreto (como muy pronto, desde junio de 2021),
ve a **Ajustes → Precios del PVPC**.

En **Precio PVPC** ves el precio de cada hora de hoy y de mañana, con su periodo.

### Consumo horario

En cada domicilio, la sección **Consumo horario** tiene tres formas de traer los datos:

1. **Importar CSV**: el fichero que descargas de Datadis, de tu distribuidora (i-DE, e-distribución, UFD…)
   o de tu comercializadora. Se reconocen automáticamente los formatos habituales.
2. **Datadis**: el portal oficial y gratuito de las distribuidoras.
   - Regístrate en [datadis.es](https://datadis.es) con tu DNI.
   - Pulsa **Datadis** en el domicilio, entra con tu usuario y elige el suministro y las fechas.
3. **Octopus Energy**: con el email y la contraseña de tu área de cliente.

Después pulsa **Crear facturas de los meses sin factura** para completar los huecos. Esas facturas no tienen
importe real, pero sirven para la comparativa.

> Las conexiones con Datadis y Octopus siguen su documentación y el esquema público de cada API, pero aún
> no se han probado con una cuenta real. Si algo falla, el mensaje de error dirá qué ha pasado.

**Las contraseñas no se guardan nunca.** Se piden en un formulario normal de inicio de sesión, que tu gestor de
contraseñas (1Password, Bitwarden, el del navegador…) puede rellenar. Se usan para esa importación y se descartan:
no se escriben ni en la base de datos ni en los registros.

> Entre tu navegador y la Raspberry viajan por tu red. Con Tailscale van cifradas. Por `http://` en la wifi de casa,
> no. Para cifrarlas también ahí, la guía de despliegue (fase 6) añadirá HTTPS.

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
- `backend/app/motor/periodos.py`: periodos P1/P2/P3, festivos y cambios de hora.
- `backend/app/servicios.py`: lógica de la comparativa, del consumo horario y del PVPC.
- `backend/app/fuentes/`: clientes de REE, Datadis y Octopus.
- `backend/app/importadores/consumo.py`: lector de CSV de consumo.
- `backend/app/api.py`: API REST bajo `/api` (documentación interactiva en `/docs`).
- `frontend/src/`: interfaz en React, Tailwind y Recharts.

## Licencia

CompElectrix es software libre bajo la [GNU General Public License v3.0 o posterior](LICENSE)
(GPL-3.0-or-later). Puedes usarlo, estudiarlo, modificarlo y redistribuirlo, pero cualquier versión
modificada que distribuyas debe publicarse también con la misma licencia y con su código fuente.

Se ofrece **sin ninguna garantía**: los cálculos son orientativos.
