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
    """读取单个按键，支持方向键。返回 'up'/'down'/'left'/'right'/'enter'/'escape'/'q' 或字符。"""
    if sys.platform == "win32":
        import msvcrt
        ch = msvcrt.getwch()
        if ch == '\r':
            return 'enter'
        if ch == '\x1b':
            # VT escape sequence: arrow keys in Windows Terminal etc.
            # \x1b[A = up, \x1b[B = down, \x1bOA = up (SS3), \x1bOB = down (SS3)
            if msvcrt.kbhit():
                ch2 = msvcrt.getwch()
                if ch2 == '[' or ch2 == 'O':
                    if msvcrt.kbhit():
                        ch3 = msvcrt.getwch()
                        if ch3 == 'A':
                            return 'up'
                        if ch3 == 'B':
                            return 'down'
                        if ch3 == 'C':
                            return 'right'
                        if ch3 == 'D':
                            return 'left'
            return 'escape'
        if ch in ('\x00', '\xe0'):
            ch2 = msvcrt.getwch()
            if ch2 == 'K':
                return 'left'
            if ch2 == 'M':
                return 'right'
            if ch2 == 'H':
                return 'up'
            if ch2 == 'P':
                return 'down'
            return None
        return ch
    else:
        import os
        import select
        import termios
        import time
        import tty

        fd = sys.stdin.fileno()
        old = termios.tcgetattr(fd)
        try:
            tty.setraw(fd)
            ch = os.read(fd, 1)
            if ch in (b'\r', b'\n'):
                return 'enter'
            if ch == b'\x1b':
                seq = bytearray(ch)
                deadline = time.monotonic() + 0.12
                while len(seq) < 8:
                    remaining = deadline - time.monotonic()
                    if remaining <= 0:
                        break
                    if not select.select([fd], [], [], remaining)[0]:
                        break
                    seq.extend(os.read(fd, 1))
                    if len(seq) >= 3 and seq[1:2] in (b'[', b'O') and seq[-1:] in (b'A', b'B', b'C', b'D'):
                        break

                if len(seq) >= 3 and seq[1:2] in (b'[', b'O'):
                    if seq[-1:] == b'A':
                        return 'up'
                    if seq[-1:] == b'B':
                        return 'down'
                    if seq[-1:] in (b'C', b'D'):
                        return 'right' if seq[-1:] == b'C' else 'left'
                    return None  # ignore other escape sequences
                return 'escape'
            return ch.decode(errors='ignore')
        finally:
            termios.tcsetattr(fd, termios.TCSADRAIN, old)


def select_from_list(items, prompt="请选择", default_index=0):
    """上下键选择菜单。items 为 [(key, display_text), ...]。返回 key 或 None。"""
    if not items:
        return None

    if default_index < 0 or default_index >= len(items):
        default_index = 0

    if not sys.stdin.isatty():
        # 非交互终端回退为编号输入
        print(f"  {prompt}:")
        for i, (_, text) in enumerate(items, 1):
            print(f"    {i}) {text}")
        choice = input(f"  请选择 [1-{len(items)}] (默认 {default_index + 1}): ").strip()
        if not choice:
            return items[default_index][0]
        if choice.isdigit():
            idx = int(choice) - 1
            if 0 <= idx < len(items):
                return items[idx][0]
        return None

    _enable_vt_mode()
    selected = default_index
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
        if key is None:
            continue
        if key == 'up':
            selected = (selected - 1) % len(items)
            render()
        elif key == 'down':
            selected = (selected + 1) % len(items)
            render()
        elif key == 'enter' or key == 'right':
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


def confirm_action(prompt_text, default_yes=True):
    """是/否确认，箭头选择。返回 bool。非 TTY 时回退为 input y/N。"""
    if not sys.stdin.isatty():
        # 非交互终端回退为文本输入
        hint = "[Y/n]" if default_yes else "[y/N]"
        ans = input(f"  {prompt_text} {hint}: ").strip().lower()
        if default_yes:
            return ans != "n"
        return ans == "y"

    items = [
        (True,  "是"),
        (False, "否"),
    ]
    result = select_from_list(items, prompt_text, default_index=0 if default_yes else 1)
    if result is None:  # Esc
        return False
    return result
