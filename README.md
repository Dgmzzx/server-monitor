# server-monitor

Monitor de recursos para servidor, en terminal. Muestra CPU (uso, por núcleo y
temperatura), RAM, red/wifi, y servicios corriendo (systemd + Docker).

![Vista del monitor](/assets/monitor-img.png)

## Instalación

```bash
git clone https://github.com/Dgmzzx/server-monitor.git
cd server-monitor
pip install -r requirements.txt
```

Opcional: instalar `lm-sensors` para que la temperatura de CPU se muestre
correctamente:

```bash
sudo apt install lm-sensors -y
sudo sensors-detect
```

## Uso

```bash
python3 main.py
```

Controles:
- Flechas / mouse: navegar la tabla de servicios
- `q`: salir

## Estructura

```
server-monitor/
├── main.py            # punto de entrada
├── monitor/
│   ├── app.py          # interfaz (Textual)
│   └── metrics.py       # recolección de datos del sistema
├── requirements.txt
└── pyproject.toml
```

## Roadmap / ideas para extender

- [ ] Panel de disco (uso, IO)
- [ ] Alertas visuales cuando CPU/RAM/temp superen un umbral
- [ ] Configuración por archivo `.toml` (qué paneles mostrar, intervalos)
- [ ] Logs históricos (guardar métricas en SQLite)
