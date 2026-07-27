import socket
import threading

# Server ချိန်ညှိချက်များ
HOST = '0.0.0.0'
PORT = 5000

# ချိတ်ဆက်လာသမျှ client များကို မှတ်သားရန် list
clients = []
clients_lock = threading.Lock()

def handle_client(conn, addr):
    print(f"[+] ချိတ်ဆက်လာသူ: {addr}")
    with clients_lock:
        clients.append(conn)
        
    try:
        while True:
            # Data ကို လက်ခံခြင်း (အရွယ်အစား 4096 bytes)
            data = conn.recv(4096)
            if not data:
                break
            
            # လက်ခံရရှိတဲ့ data ကို ချိတ်ဆက်ထားသမျှ client အားလုံးဆီသို့ ဖြန့်ဝေပေးခြင်း (Broadcast)
            with clients_lock:
                for client in clients:
                    if client != conn:  *# ပို့လိုက်တဲ့သူဆီ ပြန်မပို့ဘဲ ကျန်တဲ့သူတွေဆီ ပို့ရန်*
                        try:
                            client.sendall(data)
                        except:
                            pass
    except Exception as e:
        print(f"[-] အမှားအယွင်းရှိသည် {addr}: {e}")
    finally:
        with clients_lock:
            if conn in clients:
                clients.remove(conn)
        conn.close()
        print([-] ထွက်သွားသူ: {addr})

def start_server():
    server = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    server.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
    server.bind((HOST, PORT))
    server.listen(5)
    print(f"[*] Server စတင်အလုပ်လုပ်နေပါပြီ (Port: {PORT})...")
    
    while True:
        conn, addr = server.accept()
        thread = threading.Thread(target=handle_client, args=(conn, addr))
        thread.daemon = True
        thread.start()

if __name__ == '__main__':
    start_server()
                          
