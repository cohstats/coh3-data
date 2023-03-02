import struct
import texture2ddecoder
from PIL import Image
import zlib
import base64
from dataclasses import dataclass

def print_bytes_data(byte_data):
    for i in range(0, len(byte_data), 4):
        try:
            int32 = struct.unpack("<i",byte_data[i:i+4])[0]
        except:
            int32 = -1
            pass
        print(byte_data[i:i+4],end='')
        print('\t\t\t',end="")
        print(int32)

@dataclass
class Positions:
    idx_start: int
    idx_end:   int
    
def get_data_positions(buffer, data):
    
    found_pos = buffer.find(data)
    return Positions(found_pos, found_pos+len(data))
    

file_path = "C:/coh-data/coh3/in/assault_engineer_us_portrait.rrtex"
with open(file_path, "rb") as f:
    
    # Read the entire file into a byte buffer
    buff = f.read()
    print(f"RRTEX \t\t\t:{len(buff)} bytes")
    
    pos_datatman = get_data_positions(buff, b"DATATMAN") 
    pos_datatdat = get_data_positions(buff, b"DATATDAT")
    
    slice_datatman = buff[pos_datatman.idx_end+12 : pos_datatdat.idx_start]
    slice_datatdat = buff[pos_datatdat.idx_end:]
     
    # Unpack the width and height from the byte data
    _, width, height, _, _, textureCompression, mipCount, _, mipTextureCount , sizeUncompressed , sizeCompressed  = struct.unpack("<iiiiiiiiiii", slice_datatman[:44])
    
    
    print(f"DATATDAT\t\t:{len(slice_datatdat)} bytes")
    

    try:

        Decompressor = zlib.decompressobj()
        # get the first decompressed chunk
        chunk = Decompressor.decompress(slice_datatdat[16:])
        # unused compressed data
        unused_data = Decompressor.unused_data;


        decompressed_chunks = []                # all decompressed chunks
        decompressed_chunks.append(chunk[16:])  # first chunk is shifted
        
        # while there are still compressed data, try decompressing them
        while len(unused_data) > 0:
            NextDecompressor = zlib.decompressobj()
            chunk = NextDecompressor.decompress(unused_data)
            decompressed_chunks.append(chunk)
            unused_data = NextDecompressor.unused_data;
        
        # assamble decompressed_data from decompressed_chunks
        decompressed_data = b''
        for chunk in decompressed_chunks:
            decompressed_data += chunk
        
        print(f"DECOMPRESSED\t:{len(decompressed_data)} bytes")
        
        decoded_data= texture2ddecoder.decode_bc7(decompressed_data, width, height)
        dec_img = Image.frombytes("RGBA", (width, height), decoded_data, 'raw', ("BGRA"))
        dec_img.save("C:/coh-data/coh3/out/assault_engineer_us_portrait.tga")
    except Exception as e:
        print(e)
        pass
    