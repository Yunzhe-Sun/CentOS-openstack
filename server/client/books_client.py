# -*- coding: utf-8 -*-

from result_code import *
import re

HTTP_SUCCESSED = 0
HTTP_FAILED = 1
# Form implementation generated from reading ui file 'clientRegister.ui'
#
# Created by: PyQt5 UI code generator 5.11.3
#
# WARNING! All changes made in this file will be lost!
from gevent import monkey

monkey.patch_all()
import json
from multiprocessing import Process
import socket
import threading
from PyQt5 import QtCore, QtGui, QtWidgets
from PyQt5.QtCore import QThread, QThreadPool, pyqtSignal
from PyQt5.QtWidgets import QApplication, QMainWindow, QMessageBox
import traceback

# 读取tcp所有数据
def recvall(s:socket):
    buffer=b''
    while True:
        bytes=s.recv(1024)
        if not bytes:
            break
        buffer+=bytes
        if len(bytes)<1024:
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
            data=recvall(s)
            # data = s.recv(1024)  # type:bytes
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


class Ui_Register(object):
    def setupUi(self, MainWindow):
        MainWindow.setObjectName("RegisterWindow")
        MainWindow.resize(586, 474)
        self.centralwidget = QtWidgets.QWidget(MainWindow)
        self.centralwidget.setObjectName("centralwidget")
        self.btnRegister = QtWidgets.QPushButton(self.centralwidget)
        self.btnRegister.setGeometry(QtCore.QRect(250, 300, 111, 41))
        self.btnRegister.setObjectName("btnRegister_2")
        self.btnRegister.clicked.connect(handleRegister)
        self.inputAccount = QtWidgets.QLineEdit(self.centralwidget)
        self.inputAccount.setGeometry(QtCore.QRect(230, 60, 201, 41))
        self.inputAccount.setText("")
        self.inputAccount.setObjectName("inputAccount")
        self.label = QtWidgets.QLabel(self.centralwidget)
        self.label.setGeometry(QtCore.QRect(160, 60, 41, 31))
        font = QtGui.QFont()
        font.setFamily("宋体")
        font.setPointSize(12)
        self.label.setFont(font)
        self.label.setObjectName("label")
        self.label_2 = QtWidgets.QLabel(self.centralwidget)
        self.label_2.setGeometry(QtCore.QRect(160, 130, 51, 31))
        font = QtGui.QFont()
        font.setFamily("宋体")
        font.setPointSize(12)
        self.label_2.setFont(font)
        self.label_2.setObjectName("label_2")
        self.inputPswd = QtWidgets.QLineEdit(self.centralwidget)
        self.inputPswd.setGeometry(QtCore.QRect(230, 130, 201, 41))
        self.inputPswd.setText("")
        self.inputPswd.setObjectName("inputPswd")
        self.inputPswd.setEchoMode(QtWidgets.QLineEdit.Password)
        self.btnLogin = QtWidgets.QPushButton(self.centralwidget)
        self.btnLogin.setGeometry(QtCore.QRect(390, 300, 111, 41))
        self.btnLogin.setObjectName("btnLogin")
        self.btnLogin.clicked.connect(slot_to_login_page)
        self.confirmPswd = QtWidgets.QLineEdit(self.centralwidget)
        self.confirmPswd.setGeometry(QtCore.QRect(230, 190, 201, 41))
        self.confirmPswd.setText("")
        self.confirmPswd.setObjectName("confirmPswd")
        self.confirmPswd.setEchoMode(QtWidgets.QLineEdit.Password)

        self.label_3 = QtWidgets.QLabel(self.centralwidget)
        self.label_3.setGeometry(QtCore.QRect(130, 190, 91, 31))
        font = QtGui.QFont()
        font.setFamily("宋体")
        font.setPointSize(12)
        self.label_3.setFont(font)
        self.label_3.setObjectName("label_3")
        MainWindow.setCentralWidget(self.centralwidget)
        self.menubar = QtWidgets.QMenuBar(MainWindow)
        self.menubar.setGeometry(QtCore.QRect(0, 0, 586, 26))
        self.menubar.setObjectName("menubar")
        self.menu = QtWidgets.QMenu(self.menubar)
        self.menu.setObjectName("menu")
        MainWindow.setMenuBar(self.menubar)
        self.statusbar = QtWidgets.QStatusBar(MainWindow)
        self.statusbar.setObjectName("statusbar")
        MainWindow.setStatusBar(self.statusbar)
        self.actiontuic = QtWidgets.QAction(MainWindow)
        self.actiontuic.setObjectName("actiontuic")
        self.menu.addSeparator()
        self.menubar.addAction(self.menu.menuAction())

        self.retranslateUi(MainWindow)
        QtCore.QMetaObject.connectSlotsByName(MainWindow)

    def retranslateUi(self, MainWindow):
        _translate = QtCore.QCoreApplication.translate
        MainWindow.setWindowTitle(_translate("RegisterWindow", "注册"))
        self.btnRegister.setText(_translate("RegisterWindow", "注册"))
        self.label.setText(_translate("RegisterWindow", "账号"))
        self.label_2.setText(_translate("RegisterWindow", "密码"))
        self.btnLogin.setText(_translate("RegisterWindow", "登录"))
        self.label_3.setText(_translate("RegisterWindow", "验证密码"))
        self.menu.setTitle(_translate("RegisterWindow", "菜单"))
        self.actiontuic.setText(_translate("RegisterWindow", "tuic"))


class Ui_Login(object):
    def setupUi(self, MainWindow):
        MainWindow.setObjectName("LoginWindow")
        MainWindow.resize(586, 474)
        self.centralwidget = QtWidgets.QWidget(MainWindow)
        self.centralwidget.setObjectName("centralwidget")
        self.btnLogin = QtWidgets.QPushButton(self.centralwidget)
        self.btnLogin.setGeometry(QtCore.QRect(220, 297, 111, 41))
        self.btnLogin.setObjectName("btnLogin")
        self.btnLogin.clicked.connect(handleLogin)
        self.inputAccount = QtWidgets.QLineEdit(self.centralwidget)
        self.inputAccount.setGeometry(QtCore.QRect(220, 90, 201, 41))
        self.inputAccount.setText("")
        self.inputAccount.setObjectName("inputAccount")
        self.label = QtWidgets.QLabel(self.centralwidget)
        self.label.setGeometry(QtCore.QRect(140, 90, 72, 31))
        font = QtGui.QFont()
        font.setFamily("宋体")
        font.setPointSize(16)
        self.label.setFont(font)
        self.label.setObjectName("label")
        self.label_2 = QtWidgets.QLabel(self.centralwidget)
        self.label_2.setGeometry(QtCore.QRect(140, 180, 72, 31))
        font = QtGui.QFont()
        font.setFamily("宋体")
        font.setPointSize(16)
        self.label_2.setFont(font)
        self.label_2.setObjectName("label_2")
        self.inputPswd = QtWidgets.QLineEdit(self.centralwidget)
        self.inputPswd.setGeometry(QtCore.QRect(220, 180, 201, 41))
        self.inputPswd.setText("")
        self.inputPswd.setObjectName("inputPswd")
        self.inputPswd.setEchoMode(QtWidgets.QLineEdit.Password)

        self.btnRegister = QtWidgets.QPushButton(self.centralwidget)
        self.btnRegister.setGeometry(QtCore.QRect(370, 300, 111, 41))
        self.btnRegister.setObjectName("btnRegister")
        self.btnRegister.clicked.connect(slot_to_register_page)

        MainWindow.setCentralWidget(self.centralwidget)
        self.menubar = QtWidgets.QMenuBar(MainWindow)
        self.menubar.setGeometry(QtCore.QRect(0, 0, 586, 26))
        self.menubar.setObjectName("menubar")
        self.menu = QtWidgets.QMenu(self.menubar)
        self.menu.setObjectName("menu")
        MainWindow.setMenuBar(self.menubar)
        self.statusbar = QtWidgets.QStatusBar(MainWindow)
        self.statusbar.setObjectName("statusbar")
        MainWindow.setStatusBar(self.statusbar)
        self.actiontuic = QtWidgets.QAction(MainWindow)
        self.actiontuic.setObjectName("actiontuic")
        self.menu.addSeparator()
        self.menubar.addAction(self.menu.menuAction())

        self.retranslateUi(MainWindow)
        QtCore.QMetaObject.connectSlotsByName(MainWindow)

    def retranslateUi(self, MainWindow):
        _translate = QtCore.QCoreApplication.translate
        MainWindow.setWindowTitle(_translate("LoginWindow", "登录"))
        self.btnLogin.setText(_translate("LoginWindow", "登录"))
        self.label.setText(_translate("LoginWindow", "账号"))
        self.label_2.setText(_translate("LoginWindow", "密码"))
        self.btnRegister.setText(_translate("LoginWindow", "注册"))
        self.menu.setTitle(_translate("LoginWindow", "菜单"))
        self.actiontuic.setText(_translate("LoginWindow", "tuic"))


class Ui_MainWindow(object):
    def setupUi(self, MainWindow):
        MainWindow.setObjectName("MainWindow")
        MainWindow.resize(1143, 679)
        self.centralwidget = QtWidgets.QWidget(MainWindow)
        self.centralwidget.setObjectName("centralwidget")
        self.frame = QtWidgets.QFrame(self.centralwidget)
        self.frame.setGeometry(QtCore.QRect(50, 370, 1021, 251))
        self.frame.setFrameShape(QtWidgets.QFrame.StyledPanel)
        self.frame.setFrameShadow(QtWidgets.QFrame.Raised)
        self.frame.setObjectName("frame")
        self.label_2 = QtWidgets.QLabel(self.frame)
        self.label_2.setGeometry(QtCore.QRect(30, 100, 41, 16))
        self.label_2.setObjectName("label_2")
        self.inputDescription = QtWidgets.QTextEdit(self.frame)
        self.inputDescription.setGeometry(QtCore.QRect(80, 90, 311, 111))
        self.inputDescription.setObjectName("inputDescription")
        self.label_3 = QtWidgets.QLabel(self.frame)
        self.label_3.setGeometry(QtCore.QRect(260, 60, 41, 16))
        self.label_3.setObjectName("label_3")
        self.inputMoney = QtWidgets.QLineEdit(self.frame)
        self.inputMoney.setGeometry(QtCore.QRect(310, 50, 113, 31))
        self.inputMoney.setObjectName("inputMoney")
        self.submitNewReord = QtWidgets.QPushButton(self.frame)
        self.submitNewReord.setGeometry(QtCore.QRect(160, 210, 93, 28))
        self.submitNewReord.setObjectName("submitNewReord")
        self.inputDate = QtWidgets.QDateTimeEdit(self.frame)
        self.inputDate.setGeometry(QtCore.QRect(530, 50, 194, 31))
        self.inputDate.setObjectName("inputDate")
        self.label_5 = QtWidgets.QLabel(self.frame)
        self.label_5.setGeometry(QtCore.QRect(470, 60, 41, 16))
        self.label_5.setObjectName("label_5")
        self.btnJumpToSystemTime = QtWidgets.QPushButton(self.frame)
        self.btnJumpToSystemTime.setGeometry(QtCore.QRect(740, 50, 141, 28))
        self.btnJumpToSystemTime.setObjectName("btnJumpToSystemTime")
        self.rabUseSystemTime = QtWidgets.QRadioButton(self.frame)
        self.rabUseSystemTime.setGeometry(QtCore.QRect(470, 110, 181, 19))
        self.rabUseSystemTime.setObjectName("rabUseSystemTime")
        self.widget = QtWidgets.QWidget(self.frame)
        self.widget.setGeometry(QtCore.QRect(590, 110, 120, 80))
        self.widget.setObjectName("widget")
        self.frame_3 = QtWidgets.QFrame(self.frame)
        self.frame_3.setGeometry(QtCore.QRect(80, 50, 171, 41))
        self.frame_3.setFrameShape(QtWidgets.QFrame.StyledPanel)
        self.frame_3.setFrameShadow(QtWidgets.QFrame.Raised)
        self.frame_3.setObjectName("frame_3")
        self.radChoseIncome = QtWidgets.QRadioButton(self.frame_3)
        self.radChoseIncome.setGeometry(QtCore.QRect(20, 10, 115, 19))
        self.radChoseIncome.setObjectName("radChoseIncome")
        self.radChoseExpenditure = QtWidgets.QRadioButton(self.frame_3)
        self.radChoseExpenditure.setGeometry(QtCore.QRect(90, 10, 115, 19))
        self.radChoseExpenditure.setObjectName("radChoseExpenditure")
        self.label_6 = QtWidgets.QLabel(self.frame)
        self.label_6.setGeometry(QtCore.QRect(0, 60, 72, 15))
        self.label_6.setObjectName("label_6")
        self.frame_2 = QtWidgets.QFrame(self.centralwidget)
        self.frame_2.setEnabled(True)
        self.frame_2.setGeometry(QtCore.QRect(0, 0, 1111, 361))
        self.frame_2.setFrameShape(QtWidgets.QFrame.StyledPanel)
        self.frame_2.setFrameShadow(QtWidgets.QFrame.Raised)
        self.frame_2.setObjectName("frame_2")
        self.btnRefreshData = QtWidgets.QPushButton(self.frame_2)
        self.btnRefreshData.setGeometry(QtCore.QRect(130, 30, 93, 28))
        self.btnRefreshData.setObjectName("btnRefreshData")
        self.label_4 = QtWidgets.QLabel(self.frame_2)
        self.label_4.setGeometry(QtCore.QRect(30, 40, 72, 15))
        self.label_4.setObjectName("label_4")
        self.showRecordsTable = QtWidgets.QTableView(self.frame_2)
        self.showRecordsTable.setGeometry(QtCore.QRect(20, 70, 1091, 271))
        self.showRecordsTable.setObjectName("showRecordsTable")
        self.label = QtWidgets.QLabel(self.frame_2)
        self.label.setGeometry(QtCore.QRect(910, 40, 41, 16))
        self.label.setObjectName("label")
        self.showBalance = QtWidgets.QLineEdit(self.frame_2)
        self.showBalance.setEnabled(False)
        self.showBalance.setGeometry(QtCore.QRect(950, 40, 121, 21))
        self.showBalance.setObjectName("showBalance")
        MainWindow.setCentralWidget(self.centralwidget)
        self.menubar = QtWidgets.QMenuBar(MainWindow)
        self.menubar.setGeometry(QtCore.QRect(0, 0, 1143, 26))
        self.menubar.setObjectName("menubar")
        MainWindow.setMenuBar(self.menubar)
        self.statusbar = QtWidgets.QStatusBar(MainWindow)
        self.statusbar.setObjectName("statusbar")
        MainWindow.setStatusBar(self.statusbar)
        self.retranslateUi(MainWindow)
        QtCore.QMetaObject.connectSlotsByName(MainWindow)

    def retranslateUi(self, MainWindow):
        _translate = QtCore.QCoreApplication.translate
        MainWindow.setWindowTitle(_translate("MainWindow", "MainWindow"))
        self.label_2.setText(_translate("MainWindow", "备注:"))
        self.inputDescription.setHtml(_translate("MainWindow",
                                                 "<!DOCTYPE HTML PUBLIC \"-//W3C//DTD HTML 4.0//EN\" \"http://www.w3.org/TR/REC-html40/strict.dtd\">\n"
                                                 "<html><head><meta name=\"qrichtext\" content=\"1\" /><style type=\"text/css\">\n"
                                                 "p, li { white-space: pre-wrap; }\n"
                                                 "</style></head><body style=\" font-family:\'SimSun\'; font-size:9pt; font-weight:400; font-style:normal;\">\n"
                                                 "<p style=\"-qt-paragraph-type:empty; margin-top:0px; margin-bottom:0px; margin-left:0px; margin-right:0px; -qt-block-indent:0; text-indent:0px;\"><br /></p></body></html>"))
        self.label_3.setText(_translate("MainWindow", "金额："))
        self.submitNewReord.setText(_translate("MainWindow", "点击添加"))
        self.label_5.setText(_translate("MainWindow", "时间:"))
        self.btnJumpToSystemTime.setText(_translate("MainWindow", "跳到当前系统时间"))
        self.rabUseSystemTime.setText(_translate("MainWindow", "始终选则当前系统日期"))
        self.radChoseIncome.setText(_translate("MainWindow", "收入"))
        self.radChoseExpenditure.setText(_translate("MainWindow", "支出"))
        self.label_6.setText(_translate("MainWindow", "记账类型:"))
        self.btnRefreshData.setText(_translate("MainWindow", "刷新数据"))
        self.label_4.setText(_translate("MainWindow", "账单详情"))
        self.label.setText(_translate("MainWindow", "余额:"))
        self.__my_set(MainWindow)
    def __my_set(self,MainWindow):
        MainWindow.setWindowTitle(cookie.account)
        self.inputDate.setCalendarPopup(True)
        self.inputDate.setDateTime(QtCore.QDateTime().currentDateTime())
        self.btnJumpToSystemTime.clicked.connect(self.handleJumpToSystemTime)
        self.submitNewReord.clicked.connect(handleSubmitRecord)
        self.btnRefreshData.clicked.connect(handleGetUserBooks)
        self.radChoseIncome.setChecked(True)

    def handleJumpToSystemTime(self):
        self.inputDate.setDateTime(QtCore.QDateTime().currentDateTime())
        pass

    # def handleDeleteRecord(self, button: QtWidgets.QPushButton):
    #     print('handleRemoveRecord:', button.property('row'))
    #     print('handleRemoveRecord:', button.property('itemdata').get('money', 0))
    #     pass
    def setRecordsData(self,data):
        self.model = QtGui.QStandardItemModel()
        self.model.setColumnCount(5)
        self.model.setRowCount(len(data))
        self.model.setHeaderData(0,QtCore.Qt.Horizontal,u"类型")
        self.model.setHeaderData(1,QtCore.Qt.Horizontal,u"金额")
        self.model.setHeaderData(2,QtCore.Qt.Horizontal,u"提交日期")
        self.model.setHeaderData(3,QtCore.Qt.Horizontal,u"备注")
        self.model.setHeaderData(4,QtCore.Qt.Horizontal,u'操作')
        self.showRecordsTable.setModel(self.model)
        self.showRecordsTable.setColumnWidth(0, 80)
        self.showRecordsTable.setColumnWidth(1, 80)
        self.showRecordsTable.setColumnWidth(2, 180)
        self.showRecordsTable.setColumnWidth(3, 620)
        self.showRecordsTable.setColumnWidth(4, 80)
        # 表头信息显示居中
        self.showRecordsTable.horizontalHeader().setDefaultAlignment(QtCore.Qt.AlignCenter)
        for row,itemdata in enumerate(data):
            try:
                item = QtGui.QStandardItem('%s'%itemdata['recordType'])
                self.model.setItem(row, 0, item)
                item = QtGui.QStandardItem('%s' % itemdata['money'])
                self.model.setItem(row, 1, item)
                item = QtGui.QStandardItem('%s' % itemdata['dateTime'])
                self.model.setItem(row, 2, item)
                item = QtGui.QStandardItem('%s' % itemdata['description'])
                self.model.setItem(row, 3, item)
                button=QtWidgets.QPushButton('删除')
                button.clicked.connect(lambda: handleRemoveRecord(button))
                button.setProperty("row", row)
                button.setProperty('itemdata',itemdata)
                self.showRecordsTable.setIndexWidget(self.model.index(row,4),button)
            except Exception as e:
                traceback.print_exc()
                print('itemdata:',itemdata)
                print('itemdata type:',type(itemdata))
                print(e)
    def setBalance(self,balance):
        self.showBalance.setText(balance)
class Cookie(object):
    def __init__(self):
        self.sessionId = None
        self.account=None
        self.records={}
        self.balance=0


qWindow = None
cookie = Cookie()
loginPage = Ui_Login()
registerPage = Ui_Register()
mainPage=Ui_MainWindow()

def slot_to_login_page():
    qWindow.close()
    loginPage.setupUi(qWindow)
    qWindow.show()
def slot_to_register_page():
    qWindow.close()
    registerPage.setupUi(qWindow)
    qWindow.show()
def slot_to_main_view():
    qWindow.close()
    mainPage.setupUi(qWindow)
    qWindow.show()


REQUEST_TYPE_OF_CLIENT = 4  # 来自客户端的通信
"""
发送的数据类型如下:
data中必须要 eventType 指明请求类型
{
    'msg_type':REQUEST_TYPE_OF_CLIENT,
    'data':{
        'eventType':'register',
        'account':account,
        'pswd':pswd
    }
}
"""

def handleLogin():
    def callback(m: dict):
        if m.get('http_result', HTTP_FAILED) == HTTP_FAILED:
            QMessageBox.warning(qWindow, "提示框", '获取请求失败，请检查当前网络状况! 若网络状态良好，请联系后台工作人员！', QMessageBox.Ok)
            return
        data = m.get('data', None)  # type:dict
        result = int(data.get('result', ERROR_CODE))
        if result == SUCCESSED_CODE:
            info = data.get('info', '')
            cookie.sessionId = data.get('sessionId', 0)
            cookie.account=data.get("account",0)
            QMessageBox.information(qWindow, '通知', info, QMessageBox.Ok)
            slot_to_main_view()
            handleGetUserBooks()
            pass
        else:
            error = data.get('error', '')
            QMessageBox.warning(qWindow, "错误", error, QMessageBox.Ok)
    account = loginPage.inputAccount.text()
    pswd = loginPage.inputPswd.text().strip(' ')
    if not re.match('[0-9a-zA-Z]+$', account):
        QtWidgets.QMessageBox.warning(qWindow, '提示框', '账号只能由数字和字母组成!', QMessageBox.Ok)
        return
    if not re.match('[0-9a-zA-Z]+$', pswd):
        QtWidgets.QMessageBox.warning(qWindow, '提示框', '密码只能由数字和字母组成!', QMessageBox.Ok)
        return
    requetData = {
        'msg_type': REQUEST_TYPE_OF_CLIENT,
        'data': {
            'eventType': 'login',
            'account': account,
            'pswd': pswd
        }
    }
    CorrespondenceServer.postRequestToServer(callback=callback,requestData=requetData)

def handleRegister():
    def callback(m: dict):
        if m.get('http_result', HTTP_FAILED) == HTTP_FAILED:
            QMessageBox.warning(qWindow, "提示框", '获取请求失败，请检查当前网络状况! 若网络状态良好，请联系后台工作人员！', QMessageBox.Ok)
            return
        data = m.get('data', None)  # type:dict

        result = int(data.get('result', ERROR_CODE))
        if result == SUCCESSED_CODE:
            info = data.get('info', '')
            QMessageBox.information(qWindow, '通知', info, QMessageBox.Ok)
            pass
        else:
            error = data.get('error', '')
            QMessageBox.warning(qWindow, "错误", error, QMessageBox.Ok)

    account = registerPage.inputAccount.text()
    pswd = registerPage.inputPswd.text().strip(' ')
    confirmPswd = registerPage.confirmPswd.text().strip(' ')
    if confirmPswd != pswd:
        QtWidgets.QMessageBox.warning(qWindow, '提示框', "两次输入密码不一致!", QMessageBox.Ok)
        return
    if not re.match('[0-9a-zA-Z]+$', account):
        QtWidgets.QMessageBox.warning(qWindow, '提示框', '账号只能由数字和字母组成!', QMessageBox.Ok)
        return
    if not re.match('[0-9a-zA-Z]+$', pswd):
        QtWidgets.QMessageBox.warning(qWindow, '提示框', '密码只能由数字和字母组成!', QMessageBox.Ok)
        return
    data = {
        'msg_type': REQUEST_TYPE_OF_CLIENT,
        'data': {
            'eventType': 'register',
            'account': account,
            'pswd': pswd
        }
    }
    CorrespondenceServer.postRequestToServer(callback=callback,requestData=data)

def handleRemoveRecord(button):
    def callback(m: dict):
        if m.get('http_result', HTTP_FAILED) == HTTP_FAILED:
            QMessageBox.warning(qWindow, "提示框", '获取请求失败，请检查当前网络状况! 若网络状态良好，请联系后台工作人员！', QMessageBox.Ok)
            return
        data = m.get('data', None)  # type:dict
        result = int(data.get('result', ERROR_CODE))
        if result == SUCCESSED_CODE:
            info = data.get('info', '')
            QMessageBox.information(qWindow, '通知', info, QMessageBox.Ok)
            pass
        else:
            error = data.get('error', '')
            QMessageBox.warning(qWindow, "错误", error, QMessageBox.Ok)

    itemdata=button.property('itemdata')
    timestamp=itemdata['timestamp']
    sessionId=cookie.sessionId
    if not sessionId:
        QMessageBox.warning(qWindow, "警告", '请登录', QMessageBox.Ok)
        slot_to_login_page()
        return
    data = {
        'msg_type': REQUEST_TYPE_OF_CLIENT,
        'data': {
            'eventType': 'removeReocrd',
            'sessionId': sessionId,
            'timestamp': timestamp,
        }
    }
    CorrespondenceServer.postRequestToServer(callback=callback,requestData=data)

    pass
def handleSubmitRecord():
    def callback(m: dict):
        if m.get('http_result', HTTP_FAILED) == HTTP_FAILED:
            QMessageBox.warning(qWindow, "提示框", '获取请求失败，请检查当前网络状况! 若网络状态良好，请联系后台工作人员！', QMessageBox.Ok)
            return
        data = m.get('data', None)  # type:dict
        result = int(data.get('result', ERROR_CODE))
        if result == SUCCESSED_CODE:
            info = data.get('info', '')
            QMessageBox.information(qWindow, '通知', info, QMessageBox.Ok)
            pass
        else:
            error = data.get('error', '')
            QMessageBox.warning(qWindow, "错误", error, QMessageBox.Ok)
    print('点击率')
    sessionId=cookie.sessionId
    if not sessionId:
        QMessageBox.warning(qWindow, "警告", '请登录', QMessageBox.Ok)
        slot_to_login_page()
        return

    money = mainPage.inputMoney.text()
    description = mainPage.inputDescription.toPlainText()
    dateTime = None
    recordType = None
    if not money.isnumeric() or int(money)<0:
        QMessageBox.warning(qWindow, '警告', '金额必须是非负数', QMessageBox.Ok)
        mainPage.inputMoney.setText('0')
        return
    if mainPage.radChoseIncome.isChecked():
        recordType='income'
        money=int(money)
    else:
        recordType='expenditure '
        money=-int(money)

    isCheck=mainPage.rabUseSystemTime.isChecked()
    if isCheck:
        dateTime = QtCore.QDateTime().currentDateTime().toString(QtCore.Qt.ISODate)
    else:
        dateTime=mainPage.inputDate.dateTime().toString(QtCore.Qt.ISODate)
    data = {
            'msg_type': REQUEST_TYPE_OF_CLIENT,
            'data': {
                'eventType': 'submitBooksRecord',
                'sessionId': sessionId,
                'recordType': recordType,
                'money':money,
                'description':description,
                'dateTime':dateTime
            }
        }
    CorrespondenceServer.postRequestToServer(callback=callback,requestData=data)
# 获取用户账单
def handleGetUserBooks():
    def callback(m: dict):
        if m.get('http_result', HTTP_FAILED) == HTTP_FAILED:
            QMessageBox.warning(qWindow, "提示框", '获取请求失败，请检查当前网络状况! 若网络状态良好，请联系后台工作人员！', QMessageBox.Ok)
            return
        data = m.get('data', None)  # type:dict
        print('handleGetUserBooks:',data)
        result = int(data.get('result', ERROR_CODE))
        if result == SUCCESSED_CODE:
            records = data.get('records', {})
            #  返回的 records 数据中存在不符合格式的 单引号,json 无法解析
            records=[ json.loads(item.replace("'","\"")) for item in records]
            cookie.records=records
            cookie.balance=data.get('balance',{}).get('balance',0)
            mainPage.setRecordsData(records)
            mainPage.setBalance(cookie.balance)
        else:
            error = data.get('error', '')
            QMessageBox.warning(qWindow, "错误", error, QMessageBox.Ok)
    print('点击率')
    sessionId=cookie.sessionId
    if not sessionId:
        QMessageBox.warning(qWindow, "警告", '请登录', QMessageBox.Ok)
        slot_to_login_page()
        return

    data = {
        'msg_type': REQUEST_TYPE_OF_CLIENT,
        'data': {
            'eventType': 'getUserBooks',
            'sessionId': sessionId,
        }
    }
    CorrespondenceServer.postRequestToServer(callback=callback,requestData=data)

import sys

# 异步http类
class SyncOpertion(QThread):
    signal = pyqtSignal(dict)  # 括号里填写信号传递的参数
    # 函数
    fun = None  # type:function
    # 参数
    fun_argvs = None

    def operationConnect(self, fun, argvs):
        self.fun = fun
        self.fun_argvs = argvs

    def __init__(self):
        super().__init__()

    def __del__(self):
        self.wait()

    def run(self):
        # 进行任务操作
        re = self.fun(**self.fun_argvs)
        self.signal.emit(re)  # 发射信号


class Service(object):
    def __init__(self):
        pass

    def login(self):
        pass

SERVER_ADDRESS_LIST = []
class CorrespondenceServer:
    @classmethod
    def __run(cls,requestData):
        data=None
        for address in SERVER_ADDRESS_LIST:
            d = HttpUtil.http_request(target_address=address, requestData=requestData, timeout=3)
            if d:
                data=d
                break
        if data:
            return {'http_result': HTTP_SUCCESSED, 'data': data}
        else:
            return {'http_result': HTTP_FAILED, 'data': data}

    @classmethod
    def postRequestToServer(cls,callback,requestData):
        sync = SyncOpertion()
        sync.signal.connect(callback)
        sync.operationConnect(cls.__run, {'requestData': requestData})
        sync.start()
        pass
# type:list

def loadClientConfiguration(path='client_configuration.json'):
    try:
        jsonstr = open(path).read()
        configuration = json.loads(jsonstr)
    except Exception as e:
        print('error:加载配置文件失败!')
        sys.exit()
    return configuration
# 加载服务器的信息
def loadServerInfo():
    global SERVER_ADDRESS_LIST
    configuration=loadClientConfiguration(path='client_configuration.json')
    server_address_list=configuration['server_address_list']
    SERVER_ADDRESS_LIST=[(address['host'],address['port']) for address in server_address_list]

if __name__ == '__main__':
    loadServerInfo()
    app = QApplication(sys.argv)
    qWindow = QMainWindow()
    loginPage.setupUi(qWindow)
    qWindow.show()
    # dateTime = QtCore.QDateTime().currentDateTime().toString(QtCore.Qt.ISODate)
    # print(dateTime)
    sys.exit(app.exec_())
    pass
