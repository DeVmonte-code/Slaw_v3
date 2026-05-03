import asyncio, json
import logging
logging.basicConfig(level=logging.DEBUG)

from swiss_legal_api.engine.scan import run_benefit_scan
from swiss_legal_api.schemas.context_profile import ContextProfile
from swiss_legal_api.catalog import load_catalog

async def main():
    profile = ContextProfile(**json.load(open('fixtures/bern_tenant_profile.json')))
    catalog = load_catalog()
    # We want to trace `bern_rental_conciliation_free_procedure`
    import swiss_legal_api.engine.scan as scan_module
    original_verify = scan_module.verify_entitlement
    
    async def mocked_verify(*args, **kwargs):
        ent = args[0]
        if 'bern_rental' in ent.id:
            print("EVALUATING:", ent.id)
            res = await original_verify(*args, **kwargs)
            print("RESULT for", ent.id, ":", res)
            return res
        return await original_verify(*args, **kwargs)

    scan_module.verify_entitlement = mocked_verify
    results = await run_benefit_scan(profile, catalog)
    print("OUTPUT:", [o.entitlement_id for o in results.benefits])

if __name__ == '__main__':
    asyncio.run(main())
