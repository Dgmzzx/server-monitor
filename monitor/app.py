"""Monitor de recursos del servidor - interfaz tipo btop hecha con Textual."""
from textual.app import App, ComposeResult
from textual.containers import Horizontal, Vertical
from textual.widgets import Header, Footer, Static, DataTable
from textual.reactive import reactive

from . import metrics


class CpuPanel(Static):
    """Panel de CPU: uso total, por núcleo y temperatura."""

    def on_mount(self) -> None:
        self.update_data()
        self.set_interval(2, self.update_data)

    def update_data(self) -> None:
        cpu = metrics.get_cpu()
        temp = metrics.get_temperature()

        bar = self._bar(cpu["total"])
        lines = [f"[b]CPU[/b]  {bar}  {cpu['total']:.1f}%"]
        if cpu["freq_mhz"]:
            lines.append(f"Frecuencia: {cpu['freq_mhz']} MHz")
        if temp is not None:
            color = "red" if temp >= 75 else ("yellow" if temp >= 60 else "green")
            lines.append(f"Temp: [{color}]{temp}°C[/{color}]")
        else:
            lines.append("Temp: [dim]no disponible (instala lm-sensors)[/dim]")

        lines.append("")
        for i, pct in enumerate(cpu["per_core"]):
            lines.append(f"C{i}: {self._bar(pct, width=20)} {pct:4.1f}%")

        self.update("\n".join(lines))

    @staticmethod
    def _bar(pct: float, width: int = 30) -> str:
        filled = int(width * pct / 100)
        color = "red" if pct >= 85 else ("yellow" if pct >= 60 else "green")
        return f"[{color}]{'█' * filled}{'░' * (width - filled)}[/{color}]"


class MemPanel(Static):
    """Panel de memoria RAM."""

    def on_mount(self) -> None:
        self.update_data()
        self.set_interval(2, self.update_data)

    def update_data(self) -> None:
        mem = metrics.get_memory()
        bar = CpuPanel._bar(mem["percent"])
        lines = [
            f"[b]RAM[/b]  {bar}  {mem['percent']}%",
            "",
            f"Total:     {mem['total_gb']} GiB",
            f"Usada:     {mem['used_gb']} GiB",
            f"Disponible:{mem['available_gb']} GiB",
        ]
        self.update("\n".join(lines))


class DiskPanel(Static):
    """Panel de discos: uso por partición y velocidad de lectura/escritura."""

    def on_mount(self) -> None:
        self._prev_io = None
        self.update_data()
        self.set_interval(2, self.update_data)

    def update_data(self) -> None:
        disks = metrics.get_disks()
        lines = ["[b]DISCOS[/b]", ""]

        for part in disks["partitions"]:
            bar = CpuPanel._bar(part["percent"], width=20)
            lines.append(f"{part['mountpoint']} ({part['device']})")
            lines.append(f"  {bar} {part['percent']}%   {part['used_gb']}/{part['total_gb']} GiB")

        io = disks["io"]
        if self._prev_io is not None:
            read_speed = max(0, io["read_bytes"] - self._prev_io["read_bytes"]) / 2 / 1024
            write_speed = max(0, io["write_bytes"] - self._prev_io["write_bytes"]) / 2 / 1024
            lines.append("")
            lines.append(f"IO:  lectura {read_speed:7.1f} KiB/s   escritura {write_speed:7.1f} KiB/s")
        self._prev_io = io

        self.update("\n".join(lines))


class NetworkPanel(Static):
    """Panel de red / wifi."""

    def on_mount(self) -> None:
        self._prev = {}
        self.update_data()
        self.set_interval(2, self.update_data)

    def update_data(self) -> None:
        net = metrics.get_network()
        lines = ["[b]RED[/b]", ""]

        for iface in net["interfaces"]:
            name = iface["name"]
            recv, sent = iface["bytes_recv"], iface["bytes_sent"]
            prev = self._prev.get(name, (recv, sent))
            down_speed = max(0, recv - prev[0]) / 2 / 1024  # KiB/s (intervalo=2s)
            up_speed = max(0, sent - prev[1]) / 2 / 1024
            self._prev[name] = (recv, sent)
            lines.append(f"{name}:")
            lines.append(f"  ↓ {down_speed:7.1f} KiB/s   ↑ {up_speed:7.1f} KiB/s")

        if net["wifi"]:
            lines.append("")
            lines.append(f"WiFi ({net['wifi']['interface']}): calidad {net['wifi']['quality']}")

        self.update("\n".join(lines))


class ServicesPanel(Static):
    """Panel de servicios systemd + contenedores Docker, en tabla navegable."""

    def compose(self) -> ComposeResult:
        yield DataTable(id="services-table")

    def on_mount(self) -> None:
        table = self.query_one(DataTable)
        table.add_columns("Tipo", "Nombre", "Estado")
        table.cursor_type = "row"
        self.update_data()
        self.set_interval(3, self.update_data)

    def update_data(self) -> None:
        table = self.query_one(DataTable)
        table.clear()
        data = metrics.get_services()

        for svc in data["systemd"]:
            color = "green" if svc["active"] == "active" else "red"
            table.add_row("systemd", svc["name"], f"[{color}]{svc['active']}[/{color}]")

        for c in data["docker"]:
            color = "green" if c["status"].startswith("Up") else "red"
            table.add_row("docker", c["name"], f"[{color}]{c['status']}[/{color}]")


class ServerMonitorApp(App):
    """App principal."""

    CSS = """
    Screen {
        layout: vertical;
    }
    #top-row {
        height: 40%;
    }
    #bottom-row {
        height: 60%;
    }
    CpuPanel, MemPanel, DiskPanel, NetworkPanel {
        border: round $primary;
        padding: 1 2;
        width: 1fr;
        height: 100%;
    }
    ServicesPanel {
        border: round $primary;
        padding: 1 2;
        height: 100%;
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
            yield ServicesPanel()
        yield Footer()


def main():
    ServerMonitorApp().run()


if __name__ == "__main__":
    main()
