"""Send a Wake-on-LAN magic packet from a device on the target LAN."""
import argparse,socket

def make_packet(mac:str)->bytes:
    compact=mac.replace(":","").replace("-","").replace(".","").strip()
    if len(compact)!=12: raise ValueError("MAC must contain 12 hexadecimal digits")
    raw=bytes.fromhex(compact); return b"\xff"*6+raw*16

def main():
    p=argparse.ArgumentParser(); p.add_argument("mac"); p.add_argument("--broadcast",default="255.255.255.255"); p.add_argument("--port",type=int,default=9); a=p.parse_args()
    with socket.socket(socket.AF_INET,socket.SOCK_DGRAM) as s:
        s.setsockopt(socket.SOL_SOCKET,socket.SO_BROADCAST,1); s.sendto(make_packet(a.mac),(a.broadcast,a.port))
    print("Magic packet sent; wake is not guaranteed.")
if __name__=="__main__": main()
