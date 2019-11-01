# -*- coding: utf-8 -*-

"""
    paxose    learner只负责接受proposer 决议通过得到的值
"""

"""
    在代码中 ，对于方法和类的注释
    若是采用 --------------------------------包围的说明的是当前函数的作用，类的作用说明
    若是采用 ********************************包围 是后器可能的扩展或者的提前说明

"""

"""
    paxos2与 paxos1 区别
    在paoxs2中，proposer 的启动由server决定
    在server中传入proposer 对象
    server 通过调用 start_submission_protocol(serverId) , 通知proposer开始提交协议
    同时 proposer中有一个参数 is_running 判断 当前是否正在处于提交协议中，
    当正在处于提交协议中时 server 无法调用再次调用 __prepare_phase
"""

import inspect
import ctypes
from gevent import monkey
monkey.patch_all()
import simplejson as json
from multiprocessing import Process
import socket
import threading
# 协程
import gevent
import traceback
import time
#qt
from PyQt5.QtCore import QThread, pyqtSignal
from PyQt5 import QtCore, QtGui, QtWidgets
from PyQt5.QtWidgets import QApplication, QListWidget, QMainWindow
import sys
# 自己的库
from result_code import *
from client_service import Service

"""
-----------------------------------------------------------------------------------
                    算法思想
-----------------------------------------------------------------------------------

# Server 中有三个角色:
提议者 Proposer  发送提案 选举leader的提案 
决策者 Acceptor 接受 Proposer 发送过来的 议案(协议)
学习者 Learner  学习提案

# 类信息:
当变成分布式后  信息从 配置文件中加载
## Address:
    通信类 ServerInfo  服务器的信息: 
    字段:
        地址  host
        端口  port
        自身Id  id (可能不需要 暂时保留)
    在一个机器上 的模拟 显然只能是端口的不同
    在分布式上的部署    host不用 其他的信息
## Leader:
    选举出来的 leader信息 server中的 默认为null:
    字段:
        Address 信息       

##    
"""

"""
    常量
"""
SUCCESSED = 0
FAILED = 1

SERVER_NUM = 10  # 服务器个数
ACCEPTOR_SOCKET_SERVER_MAX_CONNECTIONS = SERVER_NUM * 2  # 决策者 的socket最大连接数

SLEEP_TIME = 2  # 休息时间
PROPOSER_START_WAIT_TIME = 5  # type:float proposer启动需要等待时
ACCEPTOR_START_WAIT_TIME = 5  # type:float acceptor启动等待时间
SERVER_START_WAIT_TIME = 5  # type:float server启动等待时间

PROPOSER_PREAPRE_PHASE_GET_RESPONSE_TIMEOUT = 5  # type:float   提议者在准备阶段获取回复 等待的时间 单位(s)
PROPOSER_DECISION_PHASE_GET_RESPONSE_TIMEOUT = 5  # type:float   提议者在决策阶段获取回复 等待的时间 单位(s)

PROPOSER_REENTER_PREPARE_PHASE_WHEN_IN_PREPARE_PHASE = 5  # type:float 提议者在准备阶段被拒绝 重新进入准备阶段提交协议需要等待时间(s)
PROPOSER_REENTER_PREPARE_PHASE_WHEN_IN_DECISION_PHASE = 5  # type:float 提议者在决策阶段被拒绝 重新进入准备阶段提交协议需要等待时间(s)

SOCKET_UDP_OF_SERVER_TIMEOUT = 5  # 设置一个udp通信 server长时间无法接收消息的时间限制 超过时间就会出现时间超时异常
SOCKET_TCP_OF_SERVER_TIMEOUT = 5  # 设置tcp 超时 没有新client连接

REQUEST_TYPE_PROPOSER_PREPARE_PHASE = 0  # Proposer 在准备阶段发送的request请求
REQUEST_TYPE_PROPOSER_DECISION_PHASE = 1  # Proposer 在决策阶段发送的request请求
RESPONSE_TYPE_ACCEPTOR__PREPARE_PHASE = 2  # Accptor 对Proposer 准备阶段请求的回复
RESPONSE_TYPE_ACCEPTOR__DECISION_PHASE = 3  # Accptor 对Proposer 决策阶段请求的回复

REQUEST_TYPE_OF_CLIENT = 4  # 来自客户端的通信
RESPONSE_TYPE_OF_CLIENT = 5  # 发送给客户端的回复
REQUEST_TYPE_HEART_SERVER_TO_LEADER = 6  # server发送给服务端的 心跳包
RESPONSE_TYPE_HEADRT_LEADER_TO_SERVER = 7  # 接受端 对发送端的 心跳包回复

"""
    工具类或方法
"""


# 读取tcp所有数据
def recvall(s: socket):
    buffer = b''
    while True:
        bytes = s.recv(1024)

        if not bytes:
            break
        buffer += bytes
        if len(bytes) < 1024:
            break
        print(bytes)
    return buffer


class MyJsonTranfansUtil:
    def to_json_str(s):
        s = json.dumps(s, default=lambda o: o.__dict__)
        return s
        pass

    def to_json_obj(s):
        if type(s) != str:
            s = json.dumps(s, default=lambda o: o.__dict__)
        s = json.loads(s)
        return s
def to_json_obj(s):
    while type(s) != dict:
        s = json.loads(s)
    return s
def to_json_str(obj):
    if type(obj) == str:
        obj = to_json_obj(obj)
    s = json.dumps(obj, default=lambda o: o.__dict__)
    return s


class ThreadControcol:
    def __init__(self):
        self.thread_flag = threading.Event()  # 用于暂停线程的标识
        self.thread_flag.set()  # 设置为True
        self.thread_running = threading.Event()  # 用于停止线程的标识
        self.thread_running.set()  # 将running设置为True
        pass

    def pause(self):
        self.thread_flag.clear()  # 设置为False, 让线程阻塞

    def resume(self):
        self.thread_flag.set()  # 设置为True, 让线程停止阻塞

    def stop(self):
        self.thread_flag.set()  # 将线程从暂停状态恢复,如果之前暂停了的话
        self.thread_running.clear()  # 设置为False




# 强制结束线程工具
def stop_thread(tid):
    _async_raise(tid, SystemExit)


def _async_raise(tid, exctype):
    """raises the exception, performs cleanup if needed"""
    tid = ctypes.c_long(tid)
    if not inspect.isclass(exctype):
        exctype = type(exctype)
    res = ctypes.pythonapi.PyThreadState_SetAsyncExc(tid, ctypes.py_object(exctype))
    if res == 0:
        print('tid:', tid)
        raise ValueError("invalid thread id")
    elif res != 1:
        # """if it returns a number greater than one, you're in trouble,
        # and you should call it again with exc=NULL to revert the effect"""
        ctypes.pythonapi.PyThreadState_SetAsyncExc(tid, None)
        raise SystemError("PyThreadState_SetAsyncExc failed")

# https 通信工具类
class HttpUtil:
    """
        :type dict
    """

    @classmethod
    def http_request(cls, target_address: tuple, requestData, timeout):
        if type(requestData) != str:
            requestData = MyJsonTranfansUtil.to_json_str(requestData)

        responseData = None
        s = None  # type: socket
        try:
            s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            s.settimeout(timeout)
            s.connect(target_address)
            s.sendall(requestData.encode('utf-8'))
            # data = s.recv(1024)  # type:bytes
            data = recvall(s)
            data = str(data, 'utf-8')
            if data == None or len(data) < 5:
                return None
            responseData = json.loads(data)
        except socket.error as e:
            print('httputil connect失败:', e, ' target address:', target_address)
            traceback.print_exc()

        except socket.timeout as e:
            print("HttpUtil timeout: ", e, ' target address:', target_address)
            responseData = None
            traceback.print_exc()
        except Exception as e:
            print("HttpUtil: ", e, ' target address:', target_address)
            responseData = None
            traceback.print_exc()
        finally:
            try:
                if s != None:
                    s.shutdown(socket.SHUT_RDWR)
                    s.close()
            except Exception as e:
                traceback.print_exc()
                pass
            pass
        print('http util:', 'socket释放')
        # print('responseData:', responseData)
        return responseData


"""
---------------------------------------------------------------------------------
                        Bean类
---------------------------------------------------------------------------------
"""


class Address:
    def __init__(self, host=None, port=None, serverId=None):
        self.host = host
        self.port = int(port)
        self.serverId = int(serverId)

    def equal(self, a):
        if self.host == a.host and self.port == a.port and self.serverId == a.serverId:
            return True
        return False

    @classmethod
    def json_to_address(cls, json):
        address = Address(**json)
        return address


"""
value 应该是Address类的对象
pid  是一个值
该对象包含的是被推举为Leader的服务器节点的信息
"""


class RequestModel:
    def __init__(self, msg_type, from_address, data=None):
        self.msg_type = msg_type
        self.from_address = from_address  # type:Address
        self.data = data
        pass
class ResponseModel:
    def __init__(self, msg_type=-1, from_address=None, data=None):
        self.msg_type = msg_type
        self.from_address = from_address  # msg_type:Address
        self.data = data
class Protocol:
    def __init__(self, value=None, pid=0):
        self.value = value  # type:Address
        self.pid = pid  # type:int

    def equal(self, b):
        if self.value.equal(b.value) and self.pid == b.pid:
            return True
        return False

    @classmethod
    def json_to_protocol(cls, jn: dict):
        value = None
        pid = None
        if jn.get('value'):
            value = Address.json_to_address(jn.get('value'))
        if jn.get('pid'):
            pid = jn.get('pid')
        protocol = Protocol(pid=pid, value=value)
        return protocol
class Leader:
    def __init__(self, address):
        self.address = address  # type:Address

    @classmethod
    def json_to_leader(cls, jn: dict):
        address = None
        if jn.get('address'):
            address = Address.json_to_address(jn.get('address'))
        leader = Leader(address=address)
        return leader


"""
---------------------------------------------------------------------------------
                    Proposer filed说明
---------------------------------------------------------------------------------
acceptor_address_list   | 决策者的Adress 信息
---------------------------------------------------------------------------------
---------------------------------------------------------------------------------
"""
class Proposer(QThread, ThreadControcol, object):
    signal = pyqtSignal()  # 括号里填写信号传递的参数

    def __init__(self, local_address, acceptor_address_list):
        self.local_address = local_address
        self.acceptor_address_list = acceptor_address_list  # type:list[Address]
        self.size_of_accptor = len(self.acceptor_address_list)
        #  当前是否在 提交协议过程中
        self.is_running = False
        # 判断当前是否接收到协议请求
        self.protocol_request_received = False
        self.tid = None  # 线程id
        super(Proposer, self).__init__()
        # ThreadControcol.__init__(self)

    def run(self):
        self.tid = self.currentThreadId()  # 保存线程id
        print("Proposer 启动 proposer_address :%s " % (json.dumps(self.local_address, default=lambda o: o.__dict__))
              + "    :")
        time.sleep(PROPOSER_START_WAIT_TIME)
        while True and self.thread_running.isSet():
            #  当前接收到来自server的协议提交请求
            if self.protocol_request_received:
                print('当前接收到来自server的协议提交请求:')
                self.protocol_request_received = False
                self.__on_start()
                self.__prepare_phase(self.server_address)
                self.__on_finished()
            time.sleep(3)
        pass

    """
    -----------------------------------------------------------------------------------------
                        start_submission_protocol 函数作用
    -----------------------------------------------------------------------------------------
                        server通过调用该函数告知 proposer自己的请求
    -----------------------------------------------------------------------------------------


    *****************************************************************************************
    *后期如果采用 proposer 与 server 隔离,
    *proposer 的个数小于 server的个数，一个proposer负责多个server的协议请求 
    *server 向proposer发送请求采用网络时 
    *在这基础上可以快速更改代码
    *****************************************************************************************
    """

    def start_submission_protocol(self, server_address,server_credit_weight=100):
        self.protocol_request_received = True
        self.server_address = server_address
        self.server_credit_weight=server_credit_weight
        self.__on_start()
        pass

    # 准备阶段
    #  serverId是启动准备阶段的serverId
    def __on_start(self):
        self.is_running = True

    def __on_finished(self):
        self.is_running = False

    def __prepare_phase(self, server_address: Address):
        pid = self.getPid(server_address.serverId)  # 本次阶段的pid值
        protocol = Protocol(value=None, pid=pid)
        data = {
            'protocol': protocol
        }
        request = RequestModel(msg_type=REQUEST_TYPE_PROPOSER_PREPARE_PHASE, from_address=self.local_address, data=data)

        print("Proposer proposer_address:%s " % (json.dumps(self.local_address, default=lambda o: o.__dict__))
              + " 进入准备阶段   Prepare Phase:"
              + "    protocol:%s " % json.dumps(protocol, default=lambda o: o.__dict__))

        responseList = gevent.joinall(
            [gevent.spawn(HttpUtil.http_request, (adress.host, adress.port), request,
                          PROPOSER_PREAPRE_PHASE_GET_RESPONSE_TIMEOUT) for
             adress in self.acceptor_address_list]
            , timeout=PROPOSER_PREAPRE_PHASE_GET_RESPONSE_TIMEOUT

        )  # type: list[ResponseModel]

        count_accept_prepare = 0  # 接受并且回复的Acceptor数量
        protocol_list = []
        for response in responseList:
            # 收到了回复 且 接受了Proposer 的prepare回复
            response = response.value
            if response != None \
                    and response.get('data', None) != None:
                count_accept_prepare += 1
                #  Accpror 返回了一个上次接受的协议
                temp_protocol = response['data'].get('protocol', None)
                if temp_protocol != None:
                    protocol_list.append(Protocol.json_to_protocol(temp_protocol))
        protocol = None
        # 回复人数未超过 一半 重新进入准备阶段
        if count_accept_prepare < self.size_of_accptor / 2:
            # 等待一段时间后重新进入准备阶段
            time.sleep(PROPOSER_REENTER_PREPARE_PHASE_WHEN_IN_PREPARE_PHASE)
            self.__prepare_phase(server_address)
            return

        if len(protocol_list) > 1:
            protocol = max(protocol_list, key=lambda protocol: protocol.pid)
            protocol.pid = pid
        else:
            protocol = Protocol(value=server_address, pid=pid)

        # 进入决策阶段
        self.__decision_phase(protocol, server_address)

    # 决策阶段 提交提议
    def __decision_phase(self, protocol: Protocol, server_address: Address):

        print("Proposer proposer_address:%s " % (json.dumps(self.local_address, default=lambda o: o.__dict__))
              + " 进入提交决策阶段   Decision Phase:"
              + "    protocol:%s " % json.dumps(protocol, default=lambda o: o.__dict__))

        data = {
            'protocol': protocol
        }
        request = RequestModel(msg_type=REQUEST_TYPE_PROPOSER_DECISION_PHASE, from_address=self.local_address,
                               data=data)
        print('preposre prtocol:', MyJsonTranfansUtil.to_json_str(request))
        responseList = gevent.joinall(
            [gevent.spawn(HttpUtil.http_request, (adress.host, adress.port), request,
                          PROPOSER_PREAPRE_PHASE_GET_RESPONSE_TIMEOUT) for
             adress
             in self.acceptor_address_list]
            , timeout=PROPOSER_PREAPRE_PHASE_GET_RESPONSE_TIMEOUT
        )  # type: list[ResponseModel]

        count_accept_decision = 0  # 接受并且回复的Acceptor数量
        for response in responseList:
            # 收到了回复 且 Acceptor 接受了Proposer 决策阶段提交的协议(leader)
            response = response.value
            if response != None and response['data'] != None \
                    and response['data']['result'] == SUCCESSED_CODE:
                count_accept_decision += 1

        # 有过半接受了
        if count_accept_decision > self.size_of_accptor / 2:
            # self.server.change_leader(Leader(protocol.value))
            print("Proposer proposer_address:%s " % (json.dumps(self.local_address, default=lambda o: o.__dict__))
                  + "    Decision Phase:"
                  + "    protocol:%s 已经被大多数决策者接受" % json.dumps(protocol, default=lambda o: o.__dict__))
        else:
            print("Proposer proposer_address:%s " % json.dumps(self.local_address, default=lambda o: o.__dict__)
                  , "    Decision Phase:"
                  , "    protocol:%s 已经被大多数决策者拒绝" % json.dumps(protocol, default=lambda o: o.__dict__)
                  , '接受者数:', count_accept_decision, "重新进入准备阶段")
            # 等待一段时间后重新进入准备阶段
            time.sleep(PROPOSER_REENTER_PREPARE_PHASE_WHEN_IN_DECISION_PHASE)
            self.__prepare_phase(server_address)

    # 可信等级credit weight  1-100
    # 生成pid 暂时使用时间戳+serverId的方式
    #  前13位 是 毫秒级时间  后五位是 serverId序号
    # 可信节点
    def getPid(self, serverId):
        # 根据可信值来保证 不可信的机器的提议被通过的可能性降低
        # 很显然 在同一秒内，可信值相差10的两个server的提交的协议中，低可信值的必定会被否定
        t = str(int(time.time() * 1000) - 100 * (100 - self.server_credit_weight))
        id = "0" * (5 - len(str(serverId))) + str(serverId)
        self.pid = int(t + id)
        return self.pid

    # 中断执行
    def do_alert(self):
        self.pause()
        pass

    def do_resume(self):
        self.resume()

    # 结束应用
    def do_stop(self):
        self.stop()
        del self


"""
    Acceptor 与Server 之前没有必要的联系


    Acceptor filed 说明
---------------------------------------------------------------------------------------
    成员变量    |       作用
---------------------------------------------------------------------------------------
    local_address | Acceptor的本地配置信息 Address的对象
---------------------------------------------------------------------------------------
    accept  |      接受的协议 Protocol 的对象
---------------------------------------------------------------------------------------
    promisePid  |  承诺的Pid值
---------------------------------------------------------------------------------------
    chosen      |   选择的协议(leader)  该参数可能无效
---------------------------------------------------------------------------------------

---------------------------------------------------------------------------------------



"""


class Acceptor(QThread, ThreadControcol):
    signal = pyqtSignal()  # 括号里填写信号传递的参数

    def __init__(self, local_address, distinguishe_learner_address_list):
        self.local_address = local_address  # type: Address
        # 接受的协议
        self.accept_protocol = None
        self.promisePid = 0
        self.distinguishe_learner_address_list = distinguishe_learner_address_list

        self.tid = None
        super(Acceptor, self).__init__()

    def run(self):
        self.tid = self.currentThreadId()  # 保存线程id
        print("Acceptor 启动 address:%s " % (json.dumps(self.local_address, default=lambda o: o.__dict__))
              + "    :")
        gevent.joinall([
            gevent.spawn(self.server_socket)
        ])
        # socket默认是 tcp通信

    def server_socket(self):
        socketserver = socket.socket()
        socketserver.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        socketserver.bind((self.local_address.host, self.local_address.port))
        # 最大连接数
        socketserver.listen(ACCEPTOR_SOCKET_SERVER_MAX_CONNECTIONS)
        socketserver.settimeout(5)
        while True and self.thread_running.isSet():
            try:
                conn, addr = socketserver.accept()
                print('acceptor :', to_json_str(self.local_address), '接收到了新链接')
                # gevent.spawn(self.handle_request, conn)
                # 改成单线程处理
                self.handle_request(conn)
            except socket.timeout as e:
                pass
            except Exception as e:
                print("Acceptor address:%s " % (json.dumps(self.local_address, default=lambda o: o.__dict__))
                      , e)
                traceback.print_exc()

        try:
            if not socketserver:
                socketserver.shutdown(socket.SHUT_RDWR)
                socketserver.close()
        except Exception as e:
            traceback.print_exc()
            pass
        print('acceptor', 'socket释放')

    def handle_request(self, conn):
        request_model = None
        try:
            data = recvall(conn)
            # data=conn.recv(1024)
            if not data:
                conn.close()
            else:
                data = str(data, 'utf-8')
                request_model = json.loads(data)  # type:json
                # print('request_model:','type:',type(request_model),request_model)
                msg_type = int(request_model.get('msg_type', -1))
                print('acceptor msg_type:', msg_type)
                if msg_type == REQUEST_TYPE_PROPOSER_PREPARE_PHASE:
                    response_model = self.handle_prepare(request_model)
                    # print('prepare response_model:',response_model)
                elif msg_type == REQUEST_TYPE_PROPOSER_DECISION_PHASE:
                    response_model = self.handle_decision(request_model)
                else:
                    response_model = {'error': '未知的消息'}
                # print('response_model:',response_model)
                response_model = json.dumps(response_model, default=lambda o: o.__dict__)
                responseByte = str(response_model).encode('utf-8')
                print('acceptor response:', str(response_model))
                conn.sendall(responseByte)
        except OSError as e:
            print("client has been closed")
            traceback.print_exc()
            # sys.exit(-1)
        except Exception as ex:
            print(ex)
            traceback.print_exc()

            # sys.exit(-1)
        finally:
            conn.close()
        pass

    def handle_prepare(self, request_model):

        response_model = ResponseModel(msg_type=RESPONSE_TYPE_ACCEPTOR__PREPARE_PHASE,
                                       from_address=self.local_address)  # msg_type: ResponseModel
        response_model.data = None
        try:
            data = request_model.get('data', None)
            if data == None:
                return response_model
            protocol = data.get('protocol', None)
            if protocol == None:
                return response_model
            #  Proposer 在准备阶段提交的值大于 Acceptor的承诺值
            if int(self.promisePid) < int(protocol['pid']):
                response_data = {
                    'protocol': self.accept_protocol,
                    'result': FAILED
                }
                response_model.data = response_data
                self.promisePid = int(protocol['pid'])
            else:
                response_model.data = None
        except Exception as e:
            print("Acceptor address:%s " % (json.dumps(self.local_address, default=lambda o: o.__dict__))
                  , "    Exception:", e)
            traceback.print_exc()
        return response_model

    def handle_decision(self, request_model):
        response_model = ResponseModel(msg_type=RESPONSE_TYPE_ACCEPTOR__DECISION_PHASE, from_address=self.local_address)
        response_model.data = None
        try:
            data = request_model.get('data', None)
            if not data:
                return response_model
            protocol = data.get('protocol', None)
            if not protocol:
                return response_model
            #  pid
            pid = int(protocol.get('pid', -1))
            new_accept_protocol = None
            """
                       if int(self.promisePid) < int(pid):
                           new_accept_protocol = Protocol(protocol_json=protocol)
                           self.promisePid=pid
                           data = {'result': HTTP_SUCCESSED}
                           response_model.data = data
                       elif int(self.promisePid) == int(pid):
                           if self.accept_protocol == None or to_json_str(self.accept_protocol.value) == str(protocol['value']):
                               new_accept_protocol = Protocol(protocol_json=protocol)
                               data = {
                                   'result': HTTP_SUCCESSED
                               }
                               response_model.data = data
                           else:
                               data = {'result': HTTP_FAILED}
                               response_model.data = data
                       else:
                           data = {'result': HTTP_FAILED}
                           response_model.data = data
                       """
            if int(self.promisePid) <= int(pid):
                new_accept_protocol = Protocol.json_to_protocol(protocol)
                self.promisePid = pid
                data = {'result': SUCCESSED_CODE}
                response_model.data = data
            else:
                if self.accept_protocol != None and MyJsonTranfansUtil.to_json_str(self.accept_protocol.value) == str(
                        protocol['value']):
                    new_accept_protocol = Protocol.json_to_protocol(protocol)
                    data = {
                        'result': SUCCESSED_CODE
                    }
                    response_model.data = data
                else:
                    data = {'result': FAILED}
                    response_model.data = data

            #  协议被更新
            if new_accept_protocol:
                print('协议被更新:', MyJsonTranfansUtil.to_json_str(new_accept_protocol))
                self.accept_protocol = new_accept_protocol
                self.send_accept_protocol_to_distinguished_learner(new_accept_protocol)

        except Exception as e:
            response_model.data = None
            print(e)
            traceback.print_exc()
        return response_model

    def send_accept_protocol_to_distinguished_learner(self, accept_protocol: Protocol):
        """
            发送的数据格式
             {
                'from_address': local_address,
                'accept_protocol':Protocol
            }
        :param accept_protocol:
        :return:
        """
        print('acceptor address:', MyJsonTranfansUtil.to_json_str(self.local_address),
              '接收了propose提交的新的协议，向distinguished_learner 发送新的协议')
        s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        try:
            for i in self.distinguishe_learner_address_list:
                address = (i.host, i.port)
                data = {
                    'from_address': self.local_address,
                    'accept_protocol': accept_protocol,
                }
                msg = json.dumps(data, default=lambda o: o.__dict__)
                msg = str(msg).encode('utf-8')
                s.sendto(msg, address)
        except Exception as e:
            print(e)
            traceback.print_exc()
        finally:
            try:
                if s:
                    s.close()
                    s = None
            except Exception as e:
                traceback.print_exc()
                print(e)
        print('')

    # 中断执行
    def do_alert(self):
        self.pause()
        pass

    def do_resume(self):
        self.resume()

    # 结束应用
    def do_stop(self):
        self.stop()
        del self


SERVER_MAX_CLIENT_NUM = 100  # 设置最大连接server的client 数目(client 指的是客户端 非其他server数目)



class Server(QThread, ThreadControcol):
    signal = pyqtSignal()  # 括号里填写信号传递的参数

    # 每个服务器类 都有一个决策者和提议者 并且 决策者和提议者并不会相互影响
    def __init__(self, local_address: Address, proposer: Proposer, acceptor: Acceptor):
        self.local_address = local_address  # type: Address
        self.__leader = None  # type: Leader
        self.__isLeader = False  # 当前是否是leader
        self.__proposer = proposer
        self.__acceptor = acceptor  # acceptor
        self.__tid = None
        # 客户端请求处理类
        self.client_service = Service()  # type:Service
        super(Server, self).__init__()

    def run(self):
        print('server 启动 address:', MyJsonTranfansUtil.to_json_str(self.local_address), ' ')
        self.__tid = self.currentThreadId()  # 保存线程id
        #  启动的时候判断是否有 leader,没有就提交协议
        if not self.__leader:
            self.start_proposer()
        # 将两项加入协程
        gevent.joinall(
            [
                gevent.spawn(self.server_handle_message),
                gevent.spawn(self.heart_socket_to_leader),
            ]
        )
        return

    #  作为一个server 接收消息
    def server_handle_message(self):
        socketserver = socket.socket()
        socketserver.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        socketserver.bind((self.local_address.host, self.local_address.port))
        # 最大连接数
        # ACCEPTOR_SOCKET_SERVER_MAX_CONNECTIONS 指代其他server数量
        # SERVER_MAX_CLIENT_NUM 客户端数量
        socketserver.listen(ACCEPTOR_SOCKET_SERVER_MAX_CONNECTIONS + SERVER_MAX_CLIENT_NUM)
        # 超时
        socketserver.settimeout(SOCKET_TCP_OF_SERVER_TIMEOUT)
        print('server socketserver 启动:')
        while True and self.thread_running.isSet():
            try:
                conn, addr = socketserver.accept()
                # print('server:',MyJsonTranfansUtil.to_json_str(self.local_address),'收到客户端的链接')
                gevent.spawn(self.handle_request, conn)
            except socket.timeout as e:
                # traceback.print_exc()
                pass
            except Exception as e:
                print("Server address:%s " % (json.dumps(self.local_address, default=lambda o: o.__dict__))
                      , e)
                traceback.print_exc()
        try:
            if not socketserver:
                socketserver.shutdown(socket.SHUT_RDWR)
                socketserver.close()
        except Exception as e:
            traceback.print_exc()
            pass
        print('server socketserver释放:')

    #   处理通信请求
    def handle_request(self, conn: socket):
        print('server:', MyJsonTranfansUtil.to_json_str(self.local_address), '处理请求')
        response = None
        try:
            data = recvall(conn)
            # data = conn.recv(1024)
            if not data:
                conn.close()
            else:
                data = str(data, 'utf-8')
                data = to_json_obj(data)  # type:json
                msg_type = int(data.get('msg_type', -1))
                if msg_type == REQUEST_TYPE_HEART_SERVER_TO_LEADER:
                    response = self.handle_heart_beat(data=data)
                    conn.send(MyJsonTranfansUtil.to_json_str(response).encode('utf-8'))
                    pass
                # 来自客户端的消息
                elif msg_type == REQUEST_TYPE_OF_CLIENT:
                    response = self.handle_client_request(data=data)
                    conn.send(MyJsonTranfansUtil.to_json_str(response).encode('utf-8'))

                else:
                    conn.send("{'error':'未知的消息'}".encode('utf-8'))
                    pass
        except OSError as e:
            print("client has been closed")
            traceback.print_exc()
            # sys.exit(-1)
        except Exception as ex:
            print(ex)
            traceback.print_exc()
        finally:
            conn.close()

    # 处理来自其他server的心跳包
    def handle_heart_beat(self, data):
        data = {
            'info': '心跳包',
        }
        response = ResponseModel(msg_type=RESPONSE_TYPE_HEADRT_LEADER_TO_SERVER, from_address=self.local_address,
                                 data=data)
        return response

    # 处理client的请求
    def handle_client_request(self, data: dict):
        print('来自客户端的操作请求:', data)
        # 没有leader
        if not self.__leader:
            return {'result': ERROR_CODE_NOT_LEADER, 'error': '没有leader'}
        # server结点是leader
        if self.__isLeader:
            data = data.get('data', None)
            return self.client_service.handleEvent(data)
        # server结点不是leader 转发请求给leader
        else:
            result = HttpUtil.http_request(target_address=(self.__leader.address.host, self.__leader.address.port),
                                           requestData=data, timeout=5)
            return result

    # 作为一个 节点 保持与leader的通信

    # 发送到 leader的心跳包机制
    def heart_socket_to_leader(self):
        SERVER_LEADER_HEART_TIME = 10  # server和leader之间的心跳时间
        SERVER_LEADER_LOST_CONNCET_MAX_TIME = 30  # server 和leader失联时间
        data = {
            'info': '心跳包',
        }
        request = ResponseModel(msg_type=REQUEST_TYPE_HEART_SERVER_TO_LEADER, from_address=self.local_address,
                                data=data)
        # 统计失去联系时间
        lost_connect_time = 0
        while True and self.thread_running.isSet():
            # leader未选举出来 或者leader是自身
            if not self.__leader or self.__isLeader:
                lost_connect_time = 0
            else:
                print('server 发送心跳消息:', MyJsonTranfansUtil.to_json_str(self.local_address))
                response = HttpUtil.http_request(
                    target_address=(self.__leader.address.host, self.__leader.address.port), requestData=request,
                    timeout=5)
                # 没有接收到回复
                if not response:
                    print('server:', MyJsonTranfansUtil.to_json_str(self.local_address), ' 没有收到leader的回复')
                    lost_connect_time += SERVER_LEADER_HEART_TIME
                else:
                    print('server:', MyJsonTranfansUtil.to_json_str(self.local_address),
                          ' 收到了leader的回复 leader:', MyJsonTranfansUtil.to_json_str(self.__leader))
                    lost_connect_time = 0

                if lost_connect_time >= SERVER_LEADER_LOST_CONNCET_MAX_TIME:
                    self.handle_event_of_cannot_conncet_leader()
            gevent.sleep(SERVER_LEADER_HEART_TIME)

    # 处理leader失联时间  默认是leader 宕机
    def handle_event_of_cannot_conncet_leader(self):
        # server与leader失去联系 重新发起选举之前的等待时间
        LOST_LEADER_SERVER_FRESH_VOTE_WAIT_TIME = 10
        # 将acceptor协议清空
        self.__leader = None
        self.__isLeader = False
        self.__acceptor.accept_protocol = None
        # 等待其他server发现leader宕机
        print('等待', LOST_LEADER_SERVER_FRESH_VOTE_WAIT_TIME, '秒 重新发起选举')
        gevent.sleep(LOST_LEADER_SERVER_FRESH_VOTE_WAIT_TIME)
        # 重新发起选举
        self.start_proposer()

    def wait_message(self):

        pass

    def start_proposer(self):
        if self.__proposer.is_running:
            return False
        # 通过proposer 提交协议
        print('server addres:', MyJsonTranfansUtil.to_json_str(self.local_address),
              '提交了协议')
        self.__proposer.start_submission_protocol(self.local_address)
        return True

    def isLeader(self):
        return self.__isLeader

    """
    -------------------------------------------------------------------------
    在Learner 中调用   当learner 检测到leader出现 就会调用server.change_leader

    -------------------------------------------------------------------------
    """

    def change_leader(self, leader):
        # leader无
        if not leader:
            self.__leader = leader
            self.__isLeader = False
        # leader是本身        elif MyJsonTranfansUtil.to_json_str(self.local_address)==MyJsonTranfansUtil.to_json_str(leader.address):
        elif self.local_address.equal(leader.address):
            print('我被选择为leader', self.local_address)
            self.__isLeader = True
            self.__leader = leader  # type:Leader
        else:
            self.__leader = leader
            self.__isLeader = False
            pass
        print("Server Address = ", json.dumps(self.local_address, default=lambda o: o.__dict__),
              'leader change newLeader:', json.dumps(leader, default=lambda o: o.__dict__)
              )

    # 中断执行
    def do_alert(self):
        self.pause()
        pass

    def do_resume(self):
        self.resume()

    # 结束应用
    def do_stop(self):
        self.stop()
        del self


# Learner 是和Server绑定的 Learner将学习到的协议(Leader)通知给Server
class Learner(QThread, ThreadControcol):
    signal = pyqtSignal()  # 括号里填写信号传递的参数

    def __init__(self, local_address, server):
        self.local_address = local_address  # type:Address
        self.server = server  # type:Server

        super(Learner, self).__init__()

        self.tid = None  # 线程id

    def run(self):
        self.tid = self.currentThreadId()
        pass
        # 接收处理消息
        gevent.joinall(
            [gevent.spawn(self.__socket_server)]
        )

    def __socket_server(self):
        """
                   接收到的数据格式如下
                   {
                       'from_address':self.local_address,
                       'choosen_protocol':choosen_protocol,
                   }
               :return:
               """
        print('learner socket server 启动:', MyJsonTranfansUtil.to_json_str(self.local_address))
        s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        s.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        s.bind((self.local_address.host, self.local_address.port))
        # 设置超时时间 超过时间就会提示异常
        s.settimeout(SOCKET_UDP_OF_SERVER_TIMEOUT)
        while True and self.thread_running.isSet():
            try:
                bytes, addr = s.recvfrom(1024)  # type:bytes
                if not bytes:
                    break
                else:
                    data = str(bytes.decode('utf-8'))
                    data = to_json_obj(data)
                    print('learner address:', MyJsonTranfansUtil.to_json_str(self.local_address),
                          'choosen protococl:', data)
                    # json.loads(json.dumps(data,default=lambda o:o.__dict__) ) # type:dict
                    choosen_protocol_json_obj = data.get('choosen_protocol', None)  # type:dict
                    if not choosen_protocol_json_obj:
                        continue
                    else:
                        choosen_protocol = Protocol.json_to_protocol(choosen_protocol_json_obj)
                        leader = Leader(choosen_protocol.value)
                        self.change_leader(leader)
            except socket.timeout as e:
                # 对于超时错误不进行提示和处理
                pass
            except Exception as e:
                traceback.print_exc()
                pass
        try:
            if s != None:
                s.shutdown(2)
                s.close()
        except Exception as e:
            traceback.print_exc()

        print('learner', 'socket释放')

    def change_leader(self, leader: Leader):
        self.server.change_leader(leader)

    # 停止
    def do_stop(self):
        self.stop()
        del self

    # 中断执行
    def do_alert(self):
        self.pause()
        pass

    def do_resume(self):
        self.resume()


# Learner 的负责人  负责接收Acceptro的消息 再发送给其他Learner
class DistinguishedLearner(Learner):
    def __init__(self, local_address: Address, server: Server, learner_address_list: list, acceptor_num: int) -> object:
        Learner.__init__(self, local_address=local_address, server=server)
        self.choosen = None  # type:Address
        self.learner_address_list = learner_address_list  # type:learner_address_list:list[Address]
        self.acceptor_num = acceptor_num
        # acceptor_accept_protocol_map 是acceptor发送给learner 的在 决策阶段 接受的协议
        self.acceptor_accept_protocol_map = {}  # 使用Acceptor地址中的serverId作为键值

    """
        接收来自Acceptor的消息 
        消息内容:Acceptor 接收了某个协议 就将该协议发送给 负责接收的 DistinguishedLearner
        DistinguishedLearner 接收协议之后 判断该协议是否被大多数 Acceptor 接受 ,如果被大多数接受 再将协议通知给普通的 learner
         接收到的Acceptor 的json数据格式
            {
                'from_address': local_address,
                'accept_protocol':Protocol
            }

         发送给Learner 的json数据格式
            {
                'from_address':self.local_address,
                'choosen_protocol':choosen_protocol,
            }
    """

    def run(self):
        self.tid = self.currentThreadId()  # 保存线程id
        gevent.joinall(
            [gevent.spawn(self.__socket_server)]
        )

    def __socket_server(self):
        print('DistinguishedLearner socket server 启动:', MyJsonTranfansUtil.to_json_str(self.local_address))

        s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        s.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        s.bind((self.local_address.host, self.local_address.port))
        s.settimeout(SOCKET_UDP_OF_SERVER_TIMEOUT)
        while True and self.thread_running.isSet():
            try:
                bytes, addr = s.recvfrom(1024)  # type:bytes
                if not bytes:
                    break
                else:
                    data = str(bytes.decode('utf-8'))
                    data = json.loads(data)
                    # json.loads(json.dumps(data, default=lambda o: o.__dict__))  # type:dict
                    print('DistinguishedLearner address:', MyJsonTranfansUtil.to_json_str(self.local_address),
                          'acceptor address:', data['from_address'],
                          'accept protocol:', data['accept_protocol'])
                    if not data:
                        continue
                    print('json data:')
                    accept_protocol = data.get('accept_protocol', None)
                    from_address_json_obj = data.get('from_address', None)
                    if not accept_protocol or not from_address_json_obj:
                        print('DistinguishedLearner address:', MyJsonTranfansUtil.to_json_str(self.local_address),
                              '来自Acceptor的信息格式不对')
                        continue
                    else:
                        accept_protocol = Protocol.json_to_protocol(accept_protocol)
                        from_address = Address.json_to_address(from_address_json_obj)
                        self.handle_accept_protocol(from_address=from_address, accept_protocol=accept_protocol)
            except socket.timeout as e:
                pass
            except Exception as e:
                print('DistinguishedLearner 接收消息异常')
                traceback.print_exc()
        try:
            if s != None:
                s.shutdown(2)
                s.close()
        except Exception as e:
            traceback.print_exc()
        print('DistinguishedLearner', 'socket释放')

    def handle_accept_protocol(self, from_address: Address, accept_protocol: Protocol):
        print('DistinguishedLearner address:', MyJsonTranfansUtil.to_json_str(self.local_address),
              'handle accept protocol:', json)
        from_address_str = json.dumps(from_address, default=lambda o: o.__dict__)
        self.acceptor_accept_protocol_map[str(from_address.serverId)] = accept_protocol
        count_the_sample_protocol = 0
        for i in self.acceptor_accept_protocol_map.values():  # type:Protocol
            if i.equal(accept_protocol):
                count_the_sample_protocol += 1

        #  大多数 Acceptor 都接受了 该协议 ,该协议(leader)被确定
        if count_the_sample_protocol > self.acceptor_num / 2:
            """
                一开始的判断:
                  如果两次choosen的协议值相同 就不通知其他学习者
                  否则通知其他学习者新的choosen协议(即leader改变)
                   if self.choosen != None and to_json_str(self.choosen.value) == to_json_str(accept_protocol.value):
                
                存在的问题:当 某个非leader的server掉线后，他重新发起申请 得到的协议任然是旧的协议
                当choosen协议选择不更改，该server 将不能获得新协议
                暂时通过直接False 
                 一般协议在10秒内左右完成  通过判断时间
            """
            print('生成协议:protocol:', MyJsonTranfansUtil.to_json_str(accept_protocol))
            # pid[0:13] 是毫秒时间
            if self.choosen != None \
                    and self.choosen.value.equal(accept_protocol.value) \
                    and int(str(accept_protocol.pid)[0:13]) - int(str(self.choosen.pid)[0:13]) < 10 * 1000:
                print('协议相同:', '\n'
                      , 'self.choosen.value:', MyJsonTranfansUtil.to_json_str(self.choosen.value), '\n'
                      , 'accept_protocol.value:', MyJsonTranfansUtil.to_json_str(accept_protocol.value), '\n'
                      , 'str(accept_protocol.pid)[0:13]:', str(accept_protocol.pid)[0:13], '\n'
                      , 'str(self.choosen.pid)[0:13]:', str(self.choosen.pid)[0:13])
                self.choosen = accept_protocol
                pass
            else:
                self.choosen = accept_protocol
                leader = Leader(self.choosen.value)
                print('DistinguishedLearner address:', MyJsonTranfansUtil.to_json_str(self.local_address),
                      'leader change:', leader)
                # 通知server leader值的改变
                self.change_leader(leader)
                # 通知其他普通的leader 最新确定的协议(leader)
                self.send_choosen_protocol_to_other_leader(choosen_protocol=self.choosen)

    def send_choosen_protocol_to_other_leader(self, choosen_protocol: Protocol):
        s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        for i in self.learner_address_list:
            address = (i.host, i.port)
            data = {
                'from_address': self.local_address,
                'choosen_protocol': choosen_protocol,
            }
            msg = json.dumps(data, default=lambda o: o.__dict__)
            msg = str(msg).encode('utf-8')
            s.sendto(msg, address)





class ServerWindow(QMainWindow):

    def __init__(self, ):
        super().__init__()
        self.is_running = False
        self.setupUi()
        self.show()

    # 加载服务器结点信息
    def load_server_data(self, server_address: Address, proposer_address: Address, acceptor_address: Address,
                         learner_address: Address, acceptor_address_list, distinguishe_learner_address_list,
                         learner_address_list, is_distinguishe_learner=False):
        self.server_address = server_address
        self.proposer_address = proposer_address
        self.acceptor_address = acceptor_address
        self.learner_address = learner_address
        self.acceptor_address_list = acceptor_address_list
        self.distinguishe_learner_address_list = distinguishe_learner_address_list
        self.learner_address_list = learner_address_list
        self.is_distinguishe_learner = is_distinguishe_learner
        self.set_info(serverid=self.server_address.serverId,
                      address=MyJsonTranfansUtil.to_json_str(self.server_address), status='stop')
        self.setWindowTitle('服务器:%d号' % self.server_address.serverId)
        pass

    def __ini_ui(self):
        self.setupUi()
        pass

    def setupUi(self):
        self.setObjectName("self")
        self.resize(709, 569)
        self.centralwidget = QtWidgets.QWidget(self)
        self.centralwidget.setObjectName("centralwidget")
        self.label = QtWidgets.QLabel(self.centralwidget)
        self.label.setGeometry(QtCore.QRect(10, 20, 72, 15))
        self.label.setObjectName("label")
        self.show_serverid = QtWidgets.QLineEdit(self.centralwidget)
        self.show_serverid.setGeometry(QtCore.QRect(90, 10, 251, 31))
        self.show_serverid.setReadOnly(True)
        self.show_serverid.setObjectName("show_serverid")
        self.label_2 = QtWidgets.QLabel(self.centralwidget)
        self.label_2.setGeometry(QtCore.QRect(10, 60, 72, 15))
        self.label_2.setObjectName("label_2")
        self.show_address = QtWidgets.QLineEdit(self.centralwidget)
        self.show_address.setGeometry(QtCore.QRect(90, 50, 251, 31))
        self.show_address.setDragEnabled(True)
        self.show_address.setReadOnly(True)
        self.show_address.setObjectName("show_address")
        self.label_3 = QtWidgets.QLabel(self.centralwidget)
        self.label_3.setGeometry(QtCore.QRect(10, 100, 72, 15))
        self.label_3.setObjectName("label_3")
        self.show_status = QtWidgets.QLineEdit(self.centralwidget)
        self.show_status.setGeometry(QtCore.QRect(90, 90, 251, 31))
        self.show_status.setDragEnabled(False)
        self.show_status.setReadOnly(True)
        self.show_status.setObjectName("show_status")
        self.bt_start = QtWidgets.QPushButton(self.centralwidget)
        self.bt_start.setGeometry(QtCore.QRect(100, 320, 121, 51))
        self.bt_start.setObjectName("bt_start")
        self.bt_start.clicked.connect(self.handle_btn_start)
        self.bt_stop = QtWidgets.QPushButton(self.centralwidget)
        self.bt_stop.setGeometry(QtCore.QRect(290, 320, 121, 51))
        self.bt_stop.setObjectName("bt_stop")
        self.bt_stop.clicked.connect(self.handle_btn_stop)

        self.bt_start.raise_()
        self.label.raise_()
        self.show_serverid.raise_()
        self.label_2.raise_()
        self.show_address.raise_()
        self.label_3.raise_()
        self.show_status.raise_()
        self.bt_stop.raise_()
        self.setCentralWidget(self.centralwidget)
        self.menubar = QtWidgets.QMenuBar(self)
        self.menubar.setGeometry(QtCore.QRect(0, 0, 709, 26))
        self.menubar.setObjectName("menubar")
        self.menu = QtWidgets.QMenu(self.menubar)
        self.menu.setObjectName("menu")
        self.setMenuBar(self.menubar)
        self.statusbar = QtWidgets.QStatusBar(self)
        self.statusbar.setObjectName("statusbar")
        self.setStatusBar(self.statusbar)
        self.menubar.addAction(self.menu.menuAction())

        self.retranslateUi()
        QtCore.QMetaObject.connectSlotsByName(self)
        self.setTabOrder(self.bt_start, self.show_address)
        self.setTabOrder(self.show_address, self.show_status)
        self.setTabOrder(self.show_status, self.show_serverid)

    def retranslateUi(self):
        _translate = QtCore.QCoreApplication.translate
        self.setWindowTitle(_translate("MainWindow", "MainWindow"))
        self.label.setText(_translate("MainWindow", "serverid:"))
        self.label_2.setText(_translate("MainWindow", "address:"))
        self.label_3.setText(_translate("MainWindow", "status:"))
        self.bt_start.setText(_translate("MainWindow", "start"))
        self.bt_stop.setText(_translate("MainWindow", "stop"))
        self.menu.setTitle(_translate("MainWindow", "菜单 "))

    def set_info(self, serverid, address, status):
        self.show_serverid.setText(str(serverid))
        self.show_address.setText(str(address))
        self.show_status.setText(str(status))

    def set_status(self, status):
        self.show_status.setText(status)

    #  启动
    def handle_btn_start(self, event):
        self.start_server()

    def handle_btn_stop(self, event):
        self.stop_server()
        pass

    def start_server(self):
        if self.is_running:
            return
        self.proposer = Proposer(local_address=self.proposer_address, acceptor_address_list=self.acceptor_address_list)
        self.acceptor = Acceptor(local_address=self.acceptor_address,
                                 distinguishe_learner_address_list=self.distinguishe_learner_address_list)
        self.server = Server(local_address=self.server_address, proposer=self.proposer, acceptor=self.acceptor)
        self.learner = None
        if self.is_distinguishe_learner:
            self.learner = DistinguishedLearner(local_address=self.learner_address, server=self.server,
                                                learner_address_list=self.learner_address_list,
                                                acceptor_num=len(self.acceptor_address_list))
        else:
            self.learner = Learner(local_address=self.learner_address, server=self.server)

        try:
            self.server.signal.connect(self.call_back)
            self.learner.signal.connect(self.call_back)
            self.proposer.signal.connect(self.call_back)
            self.acceptor.signal.connect(self.call_back)

            self.acceptor.start()
            self.learner.start()
            self.proposer.start()
            self.server.start()
        except Exception as e:
            traceback.print_exc()
        print('protocol_request_received:', self.proposer.protocol_request_received)
        self.is_running = True
        self.set_info(serverid=self.server_address.serverId,
                      address=MyJsonTranfansUtil.to_json_str(self.server_address),
                      status='running')

    def stop_server(self):
        if not self.is_running:
            return
        self.learner.do_stop()
        self.server.do_stop()
        self.acceptor.do_stop()
        self.proposer.do_stop()
        self.is_running = False
        self.set_server_status("stop")
        pass

    def call_back(self):
        pass

    def set_server_status(self, s):
        self.show_status.setText(s)

def loadConfiguration(configuration:dict):
    # 声明全局变量
    global SERVER_NUM
    global ACCEPTOR_SOCKET_SERVER_MAX_CONNECTIONS

    SERVER_NUM=configuration.get('SERVER_NUM',None)
    ACCEPTOR_SOCKET_SERVER_MAX_CONNECTIONS=configuration.get('ACCEPTOR_SOCKET_SERVER_MAX_CONNECTIONS',None)
    if not SERVER_NUM or not ACCEPTOR_SOCKET_SERVER_MAX_CONNECTIONS:
        print('加载配置信息失败!')
        sys.exit(0)
    pass
def startOne(configuration:dict,server_address: Address, proposer_address: Address, acceptor_address: Address, learner_address: Address,
             acceptor_address_list, distinguishe_learner_address_list, learner_address_list,
             is_distinguishe_learner=False, ):
    loadConfiguration(configuration)
    print('configuraatin:',SERVER_NUM)
    print('configuraatin:',ACCEPTOR_SOCKET_SERVER_MAX_CONNECTIONS)

    print('进程启动:serverId:%d' % server_address.serverId)
    app = QApplication(sys.argv)
    servre_window = ServerWindow()
    try:
        servre_window.load_server_data(server_address, proposer_address, acceptor_address, learner_address,
                                       acceptor_address_list, distinguishe_learner_address_list,
                                       learner_address_list, is_distinguishe_learner)
    except Exception as e:
        traceback.print_exc()
        sys.exit(0)
    servre_window.start_server()
    sys.exit(app.exec_())

    # proposer = Proposer(local_address=proposer_address, acceptor_address_list=acceptor_address_list)
    # server = Server(local_address=server_address,proposer=proposer)
    #
    # acceptor = Acceptor(local_address=acceptor_address,
    #                     distinguishe_learner_address_list=distinguishe_learner_address_list)
    # learner = None
    # if is_distinguishe_learner:
    #     learner = DistinguishedLearner(local_address=learner_address, server=server,
    #                                    learner_address_list=learner_address_list,
    #                                    acceptor_num=len(acceptor_address_list))
    # else:
    #     learner = Learner(local_address=learner_address, server=server)
    # server.start()
    # learner.start()
    # acceptor.start()
    # proposer.start()


pass
'''
if __name__ == '__main__':
    HOST = '127.0.0.1'
    PORT_BASE = 10000
    acceptor_address_list = []
    distinguishe_learner_address_list = []
    learner_address_list = []
    for i in range(int(SERVER_NUM)):
        # 选择 1/4 的机器作为  distinguishe_learner 用于接受 Acceptor的消息
        if i < max(int(SERVER_NUM / 4), 1):
            distinguishe_learner_address_list.append(
                Address(host=HOST, port=PORT_BASE + i * 10 + 3, serverId=i))
            pass
        else:
            learner_address_list.append(Address(host=HOST, port=PORT_BASE + i * 10 + 3, serverId=i))
            pass
        acceptor_address_list.append(Address(host=HOST, port=PORT_BASE + i * 10 + 2, serverId=i))

    for i in range(int(SERVER_NUM)):
        is_distinguishe_learner = False
        if i < max(int(SERVER_NUM / 4), 1):
            is_distinguishe_learner = True

        p = Process(target=startOne,
                    args=(Address(host=HOST, port=PORT_BASE + i * 10, serverId=i),  # server
                          Address(host=HOST, port=PORT_BASE + i * 10 + 1, serverId=i),  # proposer
                          Address(host=HOST, port=PORT_BASE + i * 10 + 2, serverId=i),  # acceptor
                          Address(host=HOST, port=PORT_BASE + i * 10 + 3, serverId=i),  # learner
                          acceptor_address_list,  # acceptor_address_list
                          distinguishe_learner_address_list,  # distinguishe_learner_address_list
                          learner_address_list,  # learner_address_list
                          is_distinguishe_learner
                          )
                    )
        p.start()
'''