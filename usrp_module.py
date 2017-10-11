from typing import Dict,List
import logging
import random
import time
import queue
import socket
import itertools
import struct
from time import sleep

import wishful_upis as upis
import wishful_framework as wishful_module
from wishful_framework.classes import exceptions

__author__ = "Franco Minucci, Seyed Ali Hassani, Alessandro Chiumento"
__copyright__ = "Copyright (c) 2017, KU Leuven "
__version__ = "0.1.0"
__email__ = "franco.minucci@esat.kuleuven.be"

#Constants
_USRP_IP_ADDRESS='10.33.101.138'
_USRP_IP_PORT = 5022
# Packet format : [Header, Length byte1, Length byte0, Key, Data0, Data1,...]
Header = [250, 1, 250]
Header_length = 3
Key_Freq = 0
Key_FreqShift = 1
Key_TxGain = 2 # Max 10
Key_RxGain = 3
Key_TxSampleRate = 4
Key_StartStopUSRP = 5  # 0: Stop, 1, Start
Key_EnableDisableSI = 6  # SelfInterferance: 0: Enable, 1, 0:Disable
Key_RetuneDuplexer = 7  # 0: Enable, 1, 0:Disable
Key_CollisionDetector = 8  # b0: Reset, b1:Train, b2: FixAlpha, b3: Start
Key_DeviceAdd = 9  # 16 bits
Key_DestinationAdd = 10  # 16 bits
Key_PacketRec_CD_Test = 11  #
Key_ReceivedPacketReq = 12  # Request for the received packet
Key_IQDataReq = 13  # Request for the IQ
Key_MACSetting = 14  # b0:Payload From Host, b1: TxMAC.CD.Enable
Key_CD_Average = 15  # CD.Average Length (uint8)
Key_CD_Average_Th = 16  # CD.Average.Th (uint8)
Key_HostPayload = 21
N_Payload = 118;


# *******************************************

def double2bytearray(double_num):
    return reversed(bytearray(struct.pack("d", double_num)))

def MakePacket(Key, data):	# Make Packet: Tx frequency
    if Key <= 20:  			# Key 0-20 for setting
        try:
            data_len = 8 + len(data)    # for doubel numbers
        except:
            data_len = 9 
        H = itertools.chain(Header,[data_len & 0x00FF ,data_len >> 8 ,   Key])
        Packet = bytes(itertools.chain(H,double2bytearray(data)))
    else:
        data_len = 1 + len(data)       # for byte arrays
        H = itertools.chain(Header,[data_len & 0x00FF ,data_len >> 8 ,   Key])
        Packet = bytes(itertools.chain(H,data))
    return Packet



@wishful_module.build_module
class USRPModule(wishful_module.AgentModule):
    def __init__(self):
        super(USRPModule, self).__init__()
        self.log = logging.getLogger('USRPModule')
        self.ip_address = _USRP_IP_ADDRESS 
        self.ip_port = _USRP_IP_PORT
        self.buffer_size = 128
        self.n_payload = 118
        self.payload = bytearray(self.n_payload)
        self.interface = "usrp0"
        self.full_duplex_0 = "usrp0"
        self.rx_gain = 0
        self.tx_power = 0
        self.retune_dup = False
        self.set_cd = 'none'
        self.dev_addr = 0
        self.dst_addr = 1
        self.mac_set = 0
        self.cd_threshold = 3
        self.cd_avg_len = 10
        self.si_en_dis = False
        # Generating payload data
        for i in range(N_Payload):
            self.payload[i] = i
        s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        s.connect((self.ip_address, self.ip_port))
        s.send(MakePacket(Key_Freq, 1750000000))
        s.send(MakePacket(Key_FreqShift, -10000000))
        s.send(MakePacket(Key_TxGain, 10))
        s.send(MakePacket(Key_RxGain, 0))
        s.send(MakePacket(Key_TxSampleRate, 16000000))
        s.send(MakePacket(Key_DeviceAdd, 0))
        s.send(MakePacket(Key_DestinationAdd, 1))
        s.send(MakePacket(Key_CD_Average, 4))
        s.send(MakePacket(Key_CD_Average_Th, 3))
        s.send(MakePacket(Key_HostPayload, self.payload))
        s.close()
        
        # Set default values; These parameters should be set before start
        print("Init parameters...")

    @wishful_module.on_start()
    def start(self):
        '''
        starts the USRP
        '''
                
        s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        s.connect((self.ip_address, self.ip_port))
        s.send(MakePacket(Key_StartStopUSRP, 1))
        s.close()
        self.si_enable_disable(True)
        print('wait a moment...')
        sleep(10)
        print('USRP started')


    @wishful_module.on_exit()
    def stop(self):
        
        '''
        stops the USRP
        '''
        self.si_enable_disable(False)
        self.log.info("This function is executed on agent exit".format())
        s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        s.connect((self.ip_address, self.ip_port))
        s.send(MakePacket(Key_StartStopUSRP, 0))
        s.close()
        print('USRP halted')


    @wishful_module.bind_function(upis.radio.set_tx_power)
    def set_tx_power(self, power):
        '''
        Set the tx gain of the USRP
        '''
        if power > 10:
            power = 10
            self.log.debug("USRP power cannot be more than 10")
        if power < 1:
            power = 1
            self.log.debug("USRP power cannot be less than 1")
        s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        s.connect((self.ip_address, self.ip_port))
        s.send(MakePacket(Key_TxGain, power))
        s.close()
        
        self.log.info("USRP power: {}".format(power))
        return {"TX_POWER" : power}
        
    @wishful_module.bind_function(upis.radio.get_parameters)
    def get_parameters(self,params):
        result = {}
        if 'TX_POWER' in params:
            result['TX_POWER'] = self.tx_power
            
        if 'RX_GAIN' in params:
            result['RX_GAIN'] = self.rx_gain
            
        if 'RETUNE_DUPLEXER' in params:
            result['RETUNE_DUPLEXER'] = self.retune_dup
            
        if 'SET_CD' in params:
            result['SET_CD'] = self.set_cd
        
        if 'DEV_ADDRESS' in params:
            result['DEV_ADDRESS'] = self.dev_addr

        if 'DEST_ADDRESS' in params:
            result['DEST_ADDRESS'] = self.dst_addr

        if 'SET_MAC' in params:
            result['SET_MAC'] = self.mac_set

        if 'CD_THRESHOLD' in params:
            result['CD_THRESHOLD'] = self.cd_threshold

        if 'SE_ENABLE' in params:
            result['SE_ENABLE'] = self.si_en_dis
            
        if 'CD_AVG_LEN' in params:
            result['SE_ENABLE'] = self.cd_avg_len
        
        self.log.info("Parameters: {}".format(result))
        return result
        
    @wishful_module.bind_function(upis.radio.set_parameters)
    def set_parameters(self,params):
        print('set parameters')
        result = {}
        if 'TX_POWER' in params:
            self.set_tx_power(params['TX_POWER'])
            self.tx_power = params['TX_POWER']
            result['TX_POWER'] = params['TX_POWER']
            
        if 'RX_GAIN' in params:
            self.set_rx_gain(params['RX_GAIN'])
            self.rx_gain = params['RX_GAIN']
            result['RX_GAIN'] = params['RX_GAIN']
            
            
        if 'RETUNE_DUPLEXER' in params:
            self.retune_duplexer(params['RETUNE_DUPLEXER'])
            self.retune_dup = params['RETUNE_DUPLEXER']
            result['RETUNE_DUPLEXER'] = params['RETUNE_DUPLEXER']
            
        if 'SET_CD' in params:
            self.set_collision_detection(params['SET_CD'])
            self.set_cd = params['SET_CD']
            result['SET_CD'] = params['SET_CD']
            
        if 'DEV_ADDRESS' in params:
            self.device_address(params['DEV_ADDRESS'])
            self.dev_addr = params['DEV_ADDRESS']
            result['DEV_ADDRESS'] = params['DEV_ADDRESS']
            
        if 'DEST_ADDRESS' in params:
            self.dest_address(params['DEST_ADDRESS'])
            self.dst_addr = params['DEST_ADDRESS']
            result['DEST_ADDRESS'] = params['DEST_ADDRESS']
            
        if 'SET_MAC' in params:
            self.set_mac(params['SET_MAC'])
            self.mac_set = params['SET_MAC']
            result['SET_MAC'] = params['SET_MAC']
            
        if 'CD_THRESHOLD' in params:
            self.set_cd_threshold(params['CD_THRESHOLD'])
            self.cd_threshold = params['CD_THRESHOLD']
            result['CD_THRESHOLD'] = params['CD_THRESHOLD']
            
        if 'SE_ENABLE' in params:
            self.si_enable_disable(params['SE_ENABLE'])
            self.si_en_dis = params['SE_ENABLE']
            result['SE_ENABLE'] = params['SE_ENABLE']
        
        if 'CD_AVG_LEN' in params:
            self.set_cd_avg_length = params['CD_AVG_LEN']
            result['CD_AVG_LEN'] = params['CD_AVG_LEN']
            self.cd_avg_len = params['CD_AVG_LEN']
            
        self.log.info("Parameters: {}".format(result))
        return result

    @wishful_module.bind_function(upis.radio.get_measurements)
    def get_measurements(self,params):
        result = {}
        if 'CD_RESULT' in params:
            result['CD_RESULT'] = self.req_cd_result()

        if 'RCV_PCKT' in params:
            result['RCV_PCKT'] = self.req_recv_pkt()

        if 'IQ_DATA' in params:
            result['IQ_DATA'] = self.req_iq_data()

        return result
        
        
    def set_rx_gain(self, gain:int):
        '''
        Sets RX gain
        '''
        if gain > 20:
            gain = 20
        if gain < 0:
            gain = 0

        s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        s.connect((self.ip_address, self.ip_port))
        s.send(MakePacket(Key_RxGain, gain))
        s.close()
        self.log.debug("USRP power: {}".format(gain))
        
       
    def retune_duplexer(self, on:bool):
        s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        s.connect((self.ip_address, self.ip_port))
        
        if on:
            s.send(MakePacket(Key_RetuneDuplexer, 1))
        else:
            s.send(MakePacket(Key_RetuneDuplexer, 0))
               
        s.close()
        
        self.log.debug("Retune duplexer: {}".format(on))
        
        
        
        
    def set_collision_detection(self,value:str):
        
        values = {'reset': 1,
              'ideal': 0,
              'train': 2,
              'fix_alpha': 6,
              'start': 14,
              }
        
        
        if value not in values:
            print('not a valid input')
            
            for k in values:
                print('\t-'+k)
            
            self.log.debug("Not a valid input: {}".format(value))
            
            return
            
        v = values[value]    
        
        s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        
        s.connect((self.ip_address, self.ip_port))
        s.send(MakePacket(Key_CollisionDetector, v))
        s.close()
        
        self.log.debug("Collision detection set to {}".format(value))
        
        
        
    def device_address(self,address:int):
    
        if len(bin(address)) > 18:
            print('You must enter must be a 16 bit number')
            self.log.debug("Not a valid input: {}".format(address))
            return
            
        s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        s.connect((self.ip_address, self.ip_port))
        s.send(MakePacket(Key_DeviceAdd, address))
        s.close()
        
        

    def dest_address(self,address:int):
    
        if len(bin(address)) > 18:
            print('You must enter must be a 16 bit number')
            self.log.debug("Not a valid input: {}".format(address))
            return
            
        s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        s.connect((self.ip_address, self.ip_port))
        s.send(MakePacket(Key_DestinationAdd, address))
        s.close()
        
        
        
    def req_cd_result(self):
        s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        s.connect((self.ip_address, self.ip_port))
        s.send(MakePacket(Key_PacketRec_CD_Test, 1))
        data = s.recv(8)
        s.close()
       
        if (data[0] == 250) and (data[1] == 1) and (data[2] == 250) and (data[5] == Key_PacketRec_CD_Test):
            print("Collision Test %: ", data[6])
            self.log.debug("Collision Test: {}".format(data[6]))

        return data[6]


    def req_recv_pkt(self):
    
        s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        s.connect((self.ip_address, self.ip_port))
        s.send(MakePacket(Key_ReceivedPacketReq, 1))
        
        length = 2 * 1024 + 3 + 2 + 1  # 1024 (16 bit data) + 3 header + 2 length + 1 key 5
        
        data = s.recv(length)
      
        s.close()
        
        
        
        result = {}
        
        if (data[0] == 250) and (data[1] == 1) and (data[2] == 250) and (data[5] == Key_ReceivedPacketReq):
            print("Number of received Bytes: ", data[3] + (data[4] << 8))
            result['NUM_RX'] = data[3] + (data[4] << 8)
            received = []
            for i in range(6,len(data)-1,2):
                received.append(data[i] + (data[i+1] << 8))
            result['RX_DATA'] = received

        return result


    def req_iq_data(self):
        s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        s.connect((self.ip_address, self.ip_port))
        s.send(MakePacket(Key_IQDataReq, 1))
        length = 2 * 1024 + 3 + 2 + 1  # 1024 (16 bit data) + 3 header + 2 length + 1 key 5
        data = s.recv(length)
        s.close()
        
        result = {}
        if (data[0] == 250) and (data[1] == 1) and (data[2] == 250) and (data[5] == Key_IQDataReq):
            print("Number of received Bytes: ", data[3] + (data[4] << 8))
            self.log.debug("Number of received Bytes:  {}".format(data[3] + (data[4] << 8)))
            result['RECEIVED_BYTES'] = data[3] + (data[4] << 8)
            received = []
            result['IQ_COMPLEX'] = []
            flag = True
            for i in range(6,len(data)-1,2):
                if flag:
                    iq = 'I'
                    flag = False
                    result['IQ_COMPLEX'].append(data[i] + (data[i+1] << 8))
                else:
                    iq = 'Q'
                    flag = True
                    result['IQ_COMPLEX'][-1] += (data[i] + (data[i+1] << 8))*1j
                    
                received.append((iq,data[i] + (data[i+1] << 8)))
                #print((iq,data[i] + (data[i+1] << 8)))
                self.log.debug("{} :  {}".format(iq,data[3] + (data[4] << 8)))
            result['IQ_DATA'] = received
            
            

        return result



    def set_mac(self, mac_setting):
        print('b0: payload form host, b1: MAC.CD.Enable')
        print(mac_setting)
        if mac_setting not in range(0,4):
            print('mac_setting must be 0 or 3')
            self.log.debug("Not a valid input: {}".format(mac_setting))
            return 
                
        s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        s.connect((self.ip_address, self.ip_port))
        s.send(MakePacket(Key_MACSetting, mac_setting))
        s.close()
       


    def set_cd_avg_length(self, avg_length: int):
        

        if avg_length not in range(256):
            print('avg length must be between 0 and 255')
            self.log.debug("Not a valid input: {}".format(avg_length))
            return 
        self.cd_avg_len = avg_length
        s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        s.connect((self.ip_address, self.ip_port))
        s.send(MakePacket(Key_CD_Average, avg_length))
        s.close()
        
    
    def set_cd_threshold(self, thr):

        if thr not in range(256):
            print('Threshold must be between 0 and 255')
            self.log.debug("Not a valid input: {}".format(thr))
            return
            
        s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        s.connect((self.ip_address, self.ip_port))
        s.send(MakePacket(Key_CD_Average_Th, thr))
        s.close()
       
        
    def send_payload(self, data):
        '''
        data must be a bytearray
        '''
        if len(data) > N_Payload:
            print('data is too long, it should be maximum %d',N_Payload)
            return
        
        
        s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        s.connect((self.ip_address, self.ip_port))
        s.send(MakePacket(Key_HostPayload, data))
        s.close()
        
        
    def si_enable_disable(self,on_off:bool):
    
        s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        s.connect((self.ip_address, self.ip_port))
        if on_off:
            s.send(MakePacket(Key_EnableDisableSI, 1))
        else:
            s.send(MakePacket(Key_EnableDisableSI, 0))
        s.close()
        
        print('Self Interference enable')

