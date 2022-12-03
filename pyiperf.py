#!/usr/bin/python3

# coding=utf-8
import socket
import sys
import getopt
import threading
import os
import time
import signal

MTU_overhead = 28 # ip 20 + udp 8
packet_overhead = 14 + MTU_overhead # ethernet 14

class speed_counter:
    def __init__(self):
        self.old_cnt = 0
        self.new_cnt = 0
        self.time = time.time()
    
    def count(self, num):
        self.new_cnt += num

    def read(self):
        return self.new_cnt

    def __str__(self):
        new_time = time.time()

        d_cnt = self.new_cnt - self.old_cnt
        d_time = new_time - self.time
        spd = d_cnt / d_time

        self.old_cnt = self.new_cnt
        self.time = new_time
        
        g_num = 1e9
        m_num = 1e6
        k_num = 1e3
        if spd > g_num:
            return "{:.2f}".format(spd / g_num) + " G"
        if spd > m_num:
            return "{:.2f}".format(spd / m_num) + " M"
        if spd > k_num:
            return "{:.2f}".format(spd / k_num) + " K"
        return "{:.2f}".format(spd)

class packet_counter: 
    def __init__(self, name):
        self.name = name
        self.pkt_cnt = speed_counter()
        self.bit_cnt = speed_counter()

    def count(self, msg):
        self.pkt_cnt.count(1)
        self.bit_cnt.count((len(msg) + packet_overhead) * 8)
    
    def read(self):
        return (self.pkt_cnt.read(), self.bit_cnt.read())

    def __str__(self):
        return self.name + ": " + str(self.pkt_cnt) + "pps, " + str(self.bit_cnt) + "bps"
    
        

def usage():
    print("Usage: python3 myiperf.py {-s|-c} <ip addr> <options>")
    print("       python3 myiperf.py [-h|--help]")
    print("Options:")
    print("    -s <ip addr>         Run server.")
    print("    -c <ip addr>         Run client.")
    print("    -p <port>            Set server port, the default value is 40009.")
    print("    -h, --help           Show this help.")
    print("Options for server:")
    print("    --ACK                Send an ACK for every packet, note that ")
    print("                         clients will neither wait for the lost ACK")
    print("                         nor check the content of ACK packet.")
    print("Options for client:")
    print("    -M <MTU>             Set MTU, the default value is 1300.")
    print("    -P <nthread>         Set number of threads, the default value is 1.")
    print("    -t <time>            Set time to stop (in seconds, can be a decimal), ")
    print("                         by default the process loops indefinitely.")
    


def run_server(server_socket, ACK_flag):
    old_time = time.time()
    counter = packet_counter("server")
    while True: 
        new_time = time.time()
        if new_time - old_time >= 1:
            print(counter)
            old_time = new_time
        try:
            msg, addr = server_socket.recvfrom(1500)
            counter.count(msg)
            if ACK_flag:
                pos = msg.find("#".encode('utf-8'))
                assert(pos > 0)
                server_socket.sendto(msg[:pos], addr)
        except:
            continue

force_quit = False

def run_client_tx(client_socket, server_addr, client_id, msg_len, counter):
    while not force_quit:
        msg = "{}-{}".format(client_id, counter.read()[0])
        fill_num = msg_len - len(msg)
        if fill_num <= 0:
            print("Error: message too long (MTU too small).")
            os._exit(1)
        msg = msg + "#" * fill_num
        msg = msg.encode("utf-8")
        try:
            client_socket.sendto(msg, server_addr)
            counter.count(msg)
        except:
            print("An error occured when sending to {}".format(server_addr))
            os._exit(1)

def run_client_rx(client_socket, server_addr, client_id, msg_len, counter):
    while not force_quit:
        try:
            msg, addr = client_socket.recvfrom(1500)
        except socket.timeout:
            continue
        if addr != server_addr:
            print("WARNING: Address {} mismatch.".format(addr))
            continue
        counter.count(msg)

def server_sig_handler(signum, frame):
    if signum == signal.SIGINT or signum == signal.SIGTERM:
        print("Exit.")
        os._exit(0)


def client_sig_handler(signum, frame):
    global force_quit
    if signum == signal.SIGINT or signum == signal.SIGTERM:
        if force_quit == True:
            print("Force exit.")
            os._exit(0)
        else:
            force_quit = True
            print("Exiting.")
            raise


def main():
    ip = "0.0.0.0"
    port = 40009
    MTU = 1300
    nthread = 1
    time_to_stop = -1

    try:
        opts, args = getopt.getopt(sys.argv[1:], "s:c:p:hM:P:t:", ["help", "ACK"])
    except getopt.GetoptError:
        usage()
        os._exit(1)
    
    help_flag = server_flag = client_flag = ACK_flag = False

    for opt, arg in opts:
        if opt in ["-h", "--help"]:
            help_flag = True
        elif opt == "-s":
            server_flag = True
            ip = arg
        elif opt == "-c":
            client_flag = True
            ip = arg
        elif opt == "-p":
            port = int(arg)
            assert(0 <= port and port < 65536)
        elif opt == "-M":
            MTU = int(arg)
            assert(50 <= MTU and MTU <= 1500)
        elif opt == "-P":
            nthread = int(arg)
            assert(0 < nthread and nthread <= 100)
        elif opt == "-t":
            time_to_stop = float(arg)
            assert(0 < time_to_stop and time_to_stop <= 3600)
        elif opt == "--ACK":
            ACK_flag = True
        
    if (not server_flag and not client_flag) or (server_flag and client_flag):
        usage()
        os._exit(1)
    
    server_addr = (ip, port)
    
    if server_flag:
        signal.signal(signal.SIGINT, server_sig_handler)
        signal.signal(signal.SIGTERM, server_sig_handler)

        server_socket = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        try:
            server_socket.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
            server_socket.bind(server_addr)
            server_socket.settimeout(0.1)
        except:
            print("Cannot bind {}.".format(server_addr))
            os._exit(1)

        run_server(server_socket, ACK_flag)
    else:
        signal.signal(signal.SIGINT, client_sig_handler)
        signal.signal(signal.SIGTERM, client_sig_handler)
        
        tx_counter = [packet_counter("client"+str(i)+"-TX") for i in range(nthread)]
        rx_counter = [packet_counter("client"+str(i)+"-RX") for i in range(nthread)]
        client_socket = [socket.socket(socket.AF_INET, socket.SOCK_DGRAM) for i in range(nthread)]
        for c_socket in client_socket:
            c_socket.settimeout(0.1)

        threads = [threading.Thread(target = run_client_tx, args = (client_socket[i], server_addr, i, MTU - MTU_overhead, tx_counter[i])) for i in range(nthread)]
        threads += [threading.Thread(target = run_client_rx, args = (client_socket[i], server_addr, i, MTU - MTU_overhead, rx_counter[i])) for i in range(nthread)]
        
        start_time = time.time()
        new_time = start_time

        for thread in threads:
            thread.start()
        
        global force_quit
        while not force_quit and (time_to_stop < 0 or time_to_stop > new_time - start_time):
            try:
                if time_to_stop < 0:
                    time.sleep(1)
                else:
                    time.sleep(min(time_to_stop - (new_time - start_time), 1))
            except:
                pass
            new_time = time.time()
            for i in range(nthread):
                print(tx_counter[i])
                print(rx_counter[i])

        force_quit = True
        
        for thread in threads:
            thread.join()

# 基于网络的数据报协议 UDP
# server.setsockopt(socket.SOL_SOCKET, socket.SO_RCVBUF, 1024)
# server.setsockopt(socket.SOL_SOCKET, socket.SO_SNDBUF, 1024)
main()
