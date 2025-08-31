import hashlib
import time

# 定义用于编码 0 和 1 的零宽字符
ZERO_WIDTH_ZERO = "\u200b"  # 零宽空格 (Zero-Width Space)
ZERO_WIDTH_ONE = "\u200c"   # 零宽非连接符 (Zero-Width Non-Joiner)

def text_to_binary(text: str) -> str:
    """将文本转换为二进制字符串"""
    return ''.join(format(ord(char), '08b') for char in text)

def binary_to_text(binary: str) -> str:
    """将二进制字符串转换回文本"""
    chars = [binary[i:i+8] for i in range(0, len(binary), 8)]
    return ''.join(chr(int(char, 2)) for char in chars)

def encode_watermark(binary_watermark: str) -> str:
    """将二进制水印编码为零宽字符串"""
    return binary_watermark.replace('0', ZERO_WIDTH_ZERO).replace('1', ZERO_WIDTH_ONE)

def decode_watermark_from_text(text: str) -> str:
    """从包含零宽字符的文本中解码出二进制水印"""
    binary_watermark = ""
    for char in text:
        if char == ZERO_WIDTH_ZERO:
            binary_watermark += '0'
        elif char == ZERO_WIDTH_ONE:
            binary_watermark += '1'
    return binary_watermark

def generate_watermark_content(user_id: str = "anonymous") -> str:
    """
    生成包含时间戳和用户标识的水印内容
    格式: timestamp|user_id|hash
    """
    timestamp = str(int(time.time()))
    # 为了简化，我们只哈希时间戳和用户ID的前8位
    signature = hashlib.sha256(f"{timestamp}|{user_id}".encode()).hexdigest()[:8]
    return f"{timestamp}|{user_id}|{signature}"

class WatermarkInjector:
    """
    负责在文本块中注入水印的类
    """
    def __init__(self, watermark: str, interval: int = 5):
        """
        Args:
            watermark (str): 已经编码好的零宽字符水印
            interval (int): 每隔多少个可见字符插入一个水印字符
        """
        self.watermark = watermark
        self.interval = interval
        self.watermark_idx = 0
        self.char_count = 0

    def inject(self, text_chunk: str) -> str:
        """向文本块中注入水印字符"""
        injected_text = ""
        for char in text_chunk:
            injected_text += char
            # 忽略空白字符，只在可见字符后插入
            if not char.isspace():
                self.char_count += 1
            
            if self.char_count % self.interval == 0 and self.char_count > 0:
                if self.watermark_idx < len(self.watermark):
                    injected_text += self.watermark[self.watermark_idx]
                    self.watermark_idx += 1
        return injected_text

# --- 用于验证的辅助函数 ---
def verify_watermark(text_with_watermark: str) -> dict:
    """
    从文本中提取并验证水印
    """
    binary_data = decode_watermark_from_text(text_with_watermark)
    if not binary_data:
        return {"valid": False, "reason": "No watermark found."}
    
    try:
        decoded_text = binary_to_text(binary_data)
        parts = decoded_text.split('|')
        if len(parts) != 3:
            return {"valid": False, "reason": "Invalid watermark format."}
        
        timestamp_str, user_id, signature = parts
        
        # 验证签名
        expected_signature = hashlib.sha256(f"{timestamp_str}|{user_id}".encode()).hexdigest()[:8]
        
        if signature == expected_signature:
            return {
                "valid": True,
                "timestamp": int(timestamp_str),
                "user_id": user_id
            }
        else:
            return {
                "valid": False,
                "reason": "Signature mismatch.",
                "data": {"timestamp": int(timestamp_str), "user_id": user_id, "signature": signature}
            }
    except Exception as e:
        return {"valid": False, "reason": f"Decoding error: {e}"}
