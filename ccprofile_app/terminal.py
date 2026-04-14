"""终端按键读取、列表选择、VT mode 支持。"""

import sys


def _enable_vt_mode():
    """Windows 上启用 VT100 转义序列支持。"""
    if sys.platform == "win32":
        import ctypes
        kernel32 = ctypes.windll.kernel32
        handle = kernel32.GetStdHandle(-11)  # STD_OUTPUT_HANDLE
        mode = ctypes.c_ulong()
        kernel32.GetConsoleMode(handle, ctypes.byref(mode))
        if not (mode.value & 0x0004):  # ENABLE_VIRTUAL_TERMINAL_PROCESSING
            kernel32.SetConsoleMode(handle, mode.value | 0x0004)


def _read_key():
    """读取单个按键，支持方向键。返回 'up'/'down'/'enter'/'escape'/'q' 或字符。"""
    if sys.platform == "win32":
        import msvcrt
        ch = msvcrt.getwch()
        if ch == '\r':
            return 'enter'
        if ch == '\x1b':
            return 'escape'
        if ch in ('\x00', '\xe0'):
            ch2 = msvcrt.getwch()
            if ch2 == 'H':
                return 'up'
            if ch2 == 'P':
                return 'down'
            return None
        return ch
    else:
        import termios
        import tty
        import select
        fd = sys.stdin.fileno()
        old = termios.tcgetattr(fd)
        try:
            tty.setraw(fd)
            ch = sys.stdin.read(1)
            if ch in ('\r', '\n'):
                return 'enter'
            if ch == '\x1b':
                # Use select with a short timeout to distinguish lone Esc
                # from escape sequences (which arrive as a burst)
                if select.select([sys.stdin], [], [], 0.05)[0]:
                    ch2 = sys.stdin.read(1)
                    if ch2 == '[':
                        ch3 = sys.stdin.read(1)
                        if ch3 == 'A':
                            return 'up'
                        if ch3 == 'B':
                            return 'down'
                    return 'escape'
                return 'escape'
            return ch
        finally:
            termios.tcsetattr(fd, termios.TCSADRAIN, old)


def select_from_list(items, prompt="请选择"):
    """上下键选择菜单。items 为 [(key, display_text), ...]。返回 key 或 None。"""
    if not items:
        return None

    if not sys.stdin.isatty():
        # 非交互终端回退为编号输入
        print(f"  {prompt}:")
        for i, (_, text) in enumerate(items, 1):
            print(f"    {i}) {text}")
        choice = input(f"  请选择 [1-{len(items)}]: ").strip()
        if choice.isdigit():
            idx = int(choice) - 1
            if 0 <= idx < len(items):
                return items[idx][0]
        return None

    _enable_vt_mode()
    selected = 0
    rendered = False
    line_count = len(items) + 1

    def render():
        nonlocal rendered
        if rendered:
            for _ in range(line_count):
                sys.stdout.write('\x1b[A\x1b[2K\r')
        rendered = True
        sys.stdout.write(f"  {prompt}  (\x1b[2m↑↓ 选择 · Enter 确认 · Esc 取消\x1b[0m)\n")
        for i, (_, text) in enumerate(items):
            if i == selected:
                sys.stdout.write(f"  \x1b[7m > {text}  \x1b[0m\n")
            else:
                sys.stdout.write(f"    {text}\n")
        sys.stdout.flush()

    render()

    while True:
        key = _read_key()
        if key == 'up':
            selected = (selected - 1) % len(items)
            render()
        elif key == 'down':
            selected = (selected + 1) % len(items)
            render()
        elif key == 'enter':
            for _ in range(line_count):
                sys.stdout.write('\x1b[A\x1b[2K\r')
            sys.stdout.write(f"  \x1b[1m> {items[selected][1]}\x1b[0m\n")
            sys.stdout.flush()
            return items[selected][0]
        elif key in ('escape', 'q'):
            for _ in range(line_count):
                sys.stdout.write('\x1b[A\x1b[2K\r')
            sys.stdout.write(f"  已取消\n")
            sys.stdout.flush()
            return None
