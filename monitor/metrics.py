"""Funciones para recolectar métricas del sistema."""
import subprocess
import psutil


def get_cpu():
    """Devuelve % de uso de CPU (total y por núcleo) y frecuencia."""
    percent_total = psutil.cpu_percent(interval=None)
    percent_per_core = psutil.cpu_percent(interval=None, percpu=True)
    freq = psutil.cpu_freq()
    return {
        "total": percent_total,
        "per_core": percent_per_core,
        "freq_mhz": round(freq.current) if freq else None,
    }


def get_temperature():
    """Intenta leer la temperatura de la CPU (requiere lm-sensors)."""
    try:
        temps = psutil.sensors_temperatures()
    except (AttributeError, Exception):
        temps = {}

    for name in ("coretemp", "k10temp", "cpu_thermal", "acpitz"):
        if name in temps and temps[name]:
            return round(temps[name][0].current, 1)

    # Fallback: cualquier sensor disponible
    for entries in temps.values():
        if entries:
            return round(entries[0].current, 1)

    return None


def get_memory():
    """Devuelve estadísticas de RAM."""
    mem = psutil.virtual_memory()
    return {
        "total_gb": round(mem.total / (1024**3), 2),
        "used_gb": round(mem.used / (1024**3), 2),
        "available_gb": round(mem.available / (1024**3), 2),
        "percent": mem.percent,
    }


def get_disks():
    """Devuelve uso de espacio por partición montada y velocidad de IO global."""
    partitions = []
    for p in psutil.disk_partitions(all=False):
        try:
            usage = psutil.disk_usage(p.mountpoint)
        except PermissionError:
            continue
        partitions.append({
            "mountpoint": p.mountpoint,
            "device": p.device,
            "total_gb": round(usage.total / (1024**3), 2),
            "used_gb": round(usage.used / (1024**3), 2),
            "percent": usage.percent,
        })

    io = psutil.disk_io_counters()
    io_counters = {
        "read_bytes": io.read_bytes if io else 0,
        "write_bytes": io.write_bytes if io else 0,
    }
    return {"partitions": partitions, "io": io_counters}


def get_network():
    """Devuelve info de red: interfaz activa, velocidad, y señal wifi si aplica."""
    io = psutil.net_io_counters(pernic=True)
    stats = psutil.net_if_stats()

    interfaces = []
    for name, s in stats.items():
        if name == "lo" or not s.isup:
            continue
        counters = io.get(name)
        interfaces.append({
            "name": name,
            "bytes_sent": counters.bytes_sent if counters else 0,
            "bytes_recv": counters.bytes_recv if counters else 0,
        })

    wifi_signal = _get_wifi_signal()
    return {"interfaces": interfaces, "wifi": wifi_signal}


def _get_wifi_signal():
    """Lee la calidad de señal wifi desde /proc/net/wireless (si existe)."""
    try:
        with open("/proc/net/wireless") as f:
            lines = f.readlines()
        for line in lines[2:]:
            parts = line.split()
            if len(parts) >= 4:
                iface = parts[0].rstrip(":")
                quality = parts[2]
                return {"interface": iface, "quality": quality}
    except FileNotFoundError:
        return None
    return None


def get_processes(proc_cache: dict):
    """Devuelve lista de (pid, nombre, usuario, mem_mb, cpu%), ordenada por CPU desc.

    proc_cache: dict {pid: psutil.Process} que el llamador debe mantener entre
    llamadas, para que cpu_percent() mida el delta real desde el refresco anterior
    (igual que hacen htop/btop), en vez de siempre devolver 0.0.
    """
    current_pids = set()
    rows = []

    for p in psutil.process_iter(["pid", "name", "username"]):
        try:
            pid = p.info["pid"]
            current_pids.add(pid)

            if pid not in proc_cache:
                proc = psutil.Process(pid)
                proc.cpu_percent(None)  # primera llamada "prime" el medidor
                proc_cache[pid] = proc

            proc = proc_cache[pid]
            cpu = proc.cpu_percent(None)
            mem_mb = proc.memory_info().rss / (1024 * 1024)
            name = p.info["name"] or "?"
            user = p.info["username"] or "?"
            rows.append((pid, name, user, mem_mb, cpu))
        except (psutil.NoSuchProcess, psutil.AccessDenied, psutil.ZombieProcess):
            continue

    # limpiar procesos que ya no existen
    for pid in list(proc_cache.keys()):
        if pid not in current_pids:
            del proc_cache[pid]

    rows.sort(key=lambda r: r[4], reverse=True)
    return rows


def get_services():
    """Devuelve servicios systemd activos/fallidos y contenedores Docker."""
    services = _get_systemd_services()
    containers = _get_docker_containers()
    return {"systemd": services, "docker": containers}


def _get_systemd_services():
    try:
        out = subprocess.run(
            ["systemctl", "list-units", "--type=service", "--all", "--no-legend"],
            capture_output=True, text=True, timeout=3,
        ).stdout
    except Exception:
        return []

    services = []
    for line in out.splitlines():
        parts = line.split()
        if len(parts) < 4:
            continue
        name, load, active, sub = parts[0], parts[1], parts[2], parts[3]
        if active in ("active", "failed"):
            services.append({"name": name, "active": active, "sub": sub})
    return services


def get_docker_stats():
    """Devuelve CPU% y uso de memoria por contenedor (como lazydocker)."""
    try:
        out = subprocess.run(
            ["docker", "stats", "--no-stream", "--format",
             "{{.Name}}|{{.CPUPerc}}|{{.MemUsage}}|{{.MemPerc}}"],
            capture_output=True, text=True, timeout=5,
        ).stdout
    except Exception:
        return []

    stats = []
    for line in out.splitlines():
        parts = line.split("|")
        if len(parts) == 4:
            stats.append({
                "name": parts[0],
                "cpu_percent": parts[1],
                "mem_usage": parts[2],
                "mem_percent": parts[3],
            })
    return stats


def _get_docker_containers():
    try:
        out = subprocess.run(
            ["docker", "ps", "--format", "{{.Names}}|{{.Image}}|{{.Status}}"],
            capture_output=True, text=True, timeout=3,
        ).stdout
    except Exception:
        return []

    containers = []
    for line in out.splitlines():
        parts = line.split("|")
        if len(parts) == 3:
            containers.append({"name": parts[0], "image": parts[1], "status": parts[2]})
    return containers