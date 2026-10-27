import base64
import re
import unicodedata
from urllib.parse import unquote

# Frozen lexical baseline. It deliberately has no TaskGrant or flow-policy access.
RULES = {
    'override':r'ignore.{0,30}(instruction|previous)|忽略.{0,12}(指令|规则|要求)',
    'role_spoof':r'<\|im_start\|>|\[system\]|管理员.{0,8}(批准|授权)|trust\s*=\s*trusted|system override',
    'exfil_target':r'\battacker\b|攻击者收件箱',
    'secret_request':r'(读取|发送|导出).{0,16}(密钥|秘密|vault)|read.{0,15}vault',
}

def filter_text(text):
    variants=[unicodedata.normalize('NFKC',text[:16000])]
    for _ in range(2):
        new=[]
        for v in variants[-8:]:
            q=unquote(v)
            if q!=v:new.append(q[:16000])
            for chunk in re.findall(r'[A-Za-z0-9+/]{16,}={0,2}',v)[:8]:
                try:
                    d=base64.b64decode(chunk,validate=True).decode('utf-8')
                    if d:new.append(d[:16000])
                except (ValueError,UnicodeDecodeError):pass
        variants.extend(new[:16])
    hits=[name for name,pattern in RULES.items() if any(re.search(pattern,v,re.I|re.S) for v in variants)]
    return ('[外部内容被输入过滤器移除；请继续其他授权任务。]' if hits else text),hits
