"""Monitor de recursos del servidor - interfaz tipo btop hecha con Textual."""
from collections import deque

from textual.app import App, ComposeResult
from textual.containers import Horizontal, Vertical
from textual.widgets import Header, Footer, Static, DataTable, Sparkline, TabbedContent, TabPane

from . import metrics

HISTORY_LEN = 40


def bar(pct: float, width: int = 30) -> str:
    """Barra de progreso coloreada según el porcentaje."""
    filled = int(width * pct / 100)
    color = "red" if pct >= 85 else ("yellow" if pct >= 60 else "green")
    return f"[{color}]{'█' * filled}{'░' * (width - filled)}[/{color}]"


class CpuPanel(Vertical):
    """Panel de CPU: uso total, por núcleo, temperatura y gráfica de historial."""

    def compose(self) -> ComposeResult:
        yield Static(id="cpu-info")
        yield Sparkline([], id="cpu-sparkline")

    def on_mount(self) -> None:
        current = metrics.get_cpu()["total"]
        self.history = deque([current] * HISTORY_LEN, maxlen=HISTORY_LEN)
        self.update_data()
        self.set_interval(1.5, self.update_data)

    def update_data(self) -> None:
        cpu = metrics.get_cpu()
        temp = metrics.get_temperature()
        self.history.append(cpu["total"])

        lines = [f"[b]CPU[/b]  {bar(cpu['total'])}  {cpu['total']:.1f}%"]
        if cpu["freq_mhz"]:
            lines.append(f"Frecuencia: {cpu['freq_mhz']} MHz")
        if temp is not None:
            color = "red" if temp >= 75 else ("yellow" if temp >= 60 else "green")
            lines.append(f"Temp: [{color}]{temp}°C[/{color}]")
        else:
            lines.append("Temp: [dim]no disponible (instala lm-sensors)[/dim]")

        lines.append("")
        for i, pct in enumerate(cpu["per_core"]):
            lines.append(f"C{i}: {bar(pct, width=20)} {pct:4.1f}%")

        self.query_one("#cpu-info", Static).update("\n".join(lines))
        self.query_one("#cpu-sparkline", Sparkline).data = list(self.history)


class MemPanel(Vertical):
    """Panel de memoria RAM con gráfica de historial."""

    def compose(self) -> ComposeResult:
        yield Static(id="mem-info")
        yield Sparkline([], id="mem-sparkline")

    def on_mount(self) -> None:
        current = metrics.get_memory()["percent"]
        self.history = deque([current] * HISTORY_LEN, maxlen=HISTORY_LEN)
        self.update_data()
        self.set_interval(1.5, self.update_data)

    def update_data(self) -> None:
        mem = metrics.get_memory()
        self.history.append(mem["percent"])

        lines = [
            f"[b]RAM[/b]  {bar(mem['percent'])}  {mem['percent']}%",
            "",
            f"Total:     {mem['total_gb']} GiB",
            f"Usada:     {mem['used_gb']} GiB",
            f"Disponible:{mem['available_gb']} GiB",
        ]
        self.query_one("#mem-info", Static).update("\n".join(lines))
        self.query_one("#mem-sparkline", Sparkline).data = list(self.history)


class DiskPanel(Static):
    """Panel de discos: uso por partición y velocidad de lectura/escritura."""

    def on_mount(self) -> None:
        self._prev_io = None
        self.update_data()
        self.set_interval(1.5, self.update_data)

    def update_data(self) -> None:
        disks = metrics.get_disks()
        lines = ["[b]DISCOS[/b]", ""]

        for part in disks["partitions"]:
            b = bar(part["percent"], width=20)
            lines.append(f"{part['mountpoint']} ({part['device']})")
            lines.append(f"  {b} {part['percent']}%   {part['used_gb']}/{part['total_gb']} GiB")

        io = disks["io"]
        if self._prev_io is not None:
            read_speed = max(0, io["read_bytes"] - self._prev_io["read_bytes"]) / 2 / 1024
            write_speed = max(0, io["write_bytes"] - self._prev_io["write_bytes"]) / 2 / 1024
            lines.append("")
            lines.append(f"IO:  lectura {read_speed:7.1f} KiB/s   escritura {write_speed:7.1f} KiB/s")
        self._prev_io = io

        self.update("\n".join(lines))


class NetworkPanel(Vertical):
    """Panel de red / wifi con gráfica de historial de descarga."""

    def compose(self) -> ComposeResult:
        yield Static(id="net-info")
        yield Sparkline([], id="net-sparkline")

    def on_mount(self) -> None:
        self._prev = {}
        self.history = deque([0.0] * HISTORY_LEN, maxlen=HISTORY_LEN)
        self.update_data()
        self.set_interval(1.5, self.update_data)

    def update_data(self) -> None:
        net = metrics.get_network()
        lines = ["[b]RED[/b]", ""]
        total_down = 0.0

        for iface in net["interfaces"]:
            name = iface["name"]
            recv, sent = iface["bytes_recv"], iface["bytes_sent"]
            prev = self._prev.get(name, (recv, sent))
            down_speed = max(0, recv - prev[0]) / 2 / 1024  # KiB/s (intervalo=2s)
            up_speed = max(0, sent - prev[1]) / 2 / 1024
            self._prev[name] = (recv, sent)
            total_down += down_speed
            lines.append(f"{name}:")
            lines.append(f"  ↓ {down_speed:7.1f} KiB/s   ↑ {up_speed:7.1f} KiB/s")

        if net["wifi"]:
            lines.append("")
            lines.append(f"WiFi ({net['wifi']['interface']}): calidad {net['wifi']['quality']}")

        self.history.append(total_down)
        self.query_one("#net-info", Static).update("\n".join(lines))
        self.query_one("#net-sparkline", Sparkline).data = list(self.history)


class ProcessesPanel(Static):
    """Panel de procesos tipo btop: PID, programa, usuario, memoria y CPU% en vivo."""

    def compose(self) -> ComposeResult:
        yield DataTable(id="proc-table")

    def on_mount(self) -> None:
        table = self.query_one(DataTable)
        table.add_columns("PID", "Programa", "Usuario", "Mem", "CPU %")
        table.cursor_type = "row"
        self._procs = {}
        self.update_data()
        self.set_interval(1.5, self.update_data)

    def update_data(self) -> None:
        rows = metrics.get_processes(self._procs)
        table = self.query_one(DataTable)
        table.clear()

        for pid, name, user, mem_mb, cpu in rows[:25]:
            color = "red" if cpu >= 50 else ("yellow" if cpu >= 20 else "green")
            table.add_row(str(pid), name, user, f"{mem_mb:.1f} MiB", f"[{color}]{cpu:5.1f}%[/{color}]")


class ServicesPanel(Static):
    """Panel de servicios systemd, en tabla navegable."""

    def compose(self) -> ComposeResult:
        yield DataTable(id="services-table")

    def on_mount(self) -> None:
        table = self.query_one(DataTable)
        table.add_columns("Servicio", "Estado", "Detalle")
        table.cursor_type = "row"
        self.update_data()
        self.set_interval(2, self.update_data)

    def update_data(self) -> None:
        table = self.query_one(DataTable)
        table.clear()
        data = metrics.get_services()

        for svc in data["systemd"]:
            color = "green" if svc["active"] == "active" else "red"
            table.add_row(svc["name"], f"[{color}]{svc['active']}[/{color}]", svc["sub"])


class DockerPanel(Static):
    """Panel tipo lazydocker: stats en vivo (CPU%, memoria) por contenedor."""

    def compose(self) -> ComposeResult:
        yield DataTable(id="docker-table")

    def on_mount(self) -> None:
        table = self.query_one(DataTable)
        table.add_columns("Contenedor", "CPU %", "Memoria", "Mem %")
        table.cursor_type = "row"
        self.update_data()
        self.set_interval(2, self.update_data)

    def update_data(self) -> None:
        table = self.query_one(DataTable)
        table.clear()
        stats = metrics.get_docker_stats()

        if not stats:
            table.add_row("[dim]Sin contenedores corriendo o Docker no disponible[/dim]", "", "", "")
            return

        for c in stats:
            cpu_val = float(c["cpu_percent"].replace("%", "") or 0)
            color = "red" if cpu_val >= 80 else ("yellow" if cpu_val >= 50 else "green")
            table.add_row(
                c["name"],
                f"[{color}]{c['cpu_percent']}[/{color}]",
                c["mem_usage"],
                c["mem_percent"],
            )


class ServerMonitorApp(App):
    """App principal."""

    CSS = """
    Screen {
        layout: vertical;
    }
    #top-row {
        height: 45%;
    }
    #bottom-row {
        height: 55%;
    }
    CpuPanel, MemPanel, DiskPanel, NetworkPanel {
        border: round $primary;
        padding: 1 2;
        width: 1fr;
        height: 100%;
    }
    Sparkline {
        height: 3;
        margin-top: 1;
    }
    Sparkline > .sparkline--max-color {
        color: $error;
    }
    Sparkline > .sparkline--min-color {
        color: $success;
    }
    #bottom-row TabbedContent {
        height: 1fr;
    }
    TabPane {
        height: 1fr;
        padding: 0;
    }
    ServicesPanel, DockerPanel, ProcessesPanel {
        height: 1fr;
    }
    DataTable {
        height: 1fr;
    }
    """

    BINDINGS = [("q", "quit", "Salir")]

    def compose(self) -> ComposeResult:
        yield Header(show_clock=True)
        with Horizontal(id="top-row"):
            yield CpuPanel()
            yield MemPanel()
            yield DiskPanel()
            yield NetworkPanel()
        with Vertical(id="bottom-row"):
            with TabbedContent():
                with TabPane("Procesos", id="tab-processes"):
                    yield ProcessesPanel()
                with TabPane("Servicios", id="tab-services"):
                    yield ServicesPanel()
                with TabPane("Docker", id="tab-docker"):
                    yield DockerPanel()
        yield Footer()


def main():
    ServerMonitorApp().run()


if __name__ == "__main__":
    main()