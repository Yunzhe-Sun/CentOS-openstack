# -*- coding: utf-8 -*-
# 客户端服务处理
import time
import json
def getTimeStamp():
    return int(round(time.time() * 1000))

class User:
    def __init__(self,account:str,pswd:str):
        self.account=account
        self.pswd=pswd
        # 账本
        self.account_books_id=self.account+"_account_books"

# 用户余额
class UserBooksBalance:
    def __init__(self,account:str,balance:int,updateTimestamp:int,createTimestamp:int):
        self.account=account
        self.balance=balance
        self.updateTimestamp=updateTimestamp
        self.createTimestamp=createTimestamp
"""
    收支 item
"""
class UserBooksRecordItem(object):

    def __init__(self, money:int, recordType:int, description:str, dateTime:str, timestamp:int):
        self.money=money
        self.recordType=recordType
        self.description=description
        # 用户
        self.dateTime=dateTime
        self.timestamp=timestamp


    # type:UserBooksRecordItem
    @classmethod
    def json_to_incomde_and_expenses(self,js:dict):
        obj=UserBooksRecordItem(**js)
        return obj
"""
    redis 配置信息
"""
import redis
redis_host='127.0.0.1'
redis_port=6379
redis_pswd=None
# 用户账本
class UserBooksDao(object):

    def __init__(self,rs):
        self.rs=rs# type:redis
    def createUserBooksBalance(self,account):
        timestamp=getTimeStamp()
        userBooksbalance=UserBooksBalance(account=account,balance=0,updateTimestamp=timestamp,createTimestamp=timestamp)
        self.rs.hmset('user_books_balance:'+str(account),userBooksbalance.__dict__)

    # 添加记录
    def addRecord(self, account, record:UserBooksRecordItem):
        userBalance=self.rs.hgetall('user_books_balance:'+str(account))
        print('account',account,'userBalance:',userBalance,'type:',type(userBalance))
        if not userBalance or len(userBalance)==0:
            self.createUserBooksBalance(account=account)
            userBalance = self.rs.hgetall('user_books_balance:' + str(account))
        balance=int(userBalance.get('balance',0))
        balance=balance+int(record.money)
        self.rs.lpush('user_books_record_list:'+str(account),json.dumps(record,default=lambda o:o.__dict__))
        self.rs.hmset('user_books_balance:'+str(account),{'balance':balance,'updateTimestamp':getTimeStamp()})
    # 移除账本记录
    def removeRecord(self,account,timestamp):
        recordlist=self.getAllRecord(account)
        record=None
        for index,rd in enumerate(recordlist):
            # 数据格式错误的原因
            print('rd:',rd)
            rdJson=json.loads(rd)
            if int(rdJson['timestamp']) == int(timestamp):
                record=rd#type:dict
                break
        # 记录存在
        if record:
            self.rs.lrem('user_books_record_list:'+str(account),1,value=record)
            record=json.loads(record)
            money=int(record.get('money',0))
            userBalance = self.rs.hgetall('user_books_balance:' + str(account))
            if not userBalance or len(userBalance)==0:
                self.createUserBooksBalance(account=account)
                userBalance = self.rs.hgetall('user_books_balance:' + str(account))
            balance = int(userBalance.get('balance',0))
            balance = balance -money
            self.rs.hmset('user_books_balance:' + str(account), {'balance': balance, 'updateTimestamp': getTimeStamp()})
            return True
        # 记录不存在
        else:
            return False
        return False
    # 获取记录
    def getAllRecord(self,account):
        records=self.rs.lrange('user_books_record_list:'+str(account),0,-1)
        print('records type:',type(records))
        return records
    # 获取用户总账单
    def getUserBalance(self,account):
        return self.rs.hgetall('user_books_balance:'+str(account))

class Sql(object):
    def __init__(self):
        pool = redis.ConnectionPool(host=redis_host, port=redis_port,
                                    decode_responses=True)  # host是redis主机，需要redis服务端和客户端都起着 redis默认端口是6379
        self.rs = redis.Redis(connection_pool=pool)#type:redis
class  UserDao:
    def __init__(self,rs):
        self.__rs=rs
        pass
    # 登录模块
    def checkUserAccountExists(self,account):
        user = self.__rs.hgetall('user:' + str(account))
        print('test :user:',user)
        if not user or len(user)==0:
            return False
        return True
        pass
    def checkAccountAndPswdMatch(self,account,pswd):
        user=self.__rs.hgetall("user:" + str(account))#type:user
        if not user or len(user)==0:
            return False
        if user.get('pswd',None) == pswd:
            return True
        return False
    # 增加用户
    def addUser(self,user:User):
        if self.checkUserAccountExists(account=user.account):
            return False
        self.__rs.hmset('user:' + str(user.account), user.__dict__)
        return True
    # 删除用户
    def deleteUser(self,account):
        self.__rs.delete('user:' + str(account))
        pass
    # 修改密码
    def updatePswd(self,account,oldPswd,newPswd):
        if self.checkAccountAndPswdMatch(account,oldPswd):
            self.__rs.hmset('user:' + str(account),{'pswd':newPswd})
            return True
        return False

class Session(object):
    def __init__(self,sessionId,account,createTimestamp:int,updateTimestamp:int):
        self.sessionId=sessionId
        self.account=account
        self.createTimestamp=createTimestamp
        self.updateTimestamp=updateTimestamp
class SessionDao:
    def __init__(self,rs:redis):
        self.__rs = rs  # type:redis
        pass
    def addSession(self,session:Session):
        self.__rs.hmset('user_session:' + str(session.sessionId), session.__dict__)
        pass
    def getAccountBySessionId(self,sessionId):
        session=self.__rs.hgetall('user_session:' + str(sessionId))#type:dict
        account=None
        if session:
            account=session.get('account',None)
        return account
import uuid
from result_code import *
#
# ERROR_CODE_NOT_LOGIN = 0x000001
# ERROR_CODE_UNKNOW_MSG=0x000002
# HTTP_SUCCESSED=0x000000
class Service(object):
    def __init__(self):
        pool = redis.ConnectionPool(host=redis_host, port=redis_port,
                                    decode_responses=True)  # host是redis主机，需要redis服务端和客户端都起着 redis默认端口是6379
        rs = redis.Redis(connection_pool=pool)
        self.userDao=UserDao(rs=rs)
        self.userBooksDao=UserBooksDao(rs=rs)
        self.sessionDao=SessionDao(rs=rs)
    def make_session_id(self):
        return str(uuid.uuid1())
    def handleEvent(self,data:dict):
        print('客户端请求数据:',data)
        eventType=data.get('eventType',None)
        if not eventType:
            return {'result': ERROR_CODE_UNKNOW_MSG, 'error': '未知消息类型!'}
        if eventType == 'login':
            return self.login(data)
        elif eventType == 'register':
            return self.register(data)
        elif eventType == 'submitBooksRecord':
            return self.submitBooksRecord(data)
        elif eventType=='getUserBooks':
            return self.getUserBooks(data)
        elif eventType == 'removeReocrd':
            return self.removeReocrd(data)
        return {'result':ERROR_CODE_UNKNOW_MSG,'error':'未知消息类型!'}
    # 注销 清除用户信息
    def clearUser(self,data:dict):
        sessionId = data.get('sessionId',None)
        if not sessionId:
            return {'result': ERROR_CODE_NOT_LOGIN, 'error': '当前账号未登录!'}

        account = self.sessionDao.getAccountBySessionId(sessionId)
        # 客户端收到该消息后 应该退出登录状态
        if not account:
            return {'result': ERROR_CODE_NOT_LOGIN, 'error': '当前账号未登录!'}
        self.userDao.deleteUser(account=account)
        pass
    # 登录模块
    def login(self,data:dict):
        account=data.get("account",None)
        pswd=data.get("pswd",None)
        if not self.userDao.checkUserAccountExists(account):
            return {"result":ERROR_CODE_LOGIN_ACCOUNT_NOT_EXITS,'error':'账户不存在!'}
        if not self.userDao.checkAccountAndPswdMatch(account,pswd):
            return {"result":ERROR_CODE_LOGIN_PSWD_NOT_MATCH_ACCOUNT,'error':'账户或密码错误!'}
        sessionId=self.make_session_id()
        timestamp=getTimeStamp()
        session=Session(sessionId=sessionId, account=account, createTimestamp=timestamp,updateTimestamp=timestamp)
        self.sessionDao.addSession(session=session)
        return {'result':0x0000,'info':'登录成功!','sessionId':sessionId,'account':account}
    def register(self,data:dict):
        account = data.get("account", None)
        pswd = data.get("pswd", None)
        isExists=self.userDao.checkUserAccountExists(account=account)
        if isExists:
            return {'result':ERROR_CODE_REGISTER_ACCOUNT_HAS_EXITS,'error':'账户已存在！'}
        user=User(account=account,pswd=pswd)
        self.userDao.addUser(user)
        self.userBooksDao.createUserBooksBalance(account)
        return {'result':SUCCESSED_CODE, 'info': '账号注册成功！'}
    # 提交账本记录
    def submitBooksRecord(self,data:dict):
        # money: int, type: int, description: str,dateTime:str, timestamp: int):
        sessionId = data.get('sessionId', None)
        if not sessionId:
            return {'result': ERROR_CODE_NOT_LOGIN, 'error': '当前账号未登录!'}
        account=self.sessionDao.getAccountBySessionId(sessionId)
        # 客户端收到该消息后 应该退出登录状态
        if not account:
            return {'result':ERROR_CODE_NOT_LOGIN,'error':'当前账号未登录!'}
        money=data['money']
        recordType=data['recordType']
        description=data['description']
        dateTime=data['dateTime']
        record=UserBooksRecordItem(money=money, recordType=recordType, description=description, dateTime=dateTime, timestamp=getTimeStamp())
        self.userBooksDao.addRecord(account=account,record=record)
        return {'result':SUCCESSED_CODE, 'info': '账本记录提交成功!'}
    # 获取账本记录
    def getUserBooks(self,data:dict):
        sessionId = data.get('sessionId', None)
        if not sessionId:
            return {'result': ERROR_CODE_NOT_LOGIN, 'error': '当前账号未登录!'}
        account = self.sessionDao.getAccountBySessionId(sessionId)
        # 客户端收到该消息后 应该退出登录状态
        if not account:
            return {'result': ERROR_CODE_NOT_LOGIN, 'error': '当前账号未登录!'}
        records=self.userBooksDao.getAllRecord(account=account)
        balance=self.userBooksDao.getUserBalance(account=account)
        return {'result':SUCCESSED_CODE, 'records':records,'balance':balance}
    # 删除账本记录
    def removeReocrd(self,data:dict):
        timestamp=data['timestamp']
        sessionId = data.get('sessionId', None)
        timestamp = data.get('timestamp',None)
        if not sessionId:
            return {'result': ERROR_CODE_NOT_LOGIN, 'error': '当前账号未登录!'}
        account = self.sessionDao.getAccountBySessionId(sessionId)
        # 客户端收到该消息后 应该退出登录状态
        if not account:
            return {'result': ERROR_CODE_NOT_LOGIN, 'error': '当前账号未登录!'}
        hasRemove=self.userBooksDao.removeRecord(account=account,timestamp=timestamp)
        if hasRemove:
            return {'result': SUCCESSED_CODE, 'info': '记录移除成功!'}
        else:
            return {'result':ERROR_CODE_REMOVE_RECORD_NOT_EXITS,'error':'移除失败，该记录不存在！'}



