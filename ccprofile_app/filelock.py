"""跨平台文件锁支持。"""

import sys
from pathlib import Path

try:
    import fcntl
    HAS_FLOCK = True
except ImportError:
    HAS_FLOCK = False

try:
    import msvcrt
    HAS_MSVCRT = True
except ImportError:
    HAS_MSVCRT = False


class FileLock:
    """跨平台文件锁上下文管理器。

    使用方法:
        with FileLock(file_path, exclusive=True):
            # 执行文件读写操作
            pass
    """

    def __init__(self, file_path, exclusive=True):
        """初始化文件锁。

        Args:
            file_path: 要保护的数据文件路径
            exclusive: 是否为排他锁（True）或共享锁（False）
        """
        self.file_path = Path(file_path)
        self.lock_path = self.file_path.with_name(self.file_path.name + ".lock")
        self.exclusive = exclusive
        self._file = None

    def __enter__(self):
        """进入上下文，获取文件锁。"""
        self.lock_path.parent.mkdir(parents=True, exist_ok=True)
        self._file = open(self.lock_path, "a+b")
        self._file.seek(0)
        self._acquire_lock()
        return self._file

    def __exit__(self, exc_type, exc_val, exc_tb):
        """退出上下文，释放文件锁。"""
        try:
            self._release_lock()
        finally:
            if self._file:
                self._file.close()
                self._file = None

    def _acquire_lock(self):
        """获取文件锁。"""
        if sys.platform == 'win32':
            if HAS_MSVCRT:
                # Windows: 使用 msvcrt.locking
                msvcrt.locking(self._file.fileno(), msvcrt.LK_LOCK, 1)
        else:
            if HAS_FLOCK:
                # Unix: 使用 fcntl.flock
                flag = fcntl.LOCK_EX if self.exclusive else fcntl.LOCK_SH
                fcntl.flock(self._file.fileno(), flag)

    def _release_lock(self):
        """释放文件锁。"""
        if sys.platform == 'win32':
            if HAS_MSVCRT:
                msvcrt.locking(self._file.fileno(), msvcrt.LK_UNLCK, 1)
        else:
            if HAS_FLOCK:
                fcntl.flock(self._file.fileno(), fcntl.LOCK_UN)
