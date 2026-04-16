"""代理进程管理：启动、停止、状态检查。"""

from collections import deque
import ctypes
from ctypes import wintypes
import json
import os
import platform
import signal
import socket
import subprocess
import sys
import time
from pathlib import Path
from typing import Any, List, Optional, Tuple

from .constants import DEFAULT_PROXY_PORT, PROXY_CONFIG, PROXY_LOG, PROXY_PID
from .storage import clear_proxy_config, load_proxy_config, save_proxy_config

# 检测操作系统
IS_WINDOWS = platform.system() == "Windows"
PID_FILE_VERSION = 1


def wait_for_port(port: int, timeout: float = 3.0) -> bool:
    """轮询等待端口就绪。

    Args:
        port: 要检查的端口号
        timeout: 超时时间（秒）

    Returns:
        端口是否在超时时间内就绪
    """
    start_time = time.time()
    while time.time() - start_time < timeout:
        try:
            with socket.create_connection(("localhost", port), timeout=0.5):
                return True
        except (ConnectionRefusedError, socket.timeout, OSError):
            time.sleep(0.1)
    return False


def wait_for_proxy_ready(
    process: subprocess.Popen,
    ready_file: Path,
    port: int,
    timeout: float = 3.0,
) -> bool:
    """等待代理子进程写入启动握手文件。"""
    start_time = time.time()
    while time.time() - start_time < timeout:
        if ready_file.exists():
            try:
                ready_info = json.loads(ready_file.read_text("utf-8"))
            except (json.JSONDecodeError, OSError):
                time.sleep(0.1)
                continue

            return (
                ready_info.get("pid") == process.pid
                and ready_info.get("port") == port
            )

        if process.poll() is not None:
            return False

        time.sleep(0.1)

    return False


def _process_start_marker(pid: int) -> Optional[str]:
    """读取进程启动标识，用于检测 PID 复用。"""
    if IS_WINDOWS:
        try:
            output = subprocess.check_output(
                [
                    "wmic",
                    "process",
                    "where",
                    f"ProcessId={pid}",
                    "get",
                    "CreationDate",
                    "/value",
                ],
                text=True,
                stderr=subprocess.DEVNULL,
                timeout=1,
            )
        except (OSError, subprocess.SubprocessError):
            return None
        for line in output.splitlines():
            if line.startswith("CreationDate="):
                value = line.partition("=")[2].strip()
                return f"windows:{value}" if value else None
        return None

    proc_stat = Path(f"/proc/{pid}/stat")
    if proc_stat.exists():
        try:
            stat_text = proc_stat.read_text("utf-8")
            close_paren = stat_text.rfind(")")
            fields = stat_text[close_paren + 2:].split()
            if len(fields) >= 20:
                return f"linux:{fields[19]}"
        except OSError:
            pass

    try:
        output = subprocess.check_output(
            ["ps", "-p", str(pid), "-o", "lstart="],
            text=True,
            stderr=subprocess.DEVNULL,
            timeout=1,
        ).strip()
    except (OSError, subprocess.SubprocessError):
        return None
    return f"ps:{output}" if output else None


def _process_command(pid: int) -> Optional[str]:
    """读取进程命令行，用于兼容旧 PID 文件和额外校验。"""
    if IS_WINDOWS:
        try:
            output = subprocess.check_output(
                [
                    "wmic",
                    "process",
                    "where",
                    f"ProcessId={pid}",
                    "get",
                    "CommandLine",
                    "/value",
                ],
                text=True,
                stderr=subprocess.DEVNULL,
                timeout=1,
            )
        except (OSError, subprocess.SubprocessError):
            return None
        for line in output.splitlines():
            if line.startswith("CommandLine="):
                return line.partition("=")[2].strip() or None
        return None

    try:
        return subprocess.check_output(
            ["ps", "-p", str(pid), "-ww", "-o", "command="],
            text=True,
            stderr=subprocess.DEVNULL,
            timeout=1,
        ).strip() or None
    except (OSError, subprocess.SubprocessError):
        return None


def _command_text(command: Any) -> str:
    """将命令行记录转换为可匹配文本。"""
    if isinstance(command, (list, tuple)):
        return " ".join(str(part) for part in command)
    return str(command or "")


def _is_proxy_command(command: Any) -> bool:
    """判断命令行是否看起来是 ccprofile 代理子进程。"""
    command_text = _command_text(command).replace("\\", "/")
    config_path = str(PROXY_CONFIG).replace("\\", "/")
    proxy_path = str(Path(__file__).parent / "proxy.py").replace("\\", "/")

    has_config = config_path in command_text
    is_frozen_proxy = "--_internal-proxy" in command_text
    is_source_proxy = proxy_path in command_text or "/proxy.py" in command_text
    return has_config and (is_frozen_proxy or is_source_proxy)


def read_pid_info() -> Optional[dict]:
    """读取代理 PID 文件，兼容旧版纯数字格式。"""
    if not PROXY_PID.exists():
        return None
    try:
        text = PROXY_PID.read_text("utf-8").strip()
    except OSError:
        return None

    if not text:
        return None

    try:
        parsed = json.loads(text)
    except json.JSONDecodeError:
        try:
            return {"pid": int(text)}
        except ValueError:
            return None

    if isinstance(parsed, int):
        return {"pid": parsed}
    if isinstance(parsed, dict):
        try:
            pid = int(parsed.get("pid"))
        except (TypeError, ValueError):
            return None
        parsed["pid"] = pid
        return parsed
    return None


def read_pid() -> Optional[int]:
    """读取代理进程 PID。"""
    pid_info = read_pid_info()
    if not pid_info:
        return None
    return pid_info["pid"]


def write_pid_info(pid: int, command: List[str]) -> None:
    """写入代理进程 PID 和启动指纹。"""
    pid_info = {
        "version": PID_FILE_VERSION,
        "pid": pid,
        "pgid": None,
        "start_marker": _process_start_marker(pid),
        "command": command,
        "created_at": time.time(),
    }
    if not IS_WINDOWS:
        try:
            pid_info["pgid"] = os.getpgid(pid)
        except (OSError, ProcessLookupError):
            pass

    PROXY_PID.write_text(json.dumps(pid_info, indent=2, ensure_ascii=False) + "\n")


def is_process_running(pid: int) -> bool:
    """检查进程是否运行中。"""
    if pid <= 0:
        return False

    if IS_WINDOWS:
        process_query_limited_information = 0x1000
        error_access_denied = 5
        still_active = 259

        kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
        kernel32.OpenProcess.argtypes = [
            wintypes.DWORD,
            wintypes.BOOL,
            wintypes.DWORD,
        ]
        kernel32.OpenProcess.restype = wintypes.HANDLE
        kernel32.GetExitCodeProcess.argtypes = [
            wintypes.HANDLE,
            ctypes.POINTER(wintypes.DWORD),
        ]
        kernel32.GetExitCodeProcess.restype = wintypes.BOOL
        kernel32.CloseHandle.argtypes = [wintypes.HANDLE]
        kernel32.CloseHandle.restype = wintypes.BOOL

        handle = kernel32.OpenProcess(
            process_query_limited_information,
            False,
            pid,
        )
        if not handle:
            return ctypes.get_last_error() == error_access_denied

        try:
            exit_code = wintypes.DWORD()
            if not kernel32.GetExitCodeProcess(handle, ctypes.byref(exit_code)):
                return False
            return exit_code.value == still_active
        finally:
            kernel32.CloseHandle(handle)

    try:
        os.kill(pid, 0)  # 发送空信号，不杀死进程
        return True
    except (OSError, ProcessLookupError):
        return False


def is_recorded_proxy_process(pid_info: dict) -> bool:
    """确认 PID 文件指向的仍是当前 ccprofile 代理进程。"""
    pid = pid_info["pid"]
    if not is_process_running(pid):
        return False

    stored_marker = pid_info.get("start_marker")
    if stored_marker:
        current_marker = _process_start_marker(pid)
        if current_marker != stored_marker:
            return False

    current_command = _process_command(pid)
    if current_command is not None:
        return _is_proxy_command(current_command)

    return bool(stored_marker)


def proxy_status() -> Tuple[bool, Optional[int], Optional[dict]]:
    """检查代理进程状态。

    Returns:
        (is_running, pid, config)
        - is_running: 代理是否运行中
        - pid: 进程 PID（如果存在）
        - config: 代理配置（如果存在）
    """
    pid_info = read_pid_info()
    pid = pid_info["pid"] if pid_info else None
    config = load_proxy_config()

    if pid and pid_info and is_recorded_proxy_process(pid_info):
        return True, pid, config

    # PID 文件存在但进程不运行，或 PID 已复用，清理
    if pid or PROXY_PID.exists():
        try:
            PROXY_PID.unlink()
        except OSError:
            pass

    return False, None, config


def cleanup_failed_start(process: subprocess.Popen, ready_file: Path):
    """清理启动失败时写入的运行时文件，并停止仍在运行的子进程。"""
    if process.poll() is None:
        try:
            if IS_WINDOWS:
                process.terminate()
            else:
                os.killpg(os.getpgid(process.pid), signal.SIGTERM)
            process.wait(timeout=1)
        except subprocess.TimeoutExpired:
            try:
                if IS_WINDOWS:
                    process.kill()
                else:
                    os.killpg(os.getpgid(process.pid), signal.SIGKILL)
                process.wait(timeout=1)
            except (OSError, ProcessLookupError, subprocess.TimeoutExpired):
                pass
        except (OSError, ProcessLookupError):
            pass

    if read_pid() == process.pid:
        try:
            PROXY_PID.unlink()
        except OSError:
            pass

    try:
        ready_file.unlink()
    except OSError:
        pass

    clear_proxy_config()


def start_proxy(config: dict) -> bool:
    """启动代理进程。

    Args:
        config: 代理配置字典（包含 port 和 model_mapping）

    Returns:
        是否成功启动
    """
    # 检查是否已有运行中的代理
    is_running, pid, _ = proxy_status()
    if is_running:
        print(f"代理已在运行中 (PID: {pid})")
        return True

    # 保存代理配置
    port = config.get("port", DEFAULT_PROXY_PORT)
    config["port"] = port
    save_proxy_config(config)
    ready_file = PROXY_CONFIG.with_name(
        f"{PROXY_CONFIG.stem}.{os.getpid()}.{int(time.time() * 1000)}.ready"
    )

    # 日志文件路径
    log_path = PROXY_LOG
    log_path.parent.mkdir(parents=True, exist_ok=True)

    # 打开日志文件
    # 注意：Popen 会继承文件描述符，父进程在此关闭文件对象不会影响子进程
    log_file = open(log_path, "a")

    process = None
    try:
        # 准备子进程参数
        popen_kwargs = {
            "stdout": log_file,
            "stderr": log_file,
            "stdin": subprocess.DEVNULL,
        }

        # Windows 不支持 start_new_session
        if not IS_WINDOWS:
            popen_kwargs["start_new_session"] = True  # noqa: SIM115

        # 构建启动命令
        if getattr(sys, "frozen", False):
            # PyInstaller 打包模式：重新调用自身并附带 --_internal-proxy 标志
            cmd = [
                sys.executable,
                "--_internal-proxy",
                "-c",
                str(PROXY_CONFIG),
                "--ready-file",
                str(ready_file),
            ]
        else:
            # 源码模式：直接用 Python 运行 proxy.py
            module_path = Path(__file__).parent / "proxy.py"
            cmd = [
                sys.executable,
                str(module_path),
                "-c",
                str(PROXY_CONFIG),
                "--ready-file",
                str(ready_file),
            ]

        # 启动代理进程，传递配置文件路径
        process = subprocess.Popen(cmd, **popen_kwargs)

        # 关闭日志文件句柄（子进程已继承文件描述符）
        # 这很重要：子进程持有了独立的 fd，父进程关闭它的文件对象不会影响子进程的写入
        log_file.close()

        # 写入 PID 文件
        write_pid_info(process.pid, cmd)

        # 等待子进程确认自己已绑定端口，避免误认已有监听进程
        if wait_for_proxy_ready(process, ready_file, port, timeout=3):
            try:
                ready_file.unlink()
            except OSError:
                pass
            print(f"代理已启动 (PID: {process.pid}), 端口: {port}")
            return True
        else:
            exit_code = process.poll()
            if exit_code is None:
                print(f"错误: 代理启动超时，未收到子进程就绪信号 (端口: {port})", file=sys.stderr)
            else:
                print(
                    f"错误: 代理子进程已退出 (退出码: {exit_code})，端口 {port} 可能已被占用",
                    file=sys.stderr,
                )
            cleanup_failed_start(process, ready_file)
            return False

    except Exception as e:
        if not log_file.closed:
            log_file.close()  # 确保异常时也关闭文件
        if process is not None:
            cleanup_failed_start(process, ready_file)
        else:
            try:
                ready_file.unlink()
            except OSError:
                pass
            clear_proxy_config()
        print(f"错误: 启动代理失败: {e}", file=sys.stderr)
        return False


def stop_proxy(quiet: bool = False) -> bool:
    """停止代理进程。

    Returns:
        是否成功停止（如果没有运行中的代理也返回 True）
    """
    pid_info = read_pid_info()
    pid = pid_info["pid"] if pid_info else None
    if not pid:
        if not quiet:
            print("代理未运行")
        try:
            PROXY_PID.unlink()
        except OSError:
            pass
        clear_proxy_config()  # 清理可能残留的配置文件
        return True

    if not is_process_running(pid):
        if not quiet:
            print(f"代理进程 (PID: {pid}) 未运行，清理 PID 文件")
        try:
            PROXY_PID.unlink()
        except OSError:
            pass
        clear_proxy_config()  # 清理可能残留的配置文件
        return True

    if not is_recorded_proxy_process(pid_info):
        if not quiet:
            print(f"代理 PID 文件已过期或不匹配 (PID: {pid})，已清理")
        try:
            PROXY_PID.unlink()
        except OSError:
            pass
        clear_proxy_config()
        return True

    try:
        # 尝试优雅关闭（SIGTERM）
        if IS_WINDOWS:
            os.kill(pid, signal.SIGTERM)  # Windows: TerminateProcess
        else:
            pgid = pid_info.get("pgid")
            os.killpg(pgid or os.getpgid(pid), signal.SIGTERM)  # Unix: kill process group
        time.sleep(0.5)

        # 如果还在运行，强制关闭
        if is_process_running(pid) and is_recorded_proxy_process(pid_info):
            if IS_WINDOWS:
                os.kill(pid, signal.SIGKILL)  # Windows: TerminateProcess
            else:
                pgid = pid_info.get("pgid")
                os.killpg(pgid or os.getpgid(pid), signal.SIGKILL)  # Unix: kill process group
            time.sleep(0.1)

        # 清理 PID 文件
        try:
            PROXY_PID.unlink()
        except OSError:
            pass

        # 清理代理配置文件（包含明文 API 密钥）
        clear_proxy_config()

        if not quiet:
            print(f"代理已停止 (PID: {pid})")
        return True

    except (OSError, ProcessLookupError) as e:
        print(f"错误: 停止代理失败: {e}", file=sys.stderr)
        return False


def get_proxy_info() -> dict:
    """获取代理信息，用于显示。

    Returns:
        包含代理状态信息的字典
    """
    is_running, pid, config = proxy_status()

    info = {
        "running": is_running,
        "pid": pid,
        "config": config,
    }

    if config:
        info["port"] = config.get("port", DEFAULT_PROXY_PORT)
        if "model_mapping" in config:
            mapping = []
            for slot, target in config["model_mapping"].items():
                provider = target.get("provider", "?")
                model = target.get("model", "?")
                mapping.append(f"{slot} → {provider}/{model}")
            info["mapping"] = mapping

    return info


def show_proxy_logs(lines: int = 50):
    """显示代理日志的最后 N 行。

    Args:
        lines: 要显示的行数
    """
    if not PROXY_LOG.exists():
        print("代理日志文件不存在。")
        return

    try:
        recent_lines = deque(maxlen=max(lines, 0))
        total_lines = 0
        with PROXY_LOG.open("r", encoding="utf-8", errors="replace") as f:
            for line in f:
                total_lines += 1
                if lines > 0:
                    recent_lines.append(line.rstrip("\n"))

        print(f"代理日志 ({PROXY_LOG}) - 最后 {len(recent_lines)} 行:")
        print("-" * 60)
        for line in recent_lines:
            print(line)
        print("-" * 60)
        print(f"共 {total_lines} 行日志。")

    except Exception as e:
        print(f"错误: 读取日志文件失败: {e}", file=sys.stderr)
