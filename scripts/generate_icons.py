"""Generate simple code-native PT icons without external image tools."""
import struct
import zlib
from pathlib import Path

def png(size):
    pixels=[]
    for y in range(size):
        row=bytearray()
        for x in range(size):
            u,v=x/size,y/size
            inner=.18<u<.82 and .18<v<.82
            p=(.30<u<.36 and .33<v<.67) or (.34<u<.47 and (.33<v<.39 or .47<v<.53)) or (.45<u<.51 and .36<v<.50)
            t=(.55<u<.73 and .33<v<.39) or (.61<u<.67 and .36<v<.67)
            row.extend((23,33,11) if (p or t) else (210,247,107) if inner else (16,19,15))
        pixels.append(b'\x00'+row)
    def chunk(kind,data):return struct.pack('!I',len(data))+kind+data+struct.pack('!I',zlib.crc32(kind+data)&0xffffffff)
    return b'\x89PNG\r\n\x1a\n'+chunk(b'IHDR',struct.pack('!2I5B',size,size,8,2,0,0,0))+chunk(b'IDAT',zlib.compress(b''.join(pixels)))+chunk(b'IEND',b'')
for size in (192,512):Path(f'apps/web/public/icon-{size}.png').write_bytes(png(size))
