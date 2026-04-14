"""脱敏和输出格式工具。"""


def mask_token(token):
    """脱敏显示 token，保留前8后4字符。"""
    if not token or len(token) < 12:
        return "***"
    return token[:8] + "..." + token[-4:]
