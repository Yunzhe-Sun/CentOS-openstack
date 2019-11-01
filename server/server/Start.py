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
from paxose import startOne
from paxose import SERVER_NUM, ACCEPTOR_SOCKET_SERVER_MAX_CONNECTIONS
from paxose import Address

# 配置信息
SERVER_NUM = 10  # 服务器个数
ACCEPTOR_SOCKET_SERVER_MAX_CONNECTIONS = SERVER_NUM * 2  # 决策者 的socket最大连接数
HOST = '127.0.0.1'
PORT_BASE = 10000
configuration = {
    'SERVER_NUM': SERVER_NUM,
    'ACCEPTOR_SOCKET_SERVER_MAX_CONNECTIONS': ACCEPTOR_SOCKET_SERVER_MAX_CONNECTIONS,

    # 该部分由代码生成
    'server_configuration_map': {
    }
}


# 用于快速创建地址的配置
def createAddressConfiguration(SERVER_NUM):
    acceptor_configuration_list = []
    learner_configuration_list = []
    proposer_configuration_list = []
    server_configuration_list = []
    for i in range(int(SERVER_NUM)):
        # 选择 1/4 的机器作为  distinguishe_learner 用于接受 Acceptor的消息
        if i < max(int(SERVER_NUM / 4), 1):
            learner_configuration_list.append(
                {'address': Address(host=HOST, port=PORT_BASE + i * 10 + 3, serverId=i),
                 'isDistinguisheLearner': True
                 }
            )
        else:
            learner_configuration_list.append(
                {'address': Address(host=HOST, port=PORT_BASE + i * 10 + 3, serverId=i),
                 'isDistinguisheLearner': False
                 }

            )

        server_configuration_list.append({'address': Address(host=HOST, port=PORT_BASE + i * 10 + 0, serverId=i)})
        proposer_configuration_list.append({'address': Address(host=HOST, port=PORT_BASE + i * 10 + 1, serverId=i)})
        acceptor_configuration_list.append({'address': Address(host=HOST, port=PORT_BASE + i * 10 + 2, serverId=i)})

    acceptor_configuration_list_json = json.dumps(acceptor_configuration_list, default=lambda o: o.__dict__)
    learner_configuration_list_json = json.dumps(learner_configuration_list, default=lambda o: o.__dict__)
    server_configuration_list_json = json.dumps(server_configuration_list, default=lambda o: o.__dict__)
    proposer_configuration_list_json = json.dumps(proposer_configuration_list, default=lambda o: o.__dict__)

    acceptor_configuration_list = json.loads(acceptor_configuration_list_json)
    learner_configuration_list = json.loads(learner_configuration_list_json)
    server_configuration_list = json.loads(server_configuration_list_json)
    proposer_configuration_list = json.loads(proposer_configuration_list_json)
    return {'acceptor_configuration_list': acceptor_configuration_list,
            'learner_configuration_list': learner_configuration_list,
            'server_configuration_list': server_configuration_list,
            'proposer_configuration_list': proposer_configuration_list,
            }


"""
def startAllServer():
    acceptor_address_list = []
    distinguishe_learner_address_list = []
    learner_address_list = []
    proposer_address_list = []
    server_address_list = []
    for i in range(int(SERVER_NUM)):
        # 选择 1/4 的机器作为  distinguishe_learner 用于接受 Acceptor的消息
        if i < max(int(SERVER_NUM / 4), 1):
            distinguishe_learner_address_list.append(
                Address(host=HOST, port=PORT_BASE + i * 10 + 3, serverId=i))
            pass
        else:
            learner_address_list.append(Address(host=HOST, port=PORT_BASE + i * 10 + 3, serverId=i))
            pass
        server_address_list.append(Address(host=HOST, port=PORT_BASE + i * 10 + 0, serverId=i))
        proposer_address_list.append(Address(host=HOST, port=PORT_BASE + i * 10 + 1, serverId=i))
        acceptor_address_list.append(Address(host=HOST, port=PORT_BASE + i * 10 + 2, serverId=i))
    for i in range(int(SERVER_NUM)):
        is_distinguishe_learner = False
        if i < max(int(SERVER_NUM / 4), 1):
            is_distinguishe_learner = True

        p = Process(target=startOne,
                    args=(
                        configuration,  # 配置信息
                        Address(host=HOST, port=PORT_BASE + i * 10, serverId=i),  # server
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
"""


def startAllServer():
    server_configuration_map = configuration['server_configuration_map']

    acceptor_configuration_list = server_configuration_map['acceptor_configuration_list']
    learner_configuration_list = server_configuration_map['learner_configuration_list']
    proposer_configuration_list = server_configuration_map['proposer_configuration_list']
    server_configuration_list = server_configuration_map['server_configuration_list']

    acceptor_address_list = [Address.json_to_address(item['address']) for item in acceptor_configuration_list]
    proposer_address_list = [Address.json_to_address(item['address']) for item in proposer_configuration_list]
    server_address_list = [Address.json_to_address(item['address']) for item in server_configuration_list]

    # not_distinguishe_learner_address_list+distinguishe_learner 是所有的learner
    not_distinguishe_learner_address_list = [Address.json_to_address(item['address']) for item in
                                             learner_configuration_list if not item['isDistinguisheLearner']]
    distinguishe_learner_address_list = [Address.json_to_address(item['address']) for item in learner_configuration_list
                                         if item['isDistinguisheLearner']]

    all_learner_address_list = [Address.json_to_address(item['address']) for item in learner_configuration_list]

    for i in range(int(SERVER_NUM)):
        is_distinguishe_learner = learner_configuration_list[i].get('isDistinguisheLearner', True)
        server_address = server_address_list[i]
        prposer_address = proposer_address_list[i]
        acceptor_address = acceptor_address_list[i]
        learner_address = all_learner_address_list[i]
        p = Process(target=startOne,
                    args=(
                        configuration,  # 配置信息
                        server_address,
                        prposer_address,
                        acceptor_address,
                        learner_address,
                        acceptor_address_list,  # acceptor_address_list
                        distinguishe_learner_address_list,  # distinguishe_learner_address_list
                        not_distinguishe_learner_address_list,  # not_distinguishe_learner_address_list
                        is_distinguishe_learner
                    )
                    )
        p.start()


import sys
import os


def loadConfiguration(path='configuration.json'):
    try:
        jsonstr = open(path).read()
        configuration = json.loads(jsonstr)
    except Exception as e:
        print('error:加载配置文件失败!')
        sys.exit()
    return configuration


# 更新client配置文件信息
def updateClientConfiguration(configuration,path='client_configuration.json',):
    server_configuration_map = configuration['server_configuration_map']
    server_configuration_list = server_configuration_map['server_configuration_list']
    server_address_list = [Address.json_to_address(item['address']) for item in server_configuration_list]
    client_configuration={
        'server_address_list':server_address_list,
        'SERVER_NUM':configuration['SERVER_NUM']
    }
    s=json.dumps(client_configuration, default=lambda o: o.__dict__)
    with open(path,'w+') as f:
        f.write(s)

    pass

'''
将启动生成的configuration.json 文件放置到 client 文件夹中
'''
if __name__ == '__main__':
    configuration['server_configuration_map'] = createAddressConfiguration(int(configuration['SERVER_NUM']))
    updateClientConfiguration(configuration,path='client_configuration.json')
    startAllServer()
