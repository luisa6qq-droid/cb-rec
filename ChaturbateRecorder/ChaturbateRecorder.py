import time
import datetime
import os
import threading
import sys
import configparser
import streamlink
import subprocess
import queue
import requests
from proxyManager import ProxyManager

if os.name == 'nt':
    import ctypes
    kernel32 = ctypes.windll.kernel32
    kernel32.SetConsoleMode(kernel32.GetStdHandle(-11), 7)

mainDir = sys.path[0]
Config = configparser.ConfigParser()
setting = {}

recording = []

hilos = []

proxy_manager = ProxyManager()

def cls():
    os.system('cls' if os.name == 'nt' else 'clear')
    
def readConfig():
    global setting

    Config.read(mainDir + '/config.conf')
    setting = {
        'save_directory': Config.get('paths', 'save_directory'),
        'wishlist': Config.get('paths', 'wishlist'),
        'interval': int(Config.get('settings', 'checkInterval')),
        'postProcessingCommand': Config.get('settings', 'postProcessingCommand'),
        }
    try:
        setting['postProcessingThreads'] = int(Config.get('settings', 'postProcessingThreads'))
    except ValueError:
        if setting['postProcessingCommand'] and not setting['postProcessingThreads']:
            setting['postProcessingThreads'] = 1
    
    if not os.path.exists(f'{setting["save_directory"]}'):
        os.makedirs(f'{setting["save_directory"]}')

def postProcess():
    while True:
        while processingQueue.empty():
            time.sleep(1)
        parameters = processingQueue.get()
        model = parameters['model']
        path = parameters['path']
        filename = os.path.split(path)[-1]
        directory = os.path.dirname(path)
        file = os.path.splitext(filename)[0]
        subprocess.call(setting['postProcessingCommand'].split() + [path, filename, directory, model,  file, 'cam4'])

class Modelo(threading.Thread):
    def __init__(self, modelo):
        threading.Thread.__init__(self)
        self.modelo = modelo
        self._stopevent = threading.Event()
        self.file = None
        self.online = None
        self.lock = threading.Lock()

    def run(self):
        global recording, hilos
        isOnline = self.isOnline()
        if isOnline == False:
            self.online = False
        else:
            self.online = True
            self.file = os.path.join(setting['save_directory'], self.modelo, f'{datetime.datetime.fromtimestamp(time.time()).strftime("%Y.%m.%d_%H.%M.%S")}_{self.modelo}.mp4')
            try:
                session = streamlink.Streamlink()

                max_attempts = 3
                fd = None

                for attempt in range(max_attempts):
                    try:
                        with open('model_check.log', 'a') as f:
                            f.write(f'[{self.modelo}] Recording attempt {attempt+1}\\n')

                        if attempt == 0:
                            with open('model_check.log', 'a') as f:
                                f.write(f'[{self.modelo}] Trying direct stream connection...\\n')
                            streams = session.streams(f'hlsvariant://{isOnline}')
                        else:
                            proxy = proxy_manager.get_random_proxy()
                            if proxy:
                                proxy_url = proxy.get('https') or proxy.get('http')
                                with open('model_check.log', 'a') as f:
                                    f.write(f'[{self.modelo}] Trying with proxy: {proxy_url}\\n')
                                session.set_option('http-proxy', proxy_url)
                                streams = session.streams(f'hlsvariant://{isOnline}')
                            else:
                                with open('model_check.log', 'a') as f:
                                    f.write(f'[{self.modelo}] No proxy available for stream\\n')
                                break

                        stream = streams['best']
                        fd = stream.open()
                        with open('model_check.log', 'a') as f:
                            f.write(f'[{self.modelo}] \u2713 Stream opened successfully!\\n')
                        break
                    except Exception as e:
                        with open('model_check.log', 'a') as f:
                            f.write(f'[{self.modelo}] Stream attempt {attempt+1} failed: {e}\\n')
                        if attempt < max_attempts - 1:
                            time.sleep(2)
                            continue
                        else:
                            raise e

                if not fd:
                    raise Exception('Failed to open stream after all attempts')
                if not isModelInListofObjects(self.modelo, recording):
                    os.makedirs(os.path.join(setting['save_directory'], self.modelo), exist_ok=True)
                    with open(self.file, 'wb') as f:
                        self.lock.acquire()
                        recording.append(self)
                        for index, hilo in enumerate(hilos):
                            if hilo.modelo == self.modelo:
                                del hilos[index]
                                break
                        self.lock.release()
                        while not (self._stopevent.isSet() or os.fstat(f.fileno()).st_nlink == 0):
                            try:
                                data = fd.read(1024)
                                f.write(data)
                            except:
                                fd.close()
                                break
                    if setting['postProcessingCommand']:
                            processingQueue.put({'model': self.modelo, 'path': self.file})
            except Exception as e:
                with open('log.log', 'a+') as f:
                    f.write(f'\n{datetime.datetime.now().strftime("%d/%m/%Y %H:%M:%S")} EXCEPTION: {e}\n')
                self.stop()
            finally:
                self.exceptionHandler()

    def exceptionHandler(self):
        self.stop()
        self.online = False
        self.lock.acquire()
        for index, hilo in enumerate(recording):
            if hilo.modelo == self.modelo:
                del recording[index]
                break
        self.lock.release()
        try:
            file = os.path.join(os.getcwd(), self.file)
            if os.path.isfile(file):
                if os.path.getsize(file) <= 1024:
                    os.remove(file)
        except Exception as e:
            with open('log.log', 'a+') as f:
                f.write(f'\n{datetime.datetime.now().strftime("%d/%m/%Y %H:%M:%S")} EXCEPTION: {e}\n')

    def isOnline(self):
        log_msg = f'[{self.modelo}] Checking if online...'
        with open('model_check.log', 'a') as f:
            f.write(f'{log_msg}\n')

        try:
            resp = requests.get(f'https://chaturbate.com/api/chatvideocontext/{self.modelo}/', timeout=10)
            json_data = resp.json()
            with open('model_check.log', 'a') as f:
                f.write(f'[{self.modelo}] Direct connection response: {json_data}\n')

            hls_url = ''
            if 'hls_source' in json_data:
                hls_url = json_data['hls_source']
            if len(hls_url):
                with open('model_check.log', 'a') as f:
                    f.write(f'[{self.modelo}] ✓ Found stream via direct connection\n')
                return hls_url
            else:
                with open('model_check.log', 'a') as f:
                    f.write(f'[{self.modelo}] No stream in direct connection, trying proxy...\n')
        except Exception as e:
            with open('model_check.log', 'a') as f:
                f.write(f'[{self.modelo}] Direct connection failed: {e}\n')

        for attempt in range(3):
            try:
                proxy = proxy_manager.get_random_proxy()
                if proxy:
                    with open('model_check.log', 'a') as f:
                        f.write(f'[{self.modelo}] Attempt {attempt+1} with proxy: {proxy.get("http")}\n')

                    resp = requests.get(f'https://chaturbate.com/api/chatvideocontext/{self.modelo}/', proxies=proxy, timeout=15)
                    json_data = resp.json()
                    with open('model_check.log', 'a') as f:
                        f.write(f'[{self.modelo}] Proxy response: {json_data}\n')

                    hls_url = ''
                    if 'hls_source' in json_data:
                        hls_url = json_data['hls_source']
                    if len(hls_url):
                        with open('model_check.log', 'a') as f:
                            f.write(f'[{self.modelo}] ✓ Found stream via PROXY!\n')
                        return hls_url
                else:
                    with open('model_check.log', 'a') as f:
                        f.write(f'[{self.modelo}] No proxy available\n')
                    break
            except Exception as e:
                with open('model_check.log', 'a') as f:
                    f.write(f'[{self.modelo}] Proxy attempt {attempt+1} failed: {e}\n')
                proxy_manager.mark_proxy_failed(proxy)
                continue

        with open('model_check.log', 'a') as f:
            f.write(f'[{self.modelo}] ✗ Model offline or geo-blocked (no working proxy)\n')
        return False

    def stop(self):
        self._stopevent.set()

class CleaningThread(threading.Thread):
    def __init__(self):
        threading.Thread.__init__(self)
        self.interval = 0
        self.lock = threading.Lock()
        
    def run(self):
        global hilos, recording
        while True:
            self.lock.acquire()
            new_hilos = []
            for hilo in hilos:
                if hilo.is_alive() or hilo.online:
                    new_hilos.append(hilo)
            hilos = new_hilos
            self.lock.release()
            for i in range(10, 0, -1):
                self.interval = i
                time.sleep(1)

class ProxyUpdateThread(threading.Thread):
    def __init__(self):
        threading.Thread.__init__(self)
        self.daemon = True

    def run(self):
        while True:
            try:
                proxy_manager.update_proxies()
                time.sleep(300)
            except:
                time.sleep(60)

class AddModelsThread(threading.Thread):
    def __init__(self):
        threading.Thread.__init__(self)
        self.wanted = []
        self.lock = threading.Lock()
        self.repeatedModels = []
        self.counterModel = 0

    def run(self):
        global hilos, recording
        lines = open(setting['wishlist'], 'r').read().splitlines()
        self.wanted = (x for x in lines if x)
        self.lock.acquire()
        aux = []
        for model in self.wanted:
            model = model.lower()
            if model in aux:
                self.repeatedModels.append(model)
            else:
                aux.append(model)
                self.counterModel = self.counterModel + 1
                if not isModelInListofObjects(model, hilos) and not isModelInListofObjects(model, recording):
                    thread = Modelo(model)
                    thread.start()
                    hilos.append(thread)
        for hilo in recording:
            if hilo.modelo not in aux:
                hilo.stop()
        self.lock.release()

def isModelInListofObjects(obj, lista):
    result = False
    for i in lista:
        if i.modelo == obj:
            result = True
            break
    return result

if __name__ == '__main__':
    readConfig()
    if setting['postProcessingCommand']:
        processingQueue = queue.Queue()
        postprocessingWorkers = []
        for i in range(0, setting['postProcessingThreads']):
            t = threading.Thread(target=postProcess)
            postprocessingWorkers.append(t)
            t.start()

    print('Initializing proxy system...')
    proxyUpdateThread = ProxyUpdateThread()
    proxyUpdateThread.start()

    cleaningThread = CleaningThread()
    cleaningThread.start()
    while True:
        try:
            readConfig()
            addModelsThread = AddModelsThread()
            addModelsThread.start()
            i = 1
            for i in range(setting['interval'], 0, -1):
                cls()
                if len(addModelsThread.repeatedModels): print('The following models are more than once in wanted: [\'' + ', '.join(modelo for modelo in addModelsThread.repeatedModels) + '\']')
                print(f'{len(hilos):02d} alive Threads (1 Thread per non-recording model), cleaning dead/not-online Threads in {cleaningThread.interval:02d} seconds, {addModelsThread.counterModel:02d} models in wanted')
                print(f'Online Threads (models): {len(recording):02d}')
                print(f'Working proxies available: {proxy_manager.get_proxy_count()}')
                print('The following models are being recorded:')
                for hiloModelo in recording: print(f'  Model: {hiloModelo.modelo}  -->  File: {os.path.basename(hiloModelo.file)}')
                print(f'Next check in {i:02d} seconds\r', end='')
                time.sleep(1)
            addModelsThread.join()
            del addModelsThread, i
        except:
            break
