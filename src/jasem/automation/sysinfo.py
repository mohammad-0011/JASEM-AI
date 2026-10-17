"""System information reporting (psutil-based)."""

from __future__ import annotations

import platform
import socket

import psutil


def system_info() -> dict:
    vm = psutil.virtual_memory()
    cpu_pct = psutil.cpu_percent(interval=0.4)
    return {
        "os": f"{platform.system()} {platform.release()} ({platform.version()})",
        "cpu_percent": cpu_pct,
        "cpu_cores": psutil.cpu_count(logical=False),
        "cpu_threads": psutil.cpu_count(logical=True),
        "cpu_freq_mhz": (psutil.cpu_freq().current if psutil.cpu_freq() else None),
        "ram_total_gb": round(vm.total / 1024 ** 3, 1),
        "ram_used_pct": vm.percent,
        "ram_available_gb": round(vm.available / 1024 ** 3, 1),
        "boot_time": psutil.boot_time(),
    }


def disk_space() -> list[dict]:
    out = []
    for part in psutil.disk_partitions(all=False):
        try:
            usage = psutil.disk_usage(part.mountpoint)
        except (OSError, PermissionError):
            continue
        out.append({
            "drive": part.mountpoint,
            "total_gb": round(usage.total / 1024 ** 3, 1),
            "free_gb": round(usage.free / 1024 ** 3, 1),
            "used_pct": usage.percent,
        })
    return out


def battery() -> dict | None:
    b = psutil.sensors_battery()
    if b is None:
        return None
    return {"percent": round(b.percent, 0), "plugged": b.power_plugged,
            "secs_left": b.secsleft}


def network_check(timeout: float = 3.0) -> dict:
    """Checks real internet reachability, not just an interface being up."""
    import httpx

    connected = False
    latency_ms = None
    try:
        import time as _t

        with httpx.Client(timeout=timeout, trust_env=False) as client:
            t0 = _t.perf_counter()
            r = client.get("https://www.msftconnecttest.com/connecttest.txt")
            latency_ms = int((_t.perf_counter() - t0) * 1000)
            connected = r.status_code == 200
    except Exception:
        connected = False
    adapters = []
    try:
        addrs = psutil.net_if_stats()
        adapters = [name for name, st in addrs.items() if st.isup]
    except Exception:
        pass
    try:
        hostname = socket.gethostname()
    except Exception:
        hostname = ""
    return {"connected": connected, "latency_ms": latency_ms,
            "active_adapters": adapters, "hostname": hostname}


def top_processes(limit: int = 12) -> list[dict]:
    procs = []
    for p in psutil.process_iter(["pid", "name", "cpu_percent", "memory_percent"]):
        try:
            info = p.info
            procs.append({
                "pid": info["pid"],
                "name": info["name"],
                "cpu": round(info["cpu_percent"] or 0.0, 1),
                "mem": round(info["memory_percent"] or 0.0, 1),
            })
        except (psutil.NoSuchProcess, psutil.AccessDenied):
            continue
    procs.sort(key=lambda x: x["cpu"], reverse=True)
    return procs[:limit]


def end_process_by_name(name: str) -> tuple[int, int]:
    """Terminate processes by exact name. Returns (killed, matched)."""
    killed = matched = 0
    for p in psutil.process_iter(["pid", "name"]):
        try:
            if (p.info["name"] or "").lower() == name.lower():
                matched += 1
                p.terminate()
                killed += 1
        except (psutil.NoSuchProcess, psutil.AccessDenied):
            continue
    return killed, matched
