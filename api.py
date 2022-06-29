import requests
import websocket
import time,csv
from threading import Thread
import json
import ativos
import datetime
import random
import logging
import login_init,configparser
from dateutil import tz


try:
    arquivo = configparser.RawConfigParser()
    arquivo.read('mode.ini')
    mode=int(arquivo.get('mode','mode'))
except:
    with open('mode.ini','w',newline='') as file:
        wri = csv.writer(file)
        wri.writerow(['[mode]'])
        wri.writerow(['mode=0'])
    mode=0

def confset(sec,var,value):
    config = configparser.RawConfigParser()
    config.optionxform = str
    config.read("conf.ini")
    config.set(sec, var, value)
    with open("conf.ini", 'w') as configfile:
        config.write(configfile)

def login_get():
    arquivo = configparser.RawConfigParser()
    arquivo.read('conf.ini')
    return arquivo.get(broker,'email'),arquivo.get(broker,'senha'),arquivo.get(broker,'session')

#{"name":"sendMessage","request_id":"53","local_time":9904,"msg":{"name":"get-user-profile-client","version":"1.0","body":{"user_id":82805494}}}
class IQOption():
    """CONFIGURANDO ATIVOS"""
    instruments_categories = ["cfd","forex","crypto"]
    top_assets_categories = ["forex","crypto","binary"]
    all_profit={'binary':{},'turbo':{},'digital':{}}
    instruments_to_id = ativos.ACTIVES
    conection_state = True
    id_to_instruments = {y:x for x,y in ativos.ACTIVES.items()}
    ACTIVES_BOOL_TURBO = {x:False for x,y in ativos.ACTIVES.items()}
    ACTIVES_BOOL_BINARY = {x:False for x,y in ativos.ACTIVES.items()}
    ACTIVES_BOOL_DIGITAL = {x:False for x,y in ativos.ACTIVES.items()}
    timeout_reicive_socket_message=5
    socket_message={'request_id':'0'}
    """INFORMAÇÔES DA CONTA"""
    login_state=''
    digital_load=False
    direction_char = {'CALL':'C', 'PUT':'P'}
    currency_char_types = {'BRL':'R$', 'USD':'$', 'EUR':'€'}
    user_id=''
    currency=''
    currency_char=''
    balance_type=0
    balance_id=''
    balance=0
    balance_actualy=''
    reconection_state=False
    reconex_n=0
    operations_times={}
    auth_two_factor=None

    def __init__(self,args):
        """Gera as URLS necessárias"""
        self.sock_on = True
        self.args = args
        self.username = args['username']
        self.password = args['password']
        self.host = "iqoption.com"
        self.session = requests.Session()
        self.generate_urls()
        self.socket = websocket.WebSocketApp(self.socket_url,on_open=self.on_socket_connect,on_message=self.on_socket_message,on_close=self.on_socket_close,on_error=self.on_socket_error)

    def wait_var(self, var):
        a=0
        while (getattr(self,var) == '') and a<=5:
            time.sleep(0.1)
            a+=0.1
        #print(round(a,2),'s')

    def generate_urls(self):
        """Gera as URLS necessárias"""
        self.api_url = "https://{}/api/".format(self.host)
        self.socket_url = "wss://{}/echo/websocket".format(self.host)
        self.login_url = 'https://auth.iqoption.com/api/v1.0/login'
        self.profile_url = self.api_url+"profile"
        self.change_account_url = self.profile_url+"/"+"changebalance"
        self.getprofile_url = self.api_url+"getprofile"

    def login(self, *args):
        #login_status
        #0 - Sucess
        #1 - Senha ou login errado
        print('fazendo login')
        self.login_status = 0

        if self.socket.keep_running==True:self.socket.close()
        else:
            def new_session():
                data = {"email":self.username,"password":self.password}
                self.__login_response = self.session.request(url=self.login_url,data=data,method="POST")
                requests.utils.add_dict_to_cookiejar(self.session.cookies, dict(platform="9"))
                json_login_response = self.__login_response.json()
                self.__ssid = self.__login_response.cookies["ssid"]
                confset('iqoption','email',self.username)
                confset('iqoption','senha',self.password)
                confset('iqoption','session',self.__ssid)
                return self.__ssid
            init_login=login_get()
            if init_login[0]!=self.username or init_login[2] =='':new_session()
            else:self.__ssid=init_login[2]
            self.start_socket_connection()
            self.login_state=''
            self.wait_var('login_state')
            if self.login_state == False:
                new_session()
                self.start_socket_connection()
                self.login_state=''
                self.wait_var('login_state')
                if self.login_state == False:
                    self.login_status = 1
            else:
                self.balance=''
                self.wait_var('balance')
                self.sock_on=True
                return True

    def on_socket_message(self,message,sock):
        #print(message) ###DEBUG###
        message = json.loads(message)
        if 'msg' in message:
            if 'request_id' in message:
                self.socket_message=message
            if message['name']=='profile':
                if message['msg'] == False:
                    self.login_state=False
                else:
                    self.login_state=True
                    self.start_profile(message['msg'])
                    print(message['msg'])
            elif message['name']=='balance-changed':
                self.balance_changed(message['msg'])
                print('2222',message['msg'])

            elif message['name']=='balances':
                self.update_balance(message['msg'])
                print('1111',message['msg'])

            elif message['name']=='history-positions':pass
            elif message['name']=='timeSync':
                self.timeSync=int(str(message['msg'])[:-3])
            elif message['name']=='heartbeat':pass
        else:
            print(message)


    def on_socket_connect(self,sock):
        """ Inicia a conexão com socket """
        self.initial_subscriptions()
        #self.get_assets_id()

    def on_socket_error(self,error,sock):
        print(error)

    def on_socket_close(self):
        self.sock_on=False

    def start_socket_connection(self):
        self.socket_thread = Thread(target=self.socket.run_forever).start()

    def send_socket_message(self,name,message_send,wait_response=True,name_response='',force_response=False):
        if message_send != '':
            for x in range(3):
                request_id=random.randint(0, 5000)
                data = {"name":name,'request_id':str(request_id),"msg":message_send}
                self.socket.send(json.dumps(data))
                if wait_response==False:return
                a=0
                while ((int(self.socket_message['request_id']) != request_id) or (self.socket_message['name']!=name_response and name_response!='')) and a<self.timeout_reicive_socket_message:
                    time.sleep(0.005)
                    a+=0.005
                #print(round(a,2),'s')
                if (int(self.socket_message['request_id']) == request_id) or (self.socket_message['name']==name_response and name_response!=''):return self.socket_message['msg']
                if force_response==True:return False
                elif a<self.timeout_reicive_socket_message:return self.socket_message['msg']
            if force_response==True:return False
            if 'msg' in self.socket_message:return self.socket_message['msg']
            return False


    def initial_subscriptions(self):
        self.send_socket_message("ssid",self.__ssid,False)
        self.send_socket_message("subscribe","tradersPulse",False)


    def start_profile(self,msg):
        """ATUALIZA PROFILE"""
        if self.balance_actualy == '':
            self.profile_init=msg
            self.currency=msg['currency']
            self.currency_char=msg['currency_char']
            self.balances=msg['balances']
            self.formatBalances(self.balances)
            self.auth_two_factor=msg['auth_two_factor']
            self.user_id=msg['id']


    def get_profile_init(self):
        return self.profile_init


    def get_balance(self):
        return round(self.balance,2)


    def change_balance(self,balance):
        self.balance_actualy=balance
        self.update_balance()
        return self.balance_actualy,self.balance

    def get_balance_ids(self, balances):
        self.accepted_type = {'REAL': None, 'PRACTICE': None}
        for i in range(7):
            if balances[i]['type'] == 1:
                self.accepted_type['REAL'] = balances[i]['id']
            elif balances[i]['type'] == 4:
                self.accepted_type['PRACTICE'] = balances[i]['id']

    def timestamp_to_date(self,x):
        hora = datetime.datetime.strptime(datetime.datetime.utcfromtimestamp(x).strftime('%d/%m/%Y %H:%M'), '%d/%m/%Y %H:%M')
        hora = hora.replace(tzinfo=tz.gettz('GMT'))
        return str(hora.astimezone(tz.gettz('America/Sao Paulo')).strftime("%d/%m/%Y %H:%M"))+":00"

    def get_expiration_binary(self, duration):
        exp = self.timeSync+360
        exp_str=self.timestamp_to_date(exp)
        minute=int(exp_str[14:-3])
        rest_minutes=0
        expiration_ciles=round(duration/15)
        for x in range(expiration_ciles):
            while True:
                minute+=1
                if minute == 60:minute=0
                rest_minutes+=1
                if(minute==0 or minute==15 or minute==30 or minute==45):break
        exp+=rest_minutes*60
        return str(exp)[:-2]+'00'

    def get_expiration_time(self, duration):
        exp = self.timeSync
        if duration >= 1 and duration <= 5:
            option = 3#"turbo"
            if (exp % 60) > 30:
                exp = exp - (exp % 60) + 60*(duration+1)
            else:
                exp = exp - (exp % 60)+60*(duration)
        elif duration > 5:
            option = 1#"binary"
            exp=self.get_expiration_binary(duration)
        return exp, option


    def update_balance(self,msg=False):
        """Pegar os ids real e demo"""
        if(msg == False):
            message={"name":"get-balances","version":"1.0"}
            balanceslist=self.send_socket_message('sendMessage',message,True,'balances')
        else:balanceslist=msg
        self.res=balanceslist
        for i in range(len(balanceslist)):
            if balanceslist[i]['type'] == 1 and self.balance_actualy=='REAL':
                self.balance = balanceslist[i]['amount']
                self.currency=balanceslist[i]['currency']
                self.balance_id=balanceslist[i]['id']
            elif balanceslist[i]['type'] == 4 and self.balance_actualy=='PRACTICE':
                self.balance = balanceslist[i]['amount']
                self.currency=balanceslist[i]['currency']
                self.balance_id=balanceslist[i]['id']
        self.currency_char=self.currency_char_types[self.currency]


    def balance_changed(self,balance):
        balance_ =  balance['current_balance']
        balance_id = balance['current_balance']['id']
        self.balances_json[balance_id]['valor'] = balance_['amount']
        for x in self.balance_list:
            if x['id'] == balance_id:
                x['valor'] = balance_['amount']
                break

    def formatBalances(self):
        self.balances_json = {}
        self.balance_list = []
        self.types = {1:'r',4:'d',2:'o',3:'o',5:'o'}
        for b in self.balances:
            balance = {b['id']:{'valor':b['amount'],'type':self.types[b['type']],'currency':b['currency']}}
            self.balances_json.update(balance)
            balance_l = {'id':b['id'], 'valor':b['amount'],'type':self.types[b['type']],'currency':b['currency']}
            self.balance_list.append(balance_l)


    def get_instruments(self):
        for typ in self.instruments_categories: #categorias são "cfd","forex","crypto"
            self.send_socket_message("sendMessage",{"name":"get-instruments","version":"1.0","body":{"type":typ}})


    def get_top_assets(self,instruments=["turbo-option","digital-option","binary-option"]):
        res={}
        for x in instruments:
            asset=self.send_socket_message("sendMessage",{"name":"get-top-assets","version":"1.2","body":{"instrument_type":x}},name_response="top-assets",force_response=True)['data']
            res.update({x:asset})
        return res


    def update_candle_data(self,market_name,interval,start_time,end_time):
        """ Mantém a conexão aberta """
        chunk_size = int((end_time-start_time)/interval)+5
        msg={"active_id":self.instruments_to_id[market_name],
                                            "duration":interval,
                                            "chunk_size":chunk_size,
                                            "from":start_time,
                                            "till":end_time,
                                          }
        self.send_socket_message("candles",msg,False)


    def get_optioninfo(self,size):
        msg={"name":"portfolio.get-history-positions","version":"1.0","body":{"user_id":self.user_id,"user_balance_id":self.balance_id,"instrument_types":["turbo-option","binary-option","digital-option"],"offset":0,"limit":size}}
        return self.send_socket_message("sendMessage",msg,True,'history-positions',True)


    def buy(self,price,active,direction,exp):
        option=self.get_expiration_time(int(exp))
        active=self.instruments_to_id[active.upper()]
        men = {"name":"binary-options.open-option",
               "version":"1.0",
               "body":{"user_balance_id":self.balance_id,
                       "active_id":active,"option_type_id":option[1],
                       "direction":direction.lower(),
                       "expired":int(option[0]),
                       "refund_value":0,
                       "price":round(price,2)}}
        try:
            message=self.send_socket_message("sendMessage", men,force_response=True)
            if message != False:
                if 'id' in message:
                    return True, message['id']
        except:pass
        return False


    def buydigi(self,price,active,direction,exp):
        duration=self.get_digital_expiration(int(exp))
        ac=active
        """
        instrument_index=self.get_instruments(active)
        for x in instrument_index['instruments']:
            if int(x['expiration'])==int(duration[1]):
                instrument_index=x['index']
                break
        """

        active='do'+str(self.instruments_to_id[active.upper()])+'A'+(str(duration[0])[:8])+'D'+(duration[0][-4:])+'00T'+str(exp)+'M'+self.direction_char[direction.upper()]+'SPT'
        print(active)
        men={"name":"digital-options.place-digital-option",
                "version":"2.0","body":{"amount":str(round(price,2)),"asset_id":self.instruments_to_id[ac.upper()],"instrument_id":active,"instrument_index": 0,"user_balance_id":self.balance_id}}
        print(men)
        try:
            message=self.send_socket_message("sendMessage", men,force_response=True)
            if message != False:
                if 'id' in message:
                    return True, message['id']
        except:pass
        return False

    def check_win(self, idd, positions=[]):
        if positions==[]:
            positions=self.get_optioninfo(10)
        for x in positions['positions']:
            if 'order_ids' in x['raw_event']:
                if idd in x['raw_event']['order_ids']:
                    if 'close_profit' in x:
                        return {'profit':round(float(x['close_profit'])-float(x['invest']),2)}
                    if 'profit_amount' in x['raw_event']:
                        return {'profit':rotund(float(x['raw_event']['profit_amount'])-float(x['raw_event']['amount']),2)}
            if 'option_id' in x['raw_event']:
                if idd == x['raw_event']['option_id']:
                    if 'close_profit' in x:
                        return {'profit':round(float(x['close_profit'])-float(x['invest']),2)}
                    if 'profit_amount' in x['raw_event']:
                        return {'profit':round(float(x['raw_event']['profit_amount'])-float(x['raw_event']['amount']),2)}
        return False

    def check_win2(self, idd, positions):
        posi=positions
        for x in posi['positions']:
            try:
                if x['raw_event']['option_id']==idd:
                    if idd in self.operations_times:
                        if self.operations_times[idd]>self.timeSync+2:return False
                    else:self.operations_times.update({idd:x['raw_event']['expiration_time']})
                    if x['raw_event']['expiration_time']<=self.timeSync+2:
                        price=self.get_price_now(self.id_to_instruments[x['active_id']],60,True)
                        if x['raw_event']['expiration_time']==price['time']:
                            profit=round(float(x['expected_profit'])-float(x['invest']),2)
                            price=price['close']
                            if profit<0:
                                if (x['raw_event']['direction'] == 'call' and price<x['open_quote']) or (x['raw_event']['direction'] == 'put' and price>x['open_quote']):
                                    return {'profit':profit}
                            if profit>0:
                                if (x['raw_event']['direction'] == 'call' and price>x['open_quote']) or (x['raw_event']['direction'] == 'put' and price<x['open_quote']):
                                    return {'profit':profit}
                            if profit==0:
                                if (x['raw_event']['direction'] == 'call' and price==x['open_quote']) or (x['raw_event']['direction'] == 'put' and price==x['open_quote']):
                                    return {'profit':profit}
            except:
                try:
                    if idd in x['raw_event']['order_ids']:
                        if idd in self.operations_times:
                            if self.operations_times[idd]>self.timeSync+2:return False
                        else:self.operations_times.update({idd:int(str(x['raw_event']['instrument_expiration'])[:-3])})
                        if int(str(x['raw_event']['instrument_expiration'])[:-3])<=self.timeSync+2:
                            price=self.get_price_now(self.id_to_instruments[x['active_id']],60,True)
                            if int(str(x['raw_event']['instrument_expiration'])[:-3])==price['time']:
                                profit=round(float(x['expected_profit'])-float(x['invest']),2)
                                price=self.get_price_now(self.id_to_instruments[x['active_id']])['close']
                                if profit<0:
                                    if (x['raw_event']['instrument_dir'] == 'call' and price<x['open_quote']) or (x['raw_event']['instrument_dir'] == 'put' and price>x['open_quote']):
                                        return {'profit':profit}
                                if profit>0:
                                    if (x['raw_event']['instrument_dir'] == 'call' and price>x['open_quote']) or (x['raw_event']['instrument_dir'] == 'put' and price<x['open_quote']):
                                        return {'profit':profit}
                                if profit==0:
                                    if (x['raw_event']['instrument_dir'] == 'call' and price==x['open_quote']) or (x['raw_event']['instrument_dir'] == 'put' and price==x['open_quote']):
                                        return {'profit':profit}
                except:pass
        return False

            #Binario fechou 'result'
            #Digital fechou 'result'
            #Binaria fechou na mão 'amount'-'profit_amount'

    def get_digital_expiration(self, duration):
        tim_=time.gmtime()
        tim = datetime.datetime.fromtimestamp(time.mktime(tim_))
        minute = tim.strftime('%M')
        seconds = int(tim.strftime('%S'))
        if duration==5:
            minute=int(minute[1:])
            if minute<5:
                duration=5-minute
            if minute>=5 or (minute==4 and seconds>=30):
                duration=10-minute
                if minute==9 and seconds>=30:
                    duration=6

        if duration==15:
            minute=int(minute)
            if (minute >= 0 and minute < 15):
                    duration=15-minute
            if (minute >= 15 and minute < 30 or (minute==14 and seconds>=30)):
                    duration=30-minute
            if (minute >= 30 and minute < 45 or (minute==29 and seconds>=30)):
                    duration=45-minute
            if (minute >= 45 and minute < 60 or (minute==44 and seconds>=30)):
                    duration=60-minute
            if (minute==59 and seconds>=30):
                    duration=16
        if duration==1:
            if seconds>=30:
                duration=2
        tim_=datetime.datetime.timestamp(tim)+(duration*60)
        time_=self.timeSync+(duration*60)
        time_=datetime.datetime.fromtimestamp(time_)
        time_=time_.replace(second=00)
        time_=datetime.datetime.timestamp(time_)
        tim = datetime.datetime.fromtimestamp(tim_)
        tim=str(tim.replace(second=00))
        tim=tim.replace(' ','')
        tim=tim.replace(':','')
        tim=tim.replace('-','')
        tim=str(int(int(tim)/100))
        return tim,time_


    def get_open_options(self,size=20,instrument_types=["turbo-option","binary-option","digital-option"]):
        msg={"name":"portfolio.get-positions",
            "version":"3.0",
            "body":{"offset":0,
                 "limit":size,
                 "user_balance_id":self.balance_id,
                 "instrument_types":instrument_types}}

        return self.send_socket_message("sendMessage",msg, True, 'positions',True)

    def get_initialization_data(self):
        msg={"name":"get-initialization-data","version":"3.0","body":{}}
        data= self.send_socket_message("sendMessage",msg,True,'initialization-data',True)
        return data


    def get_underlying_list(self):
        msg={"name": "get-underlying-list",
                                    "version": "2.0",
                                    "body": {"type": "digital-option"}
                                    }
        return self.send_socket_message("sendMessage",msg,True,'underlying-list',True)


    def get_open_assets(self):
        try:
            self.open_actives={'binary':self.ACTIVES_BOOL_BINARY,'turbo':self.ACTIVES_BOOL_TURBO,'digital':self.ACTIVES_BOOL_DIGITAL}
            actives=self.get_initialization_data()
            actives_digital=self.get_underlying_list()['underlying']
            if 'binary' in actives:
                for x in actives['binary']['actives']:
                    if actives['binary']['actives'][x]['enabled'] == True:
                        self.open_actives['binary'].update({actives['binary']['actives'][x]['name'].replace('front.',''):True})
                for x in actives['turbo']['actives']:
                    if actives['turbo']['actives'][x]['enabled'] == True:
                        self.open_actives['turbo'].update({actives['turbo']['actives'][x]['name'].replace('front.',''):True})
            for x in actives_digital:
                underlying=x['underlying']
                for times in x['schedule']:
                    if times['open']<self.timeSync<times['close']:
                        data={underlying:True}
                        self.open_actives['digital'].update(data)
                        break
        except:self.open_actives={'binary':{x:True for x,y in ativos.ACTIVES.items()},'turbo':{x:True for x,y in ativos.ACTIVES.items()},'digital':{x:True for x,y in ativos.ACTIVES.items()}}
        return self.open_actives

    def get_assets_id(self):
        actives=self.get_initialization_data()
        actives_digital=self.get_underlying_list()['underlying']
        for x in actives['binary']['actives']:
            ativos.ACTIVES.update({actives['binary']['actives'][x]['name'].replace('front.',''):actives['binary']['actives'][x]['id']})
        for x in actives['turbo']['actives']:
            ativos.ACTIVES.update({actives['turbo']['actives'][x]['name'].replace('front.',''):actives['turbo']['actives'][x]['id']})
        for x in actives_digital:
            ativos.ACTIVES.update({x['underlying']:x['active_id']})
        return ativos.ACTIVES

    def get_all_actives(self):
        actives=self.get_initialization_data()
        actives_digital=self.get_underlying_list()['underlying']
        for x in actives['binary']['actives']:
            ativos.ACTIVES.update({actives['binary']['actives'][x]['name'].replace('front.',''):actives['binary']['actives'][x]['id']})
        for x in actives['turbo']['actives']:
            ativos.ACTIVES.update({actives['turbo']['actives'][x]['name'].replace('front.',''):actives['turbo']['actives'][x]['id']})
        for x in actives_digital:
            ativos.ACTIVES.update({x['underlying']:x['active_id']})
        self.instruments_to_id = ativos.ACTIVES
        self.id_to_instruments = {y:x for x,y in ativos.ACTIVES.items()}
        self.ACTIVES_BOOL_TURBO = {x:False for x,y in ativos.ACTIVES.items()}
        self.ACTIVES_BOOL_BINARY = {x:False for x,y in ativos.ACTIVES.items()}
        self.ACTIVES_BOOL_DIGITAL = {x:False for x,y in ativos.ACTIVES.items()}
        return ativos.ACTIVES

    def get_all_profit(self):
        actives=self.get_initialization_data()
        actives_digital=self.get_top_assets(['digital-option'])
        for x in actives['binary']['actives']:
            try:
                data={actives['binary']['actives'][x]['name'].replace('front.',''):(100-actives['binary']['actives'][x]["option"]["profit"]["commission"])}
                self.all_profit['binary'].update(data)
            except:pass
        for x in actives['turbo']['actives']:
            try:
                data={actives['turbo']['actives'][x]['name'].replace('front.',''):(100-actives['turbo']['actives'][x]["option"]["profit"]["commission"])}
                self.all_profit['turbo'].update(data)
            except:pass
        for x in actives_digital['digital-option']:
            try:
                data={self.id_to_instruments[x['active_id']]:round(x['spot_profit']['value'],2)}
                self.all_profit['digital'].update(data)
            except:pass



        return self.all_profit


    def get_server_timestamp(self):
        return self.timeSync

    def check_connect(self):
        try:
            self.session.request(url='https://iqoption.com',method="GET")
            return True
        except:
            return False


    def get_history_trading(self,size=1):
        msg ={"name":"get-history",
        "version":"2.0",
        "body":{"user_balance_id":self.balance_id,
                "instrument_types":["binary-option","turbo-option"],
                "limit":size,
                "offset":0,},
        "microserviceName":"portfolio"}
        return self.send_socket_message("sendMessage",msg)
        #aa['total_equity'] - 3862.04999999999 = Lucro



    def get_candles(self,active,size=1,timef=60,close=False):
        msg={"name":"get-candles",
                    "version":"2.0",
                    "body":{"active_id":self.instruments_to_id[active],
                            "size":timef,
                            "count":size,
                            "only_closed":close}}
        return self.send_socket_message("sendMessage",msg)



    def get_price_now(self,active,timef=60,close=False):
        price=self.get_candles(active,1,timef,close)
        if close==False:time=int(str(price['candles'][0]['at'])[:-9])
        else:time=price['candles'][0]['to']
        return {'open':price['candles'][0]['open'],'close':price['candles'][0]['close'], 'time':time}

    def get_alerts(self,active):
        msg={"name":"get-alerts",
             "version":"1.0",
             "body":{"asset_id":self.instruments_to_id[active],
                     "type":""}}
        return self.send_socket_message("sendMessage",msg)


    def reconex(self):
        self.reconex_n+=1
        print('reconectando')
        try:
            if self.reconex_n > 1:
                time.sleep(2)
                while True:
                    try:
                        print('verificando')
                        if self.check_connect() == True:
                            try:
                                print('logando')
                                if self.login()==True:
                                    self.reconex_n=0
                                    time.sleep(2)
                                    return
                                else:time.sleep(300)
                            except:pass
                        else:time.sleep(3)
                    except:pass
        except:pass
        reconectando=False
