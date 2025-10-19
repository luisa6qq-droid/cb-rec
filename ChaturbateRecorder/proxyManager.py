import requests
import random
import time
import datetime
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
        self.log_file = 'proxy_debug.log'

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
                self.log(f'Fetching from: {source}')
                response = requests.get(source, timeout=8)
                count_before = len(proxy_list)
                for line in response.text.split('\n'):
                    line = line.strip()
                    if line and ':' in line and not line.startswith('#'):
                        if 'http://' not in line and 'https://' not in line:
                            proxy_list.append(f'http://{line}')
                        else:
                            proxy_list.append(line)
                count_after = len(proxy_list)
                self.log(f'  -> Got {count_after - count_before} proxies from this source')
            except Exception as e:
                self.log(f'  -> Failed to fetch from {source}: {e}')
                continue

        try:
            sources = [
                'https://www.sslproxies.org/',
                'https://free-proxy-list.net/',
                'https://www.us-proxy.org/'
            ]

            for source in sources:
                try:
                    self.log(f'Scraping HTML from: {source}')
                    response = requests.get(source, timeout=8)
                    soup = BeautifulSoup(response.content, 'html.parser')
                    table = soup.find('table', {'class': 'table table-striped table-bordered'})

                    count_before = len(proxy_list)
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
                    count_after = len(proxy_list)
                    self.log(f'  -> Got {count_after - count_before} proxies from HTML scraping')
                except Exception as e:
                    self.log(f'  -> Failed to scrape {source}: {e}')
                    continue
        except Exception as e:
            self.log(f'Error in HTML scraping section: {e}')

        unique_proxies = list(set(proxy_list))
        self.log(f'Total unique proxies after deduplication: {len(unique_proxies)}')
        return unique_proxies

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

    def log(self, message):
        timestamp = datetime.datetime.now().strftime('%Y-%m-%d %H:%M:%S')
        log_message = f'[{timestamp}] {message}\n'
        try:
            with open(self.log_file, 'a') as f:
                f.write(log_message)
        except:
            pass
        print(log_message.strip())

    def update_proxies(self, force=False):
        current_time = time.time()

        if not force and (current_time - self.last_update) < self.update_interval:
            return

        self.lock.acquire()
        try:
            self.log('='*60)
            self.log('Starting proxy fetch cycle')
            self.log('Fetching free proxies from multiple sources...')
            new_proxies = self.fetch_free_proxies()
            self.log(f'Found {len(new_proxies)} total proxies from all sources')

            self.proxies = new_proxies
            self.last_update = current_time

            if len(new_proxies) == 0:
                self.log('WARNING: No proxies found from any source!')
                return

            self.log(f'Testing proxies (up to 50 tests, stopping at 10 working)...')
            tested = 0
            working_found = 0
            for proxy in self.proxies[:100]:
                if len(self.working_proxies) >= 10:
                    self.log('Reached 10 working proxies, stopping tests')
                    break
                if tested >= 50:
                    self.log('Reached 50 test attempts, stopping')
                    break
                if proxy not in self.failed_proxies:
                    self.log(f'Testing proxy {tested+1}: {proxy}')
                    if self.test_proxy(proxy):
                        if proxy not in self.working_proxies:
                            self.working_proxies.append(proxy)
                            working_found += 1
                            self.log(f'✓ WORKING proxy #{working_found}: {proxy}')
                    else:
                        self.log(f'✗ Failed: {proxy}')
                tested += 1

            self.log(f'Testing complete. Total working proxies: {len(self.working_proxies)}')
            self.log('='*60)
        except Exception as e:
            self.log(f'ERROR in update_proxies: {e}')
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
