import requests
import random
import time
from threading import Lock
from bs4 import BeautifulSoup

class ProxyManager:
    def __init__(self):
        self.proxies = []
        self.working_proxies = []
        self.failed_proxies = set()
        self.lock = Lock()
        self.last_update = 0
        self.update_interval = 300

    def fetch_free_proxies(self):
        proxy_list = []

        api_sources = [
            'https://api.proxyscrape.com/v2/?request=displayproxies&protocol=http&timeout=10000&country=all&ssl=all&anonymity=all',
            'https://api.proxyscrape.com/v2/?request=displayproxies&protocol=https&timeout=10000&country=all&ssl=all&anonymity=all',
            'https://www.proxy-list.download/api/v1/get?type=http',
            'https://www.proxy-list.download/api/v1/get?type=https',
            'https://raw.githubusercontent.com/TheSpeedX/PROXY-List/master/http.txt',
            'https://raw.githubusercontent.com/ShiftyTR/Proxy-List/master/http.txt',
            'https://raw.githubusercontent.com/ShiftyTR/Proxy-List/master/https.txt',
            'https://raw.githubusercontent.com/monosans/proxy-list/main/proxies/http.txt',
            'https://raw.githubusercontent.com/monosans/proxy-list/main/proxies_anonymous/http.txt',
            'https://raw.githubusercontent.com/clarketm/proxy-list/master/proxy-list-raw.txt',
            'https://raw.githubusercontent.com/sunny9577/proxy-scraper/master/proxies.txt',
            'https://raw.githubusercontent.com/hendrikbgr/Free-Proxy-Repo/master/proxy_list.txt',
        ]

        for source in api_sources:
            try:
                response = requests.get(source, timeout=8)
                for line in response.text.split('\n'):
                    line = line.strip()
                    if line and ':' in line and not line.startswith('#'):
                        if 'http://' not in line and 'https://' not in line:
                            proxy_list.append(f'http://{line}')
                        else:
                            proxy_list.append(line)
            except:
                continue

        try:
            sources = [
                'https://www.sslproxies.org/',
                'https://free-proxy-list.net/',
                'https://www.us-proxy.org/'
            ]

            for source in sources:
                try:
                    response = requests.get(source, timeout=8)
                    soup = BeautifulSoup(response.content, 'html.parser')
                    table = soup.find('table', {'class': 'table table-striped table-bordered'})

                    if table:
                        for row in table.find('tbody').find_all('tr'):
                            cols = row.find_all('td')
                            if len(cols) >= 7:
                                ip = cols[0].text.strip()
                                port = cols[1].text.strip()
                                https = cols[6].text.strip()

                                if https == 'yes':
                                    proxy_list.append(f'https://{ip}:{port}')
                                else:
                                    proxy_list.append(f'http://{ip}:{port}')
                except:
                    continue
        except:
            pass

        return list(set(proxy_list))

    def test_proxy(self, proxy, test_url='http://www.google.com'):
        try:
            proxies = {
                'http': proxy,
                'https': proxy
            }
            response = requests.get(test_url, proxies=proxies, timeout=5)
            if response.status_code == 200:
                return True
        except:
            pass
        return False

    def update_proxies(self, force=False):
        current_time = time.time()

        if not force and (current_time - self.last_update) < self.update_interval:
            return

        self.lock.acquire()
        try:
            print('Fetching free proxies...')
            new_proxies = self.fetch_free_proxies()
            print(f'Found {len(new_proxies)} proxies from free sources')

            self.proxies = new_proxies
            self.last_update = current_time

            print('Testing proxies (testing up to 50 proxies)...')
            tested = 0
            for proxy in self.proxies[:100]:
                if len(self.working_proxies) >= 10:
                    break
                if tested >= 50:
                    break
                if proxy not in self.failed_proxies:
                    if self.test_proxy(proxy):
                        if proxy not in self.working_proxies:
                            self.working_proxies.append(proxy)
                            print(f'Working proxy found: {proxy}')
                tested += 1

            print(f'Total working proxies: {len(self.working_proxies)}')
        finally:
            self.lock.release()

    def get_random_proxy(self):
        self.lock.acquire()
        try:
            if not self.working_proxies:
                self.update_proxies(force=True)

            if self.working_proxies:
                proxy = random.choice(self.working_proxies)
                return {
                    'http': proxy,
                    'https': proxy
                }
            return None
        finally:
            self.lock.release()

    def mark_proxy_failed(self, proxy_dict):
        if not proxy_dict:
            return

        self.lock.acquire()
        try:
            proxy = proxy_dict.get('http') or proxy_dict.get('https')
            if proxy:
                self.failed_proxies.add(proxy)
                if proxy in self.working_proxies:
                    self.working_proxies.remove(proxy)
        finally:
            self.lock.release()

    def get_proxy_count(self):
        return len(self.working_proxies)
