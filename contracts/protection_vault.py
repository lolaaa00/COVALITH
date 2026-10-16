# { "Depends": "py-genlayer:1jb45aa8ynh2a9c9xn3b7qqh8sm5q93hwfp7jqmwsfhh8jpz09h6" }
from genlayer import *
import json
from datetime import datetime, timezone

# Purchase requires recent CLEAR assessments. Each cover starts after an anti-selection delay.
CLEAR_MAX_AGE = 21600       # 6 hours
INCEPTION_DELAY = 3600     # 1 hour
CLAIM_GRACE = 86400        # 24 hours after expiry
MIN_TERM = 86400           # one day
MAX_TERM = 2592000         # 30 days
MAX_COVER = 10**23         # 100,000 GEN per policy


@gl.evm.contract_interface
class _Recipient:
    class View:
        pass
    class Write:
        pass


def timestamp() -> int:
    return int(datetime.now(timezone.utc).timestamp())


MONEY_KEYS = ('capital', 'reserved', 'max_policy_cover', 'cover_wei', 'premium_wei')

def encode(data: dict) -> str:
    # JSON/JavaScript numbers above 2**53 lose wei precision. Always export amounts as strings.
    safe = {k: str(v) if k in MONEY_KEYS else v for k, v in data.items()}
    return json.dumps(safe, sort_keys=True, separators=(',', ':'))


def require(condition: bool, message: str) -> None:
    if not condition:
        raise gl.vm.UserError(message)


def quoted_premium(cover: int, rate_bps: int, days: int) -> int:
    # Rate is per 30 days; charge at least one wei, rounded up.
    return max(1, (cover * rate_bps * days + 300000 - 1) // 300000)


class ProtectionVault(gl.Contract):
    registry: Address
    engine: Address
    pool_count: u256
    policy_count: u256
    pools: TreeMap[u256, str]
    policies: TreeMap[u256, str]
    credits: TreeMap[Address, u256]
    credit_total: u256
    pool_total: u256
    transfer_attempt_count: u256
    transfer_attempts: TreeMap[u256, str]

    def __init__(self, registry: Address, engine: Address) -> None:
        self.registry = registry
        self.engine = engine
        self.pool_count = u256(0)
        self.policy_count = u256(0)
        self.credit_total = u256(0)
        self.pool_total = u256(0)
        self.transfer_attempt_count = u256(0)

    def _pool(self, pool_id: u256) -> dict:
        require(pool_id > u256(0) and pool_id <= self.pool_count, 'pool not found')
        pool = json.loads(self.pools[pool_id])
        for key in ('capital', 'reserved', 'max_policy_cover'):
            pool[key] = int(pool[key])
        return pool

    def _policy(self, policy_id: u256) -> dict:
        require(policy_id > u256(0) and policy_id <= self.policy_count, 'policy not found')
        policy = json.loads(self.policies[policy_id])
        for key in ('cover_wei', 'premium_wei'):
            policy[key] = int(policy[key])
        return policy

    def _credit(self, recipient: Address, amount: int) -> None:
        require(amount > 0, 'zero credit')
        self.credits[recipient] = self.credits.get(recipient, u256(0)) + u256(amount)
        self.credit_total += u256(amount)

    def _assessment(self, assessment_id: u256) -> dict:
        return json.loads(gl.get_contract_at(self.engine).view().get_assessment(assessment_id))

    def _clear_for_purchase(self, asset_id: int, kind: str, now: int) -> None:
        # This intentionally does not certify the absence of a pre-existing event.
        # It requires recent affirmative clear observations from both tracks.
        for track in ('DEPEG', 'COLLATERAL'):
            data = gl.get_contract_at(self.engine).view().get_latest(u256(asset_id), track)
            require(bool(data), 'fresh clear assessments required before purchase')
            result = json.loads(data)
            require(result['asset_id'] == asset_id and result['status'] == 'CLEAR',
                    'risk has not been cleared')
            require(0 <= now - result['assessed_at'] <= CLEAR_MAX_AGE,
                    'risk assessment is stale')

    @gl.public.write.payable
    def create_pool(self, asset_id: u256, risk_kind: str, max_policy_cover_wei: u256,
                    premium_rate_bps: u256, max_duration_days: u256) -> u256:
        require(risk_kind in ('DEPEG', 'COLLATERAL'), 'invalid risk kind')
        # Registry lookup must succeed; prevents pools for nonexistent assets.
        gl.get_contract_at(self.registry).view().get_asset(asset_id)
        deposit = int(gl.message.value)
        limit = int(max_policy_cover_wei)
        require(0 < limit <= MAX_COVER and deposit >= limit,
                'seed funding must cover one maximum policy')
        require(20 <= int(premium_rate_bps) <= 3000, 'invalid risk premium rate')
        require(1 <= int(max_duration_days) <= 30, 'invalid duration')
        self.pool_count += u256(1)
        i = self.pool_count
        self.pools[i] = encode({
            'id': int(i), 'asset_id': int(asset_id), 'risk_kind': risk_kind,
            'owner': str(gl.message.sender_address), 'capital': deposit,
            'reserved': 0, 'max_policy_cover': limit, 'premium_rate_bps': int(premium_rate_bps),
            'max_duration_days': int(max_duration_days), 'paused': False,
            'opened_at': timestamp(), 'policies_sold': 0, 'claims_paid': 0})
        self.pool_total += u256(deposit)
        return i

    @gl.public.write.payable
    def fund_pool(self, pool_id: u256) -> None:
        pool = self._pool(pool_id)
        require(str(gl.message.sender_address) == pool['owner'], 'only underwriter can fund pool')
        amount = int(gl.message.value)
        require(amount > 0, 'empty funding')
        pool['capital'] += amount
        self.pool_total += u256(amount)
        self.pools[pool_id] = encode(pool)

    @gl.public.write
    def set_pool_paused(self, pool_id: u256, paused: bool) -> None:
        pool = self._pool(pool_id)
        require(str(gl.message.sender_address) == pool['owner'], 'only underwriter can pause')
        pool['paused'] = paused
        self.pools[pool_id] = encode(pool)

    @gl.public.write.payable
    def buy_protection(self, pool_id: u256, cover_wei: u256, duration_days: u256) -> u256:
        pool = self._pool(pool_id)
        now = timestamp()
        require(not pool['paused'], 'pool paused')
        self._clear_for_purchase(pool['asset_id'], pool['risk_kind'], now)
        amount = int(cover_wei)
        days = int(duration_days)
        require(0 < amount <= pool['max_policy_cover'], 'cover outside pool limit')
        require(1 <= days <= pool['max_duration_days'], 'term outside pool limit')
        require(amount <= pool['capital'] - pool['reserved'], 'insufficient free collateral')
        price = quoted_premium(amount, pool['premium_rate_bps'], days)
        require(int(gl.message.value) == price, 'premium must match exact quote')
        pool['capital'] += price
        pool['reserved'] += amount
        pool['policies_sold'] += 1
        self.pool_total += u256(price)
        self.policy_count += u256(1)
        i = self.policy_count
        self.policies[i] = encode({
            'id': int(i), 'pool_id': int(pool_id), 'asset_id': pool['asset_id'],
            'risk_kind': pool['risk_kind'], 'holder': str(gl.message.sender_address),
            'cover_wei': amount, 'premium_wei': price,
            'purchased_at': now, 'starts_at': now + INCEPTION_DELAY,
            'ends_at': now + INCEPTION_DELAY + days * MIN_TERM,
            'state': 'ACTIVE', 'assessment_id': 0, 'settled_at': 0})
        self.pools[pool_id] = encode(pool)
        return i

    @gl.public.write
    def claim_protection(self, policy_id: u256, assessment_id: u256) -> None:
        policy = self._policy(policy_id)
        require(policy['state'] == 'ACTIVE', 'policy already resolved')
        require(str(gl.message.sender_address) == policy['holder'], 'only holder may claim')
        now = timestamp()
        require(now <= policy['ends_at'] + CLAIM_GRACE, 'claim window closed')
        assessment = self._assessment(assessment_id)
        require(assessment['asset_id'] == policy['asset_id'] and
                assessment['kind'] == policy['risk_kind'] and
                assessment['status'] == 'TRIGGERED', 'assessment cannot authorize payout')
        require(policy['starts_at'] <= assessment['assessed_at'] <= policy['ends_at'],
                'assessment outside coverage window')
        pool_id = u256(policy['pool_id'])
        pool = self._pool(pool_id)
        amount = policy['cover_wei']
        require(pool['capital'] >= amount and pool['reserved'] >= amount,
                'collateral accounting invariant violated')
        pool['capital'] -= amount
        pool['reserved'] -= amount
        pool['claims_paid'] += 1
        self.pool_total -= u256(amount)
        self._credit(gl.message.sender_address, amount)
        policy['state'] = 'PAID_TO_CREDIT'
        policy['assessment_id'] = int(assessment_id)
        policy['settled_at'] = now
        self.pools[pool_id] = encode(pool)
        self.policies[policy_id] = encode(policy)

    @gl.public.write
    def expire_policy(self, policy_id: u256) -> None:
        policy = self._policy(policy_id)
        require(policy['state'] == 'ACTIVE', 'policy already resolved')
        require(timestamp() > policy['ends_at'] + CLAIM_GRACE,
                'claim grace still open')
        pool_id = u256(policy['pool_id'])
        pool = self._pool(pool_id)
        require(pool['reserved'] >= policy['cover_wei'], 'reserve accounting corrupted')
        pool['reserved'] -= policy['cover_wei']
        policy['state'] = 'EXPIRED'
        policy['settled_at'] = timestamp()
        self.pools[pool_id] = encode(pool)
        self.policies[policy_id] = encode(policy)

    @gl.public.write
    def redeem_free_capital(self, pool_id: u256, amount_wei: u256) -> None:
        pool = self._pool(pool_id)
        require(str(gl.message.sender_address) == pool['owner'], 'only pool underwriter may redeem')
        amount = int(amount_wei)
        require(amount > 0 and amount <= pool['capital'] - pool['reserved'],
                'amount exceeds free capital')
        pool['capital'] -= amount
        self.pool_total -= u256(amount)
        self._credit(gl.message.sender_address, amount)
        self.pools[pool_id] = encode(pool)

    @gl.public.write
    def withdraw_credit(self) -> None:
        caller = gl.message.sender_address
        amount = self.credits.get(caller, u256(0))
        require(amount > u256(0), 'nothing to withdraw')
        # State first. Each credit can be sent only once. The emitted EVM transfer
        # is delivered after finalization; a queued attempt is NOT proof of delivery.
        self.credits[caller] = u256(0)
        self.credit_total -= amount
        self.transfer_attempt_count += u256(1)
        self.transfer_attempts[self.transfer_attempt_count] = encode({
            'id': int(self.transfer_attempt_count), 'recipient': str(caller),
            'amount_wei': str(int(amount)), 'queued_at': timestamp(),
            'state': 'QUEUED_EXTERNAL_TRANSFER'})
        _Recipient(caller).emit_transfer(value=amount)

    @gl.public.view
    def quote_premium(self, pool_id: u256, cover_wei: u256, duration_days: u256) -> u256:
        pool = self._pool(pool_id)
        require(0 < int(cover_wei) <= pool['max_policy_cover'] and
                1 <= int(duration_days) <= pool['max_duration_days'], 'invalid quote')
        return u256(quoted_premium(int(cover_wei), pool['premium_rate_bps'], int(duration_days)))

    @gl.public.view
    def get_pool(self, pool_id: u256) -> str:
        return encode(self._pool(pool_id))

    @gl.public.view
    def get_policy(self, policy_id: u256) -> str:
        return encode(self._policy(policy_id))

    @gl.public.view
    def get_credit(self, who: Address) -> u256:
        return self.credits.get(who, u256(0))

    @gl.public.view
    def get_counts(self) -> str:
        return encode({'pools': int(self.pool_count), 'policies': int(self.policy_count),
                       'transfer_attempts': int(self.transfer_attempt_count)})

    @gl.public.view
    def get_solvency(self) -> str:
        balance = int(self.balance)
        liability = int(self.pool_total + self.credit_total)
        return encode({'balance_wei': str(balance), 'pool_capital_wei': str(int(self.pool_total)),
                       'withdrawal_credits_wei': str(int(self.credit_total)),
                       'unallocated_wei': str(balance - liability),
                       'solvent': balance >= liability})

    @gl.public.view
    def get_transfer_attempt(self, attempt_id: u256) -> str:
        require(attempt_id > u256(0) and attempt_id <= self.transfer_attempt_count,
                'unknown withdrawal attempt')
        return self.transfer_attempts[attempt_id]

    @gl.public.view
    def list_pools(self, start: u256, limit: u256) -> str:
        require(u256(0) < limit <= u256(30), 'invalid page size')
        first = max(int(start), 1)
        return json.dumps([json.loads(self.pools[u256(i)]) for i in range(first,
                          min(int(self.pool_count) + 1, first + int(limit)))], separators=(',', ':'))

    @gl.public.view
    def list_policies(self, start: u256, limit: u256) -> str:
        require(u256(0) < limit <= u256(30), 'invalid page size')
        first = max(int(start), 1)
        return json.dumps([json.loads(self.policies[u256(i)]) for i in range(first,
                          min(int(self.policy_count) + 1, first + int(limit)))], separators=(',', ':'))
