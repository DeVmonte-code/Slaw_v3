import asyncio, json
import logging
logging.basicConfig(level=logging.DEBUG)

from swiss_legal_api.engine.scan import run_benefit_scan
from swiss_legal_api.schemas.context_profile import ContextProfile
from swiss_legal_api.catalog import load_catalog

async def main():
    profile = ContextProfile(**json.load(open('fixtures/bern_tenant_profile.json')))
    catalog = load_catalog()
    results = await run_benefit_scan(profile, catalog)
    for s in getattr(results, 'suppressed_benefits', []):
        if 'bern' in s.entitlement_id:
            print('SUPPRESSED:', s.entitlement_id, s.verification_reasoning)

if __name__ == '__main__':
    asyncio.run(main())
