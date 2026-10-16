# { "Depends": "py-genlayer:1jb45aa8ynh2a9c9xn3b7qqh8sm5q93hwfp7jqmwsfhh8jpz09h6" }
from genlayer import *
import json
from datetime import datetime, timezone


def timestamp() -> int:
    return int(datetime.now(timezone.utc).timestamp())


def safe_id(value: str, maximum: int) -> bool:
    return 1 <= len(value) <= maximum and all(c in "abcdefghijklmnopqrstuvwxyz0123456789-_" for c in value)


def document_url(value: str) -> bool:
    if not (value.startswith('https://') and len(value) <= 240 and '?' not in value and '#' not in value):
        return False
    host = value[8:].split('/')[0].lower()
    return ('.' in host and not host.startswith(('localhost', '127.', '10.', '192.168.', '172.'))
            and ':' not in host and '@' not in host and not host.endswith('.local'))


def host(value: str) -> str:
    return value[8:].split('/')[0].lower()


class AssetRegistry(gl.Contract):
    owner: Address
    count: u256
    records: TreeMap[u256, str]

    def __init__(self) -> None:
        self.owner = gl.message.sender_address
        self.count = u256(0)

    @gl.public.write
    def register_asset(self, symbol: str, coingecko_id: str, coinpaprika_id: str,
                       issuer_url: str, independent_url: str, terms: str,
                       lower_price_bps: u256, upper_price_bps: u256,
                       predecessor: u256) -> u256:
        if not (2 <= len(symbol) <= 12 and symbol.isascii() and symbol.isalnum() and symbol == symbol.upper()):
            raise gl.vm.UserError('invalid asset symbol')
        if not safe_id(coingecko_id, 60) or not safe_id(coinpaprika_id, 60):
            raise gl.vm.UserError('invalid immutable market identifiers')
        if not document_url(issuer_url) or not document_url(independent_url):
            raise gl.vm.UserError('only bounded HTTPS public sources permitted')
        if host(issuer_url) == host(independent_url):
            raise gl.vm.UserError('issuer and corroborating publisher must be independent domains')
        if not (30 <= len(terms) <= 1200):
            raise gl.vm.UserError('define explicit asset and impairment policy')
        if lower_price_bps < u256(8500) or lower_price_bps > u256(9900):
            raise gl.vm.UserError('lower trigger outside supported boundary')
        if upper_price_bps < u256(10100) or upper_price_bps > u256(11500):
            raise gl.vm.UserError('upper trigger outside supported boundary')
        if predecessor != u256(0):
            if predecessor > self.count:
                raise gl.vm.UserError('unknown predecessor')
            prior = json.loads(self.records[predecessor])
            if prior['creator'] != str(gl.message.sender_address):
                raise gl.vm.UserError('successor must be authored by profile owner')
            if prior['symbol'] != symbol:
                raise gl.vm.UserError('successor cannot change the represented symbol')
        self.count += u256(1)
        key = self.count
        record = {'id': int(key), 'creator': str(gl.message.sender_address),
                  'symbol': symbol, 'coingecko_id': coingecko_id,
                  'coinpaprika_id': coinpaprika_id,
                  'issuer_url': issuer_url, 'independent_url': independent_url,
                  'terms': terms, 'lower_bps': int(lower_price_bps),
                  'upper_bps': int(upper_price_bps), 'predecessor': int(predecessor),
                  'created_at': timestamp(), 'chain_id': int(gl.message.chain_id)}
        self.records[key] = json.dumps(record, sort_keys=True, separators=(',', ':'))
        return key

    @gl.public.view
    def get_asset(self, asset_id: u256) -> str:
        if asset_id == u256(0) or asset_id > self.count:
            raise gl.vm.UserError('unknown asset')
        return self.records[asset_id]

    @gl.public.view
    def get_asset_count(self) -> u256:
        return self.count

    @gl.public.view
    def list_assets(self, start: u256, limit: u256) -> str:
        if limit == u256(0) or limit > u256(30):
            raise gl.vm.UserError('pagination bound exceeded')
        first = max(int(start), 1)
        end = min(int(self.count) + 1, first + int(limit))
        return json.dumps([json.loads(self.records[u256(i)]) for i in range(first, end)], separators=(',', ':'))
